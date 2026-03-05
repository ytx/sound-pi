"""Media key input via evdev — Consumer Control and BT AVRCP devices."""

import fcntl
import os
import re
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path

from logger import get_logger

log = get_logger("media_input")

# evdev input_event on 64-bit: tv_sec(q) + tv_usec(q) + type(H) + code(H) + value(i)
EVENT_FORMAT = "qqHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

EV_KEY = 0x01

# EVIOCGRAB ioctl — exclusive access to prevent WirePlumber double-handling
EVIOCGRAB = 0x40044590

# Key codes (Consumer Control)
KEY_PLAYPAUSE = 164
KEY_NEXTSONG = 163
KEY_PREVIOUSSONG = 165
KEY_VOLUMEUP = 115
KEY_VOLUMEDOWN = 114

CODE_TO_EVENT = {
    KEY_PLAYPAUSE: "play_pause",
    KEY_NEXTSONG: "next",
    KEY_PREVIOUSSONG: "prev",
    KEY_VOLUMEUP: "volume_up",
    KEY_VOLUMEDOWN: "volume_down",
}


@dataclass
class MediaDevice:
    event_path: str       # "/dev/input/event0"
    name: str             # "Consumer Control"
    uniq: str             # USB serial or BT addr
    phys: str             # "usb-xhci-hcd.1-1.3/input3" or BT phys
    fd: int | None = field(default=None, repr=False)


# Minimum interval (seconds) between same key events from same device
DEBOUNCE_INTERVAL = 0.3


class MediaInputManager:
    """Monitors evdev Consumer Control / AVRCP devices for media key events."""

    def __init__(self):
        self._devices: list[MediaDevice] = []
        self._stub = False
        self._last_rescan = 0.0
        # Debounce: (event_path, code) → last event timestamp
        self._last_event: dict[tuple[str, int], float] = {}

    def start(self):
        """Detect and open media input devices."""
        self._scan_devices()

    def stop(self):
        """Close all open fds."""
        for dev in self._devices:
            self._close_device(dev)
        self._devices.clear()
        log.info("media input stopped")

    def poll(self) -> list[tuple[str, "MediaDevice"]]:
        """Poll all devices for key events.

        Returns list of (event_name, device) for press events only.
        """
        results = []
        for dev in self._devices:
            if dev.fd is None:
                continue
            try:
                while True:
                    data = os.read(dev.fd, EVENT_SIZE)
                    if len(data) < EVENT_SIZE:
                        break
                    _sec, _usec, ev_type, code, value = struct.unpack(
                        EVENT_FORMAT, data
                    )
                    # EV_KEY, value=1 (press) only — ignore release(0) and repeat(2)
                    if ev_type == EV_KEY and value == 1 and code in CODE_TO_EVENT:
                        now = time.monotonic()
                        debounce_key = (dev.event_path, code)
                        last = self._last_event.get(debounce_key, 0.0)
                        if now - last < DEBOUNCE_INTERVAL:
                            continue
                        self._last_event[debounce_key] = now
                        event_name = CODE_TO_EVENT[code]
                        log.debug("key event: %s from %s", event_name, dev.name)
                        results.append((event_name, dev))
            except BlockingIOError:
                pass
            except OSError as e:
                # Device disconnected
                log.warning("read error on %s: %s", dev.event_path, e)
                self._close_device(dev)
        return results

    def maybe_rescan(self, interval: float = 10.0):
        """Rescan if enough time has elapsed since last scan."""
        now = time.monotonic()
        if now - self._last_rescan >= interval:
            self._last_rescan = now
            self._incremental_scan()

    def _close_device(self, dev: MediaDevice):
        """Release grab and close fd."""
        if dev.fd is not None:
            try:
                fcntl.ioctl(dev.fd, EVIOCGRAB, 0)
            except OSError:
                pass
            try:
                os.close(dev.fd)
            except OSError:
                pass
            dev.fd = None

    def _open_device(self, event_path: str, name: str) -> int | None:
        """Open evdev device with exclusive grab."""
        if not os.path.exists(event_path):
            return None
        try:
            fd = os.open(event_path, os.O_RDONLY | os.O_NONBLOCK)
            try:
                fcntl.ioctl(fd, EVIOCGRAB, 1)
            except OSError as e:
                log.warning("EVIOCGRAB failed on %s: %s", event_path, e)
            log.info("opened media device: %s (%s)", event_path, name)
            return fd
        except OSError as e:
            log.warning("cannot open %s: %s", event_path, e)
            return None

    def _scan_devices(self):
        """Parse /proc/bus/input/devices to find Consumer Control / AVRCP."""
        self._last_rescan = time.monotonic()
        found = self._parse_proc_devices()
        for dev in found:
            dev.fd = self._open_device(dev.event_path, dev.name)
            self._devices.append(dev)
        if not self._devices:
            log.info("no media input devices found")

    def _incremental_scan(self):
        """Add newly appeared devices without disrupting existing ones."""
        # Prune dead devices
        for dev in self._devices:
            if dev.fd is not None and not os.path.exists(dev.event_path):
                log.info("device removed: %s", dev.event_path)
                self._close_device(dev)
        self._devices = [d for d in self._devices if d.fd is not None]

        # Find new devices
        known_paths = {d.event_path for d in self._devices}
        found = self._parse_proc_devices()
        for dev in found:
            if dev.event_path not in known_paths:
                dev.fd = self._open_device(dev.event_path, dev.name)
                if dev.fd is not None:
                    self._devices.append(dev)

    def _parse_proc_devices(self) -> list[MediaDevice]:
        """Parse /proc/bus/input/devices and return matching MediaDevice list."""
        proc_path = Path("/proc/bus/input/devices")
        if not proc_path.exists():
            self._stub = True
            return []

        try:
            text = proc_path.read_text()
        except OSError as e:
            log.warning("cannot read %s: %s", proc_path, e)
            self._stub = True
            return []

        results = []
        for block in text.split("\n\n"):
            if not block.strip():
                continue
            name = _parse_field(block, "N")
            if not name:
                continue
            # Skip touchscreen
            if "ads7846" in name.lower():
                continue
            # Match Consumer Control or AVRCP
            if "consumer control" not in name.lower() and "(avrcp)" not in name.lower():
                continue
            handlers = _parse_field(block, "H")
            event_path = _extract_event_path(handlers)
            if not event_path:
                continue
            uniq = _parse_field(block, "U") or ""
            phys = _parse_field(block, "P") or ""
            results.append(MediaDevice(
                event_path=event_path,
                name=name,
                uniq=uniq,
                phys=phys,
            ))
        return results


def _parse_field(block: str, prefix: str) -> str | None:
    """Extract value from /proc/bus/input/devices field line.

    Lines look like:
      N: Name="Consumer Control"
      U: Uniq=D09739B16F03195D3B07
      P: Phys=usb-xhci-hcd.1-1.3/input3
      H: Handlers=kbd event0
    """
    for line in block.splitlines():
        if line.startswith(f"{prefix}:"):
            val = line.split(":", 1)[1].strip()
            # Remove field name prefix (e.g. "Name=", "Uniq=")
            if "=" in val:
                val = val.split("=", 1)[1]
            # Strip quotes
            return val.strip('"')
    return None


def _extract_event_path(handlers: str | None) -> str | None:
    """Extract /dev/input/eventN from Handlers line."""
    if not handlers:
        return None
    m = re.search(r"(event\d+)", handlers)
    if m:
        return f"/dev/input/{m.group(1)}"
    return None
