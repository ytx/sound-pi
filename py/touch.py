"""Touch input via evdev (ADS7846) with pygame mouse fallback."""

import os
import struct
from pathlib import Path

from logger import get_logger

log = get_logger("touch")

WIDTH, HEIGHT = 480, 320
TOUCH_MAX = 4095

# evdev input_event: struct timeval (16 bytes on aarch64) + type(H) + code(H) + value(i)
# on 64-bit: tv_sec(q) + tv_usec(q) + type(H) + code(H) + value(i) = 24 bytes
EVENT_FORMAT = "qqHHi"
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

EV_ABS = 0x03
EV_KEY = 0x01
EV_SYN = 0x00
ABS_X = 0x00
ABS_Y = 0x01
BTN_TOUCH = 0x14A

# Touch event types
TOUCH_DOWN = "down"
TOUCH_MOVE = "move"
TOUCH_UP = "up"


def _find_ads7846() -> str | None:
    """Find ADS7846 touchscreen input device."""
    input_dir = Path("/sys/class/input")
    if not input_dir.exists():
        return None
    for dev_dir in sorted(input_dir.iterdir()):
        name_file = dev_dir / "device" / "name"
        if name_file.exists():
            try:
                name = name_file.read_text().strip()
                if "ads7846" in name.lower():
                    dev = f"/dev/input/{dev_dir.name}"
                    log.info("found ADS7846: %s (%s)", dev, name)
                    return dev
            except Exception:
                pass
    return None


class Touch:
    """Reads touch events from evdev or falls back to pygame mouse."""

    def __init__(self):
        self._fd = None
        self._use_evdev = False
        self._raw_x = 0
        self._raw_y = 0
        self._touching = False
        self._was_touching = False  # previous state — distinguishes DOWN from MOVE

        dev = _find_ads7846()
        if dev and os.path.exists(dev):
            try:
                self._fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
                self._use_evdev = True
                log.info("evdev mode: %s", dev)
            except Exception as e:
                log.warning("evdev open failed: %s — using pygame mouse", e)

        if not self._use_evdev:
            log.info("mouse fallback mode")

    def poll(self) -> list[tuple[str, int, int]]:
        """Return list of (event_type, x, y) touch events since last poll."""
        if self._use_evdev:
            return self._poll_evdev()
        return self._poll_pygame()

    def _poll_evdev(self) -> list[tuple[str, int, int]]:
        events = []
        try:
            while True:
                data = os.read(self._fd, EVENT_SIZE)
                if len(data) < EVENT_SIZE:
                    break
                _sec, _usec, ev_type, code, value = struct.unpack(EVENT_FORMAT, data)
                if ev_type == EV_ABS:
                    if code == ABS_X:
                        self._raw_x = value
                    elif code == ABS_Y:
                        self._raw_y = value
                elif ev_type == EV_KEY and code == BTN_TOUCH:
                    if value == 1:
                        self._touching = True
                    elif value == 0:
                        self._touching = False
                        x, y = self._map_coords()
                        events.append((TOUCH_UP, x, y))
                elif ev_type == EV_SYN and self._touching:
                    x, y = self._map_coords()
                    if not self._was_touching:
                        events.append((TOUCH_DOWN, x, y))
                        self._was_touching = True
                    else:
                        events.append((TOUCH_MOVE, x, y))
        except BlockingIOError:
            pass
        except Exception as e:
            log.warning("evdev read error: %s", e)
        # Update state for next poll cycle
        if not self._touching:
            self._was_touching = False
        return events

    def _map_coords(self) -> tuple[int, int]:
        x = int(self._raw_x * WIDTH / TOUCH_MAX)
        y = int(self._raw_y * HEIGHT / TOUCH_MAX)
        return max(0, min(WIDTH - 1, x)), max(0, min(HEIGHT - 1, y))

    def _poll_pygame(self) -> list[tuple[str, int, int]]:
        import pygame
        events = []
        for ev in pygame.event.get([pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION]):
            if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                events.append((TOUCH_DOWN, ev.pos[0], ev.pos[1]))
                self._touching = True
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                events.append((TOUCH_UP, ev.pos[0], ev.pos[1]))
                self._touching = False
            elif ev.type == pygame.MOUSEMOTION and self._touching:
                events.append((TOUCH_MOVE, ev.pos[0], ev.pos[1]))
        return events

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        log.info("touch closed")
