"""PipeWire audio manager and capture."""

import subprocess
import threading
import struct
import math
import re
import time

import config as cfg
from logger import get_logger

log = get_logger("audio")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    log.warning("numpy not available — FFT disabled")

SAMPLE_RATE = 48000
CHANNELS = 2
CHUNK_FRAMES = 1024  # frames per read
BYTES_PER_SAMPLE = 2  # S16LE
CHUNK_BYTES = CHUNK_FRAMES * CHANNELS * BYTES_PER_SAMPLE

NUM_BANDS = 32


class AudioCapture:
    """Capture audio from PipeWire via pw-cat and compute levels + spectrum."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()

        # Current audio data
        self.level_l: float = 0.0
        self.level_r: float = 0.0
        self.peak_l: float = 0.0
        self.peak_r: float = 0.0
        self.spectrum: list[float] = [0.0] * NUM_BANDS

        self._dummy = False

    def _find_uac2_source(self) -> str | None:
        """Find UAC2 Gadget capture source name via pw-cli."""
        try:
            out = subprocess.check_output(
                ["pw-cli", "ls", "Node"], timeout=5, text=True, stderr=subprocess.DEVNULL,
            )
            # Parse pw-cli output into blocks separated by "id NNN" lines
            # Find the block with node.nick containing "UAC2"
            lines = out.splitlines()
            block_lines: list[str] = []
            found_name = None
            for line in lines:
                if line.strip().startswith("id "):
                    # Process previous block
                    found_name = self._check_uac2_block(block_lines)
                    if found_name:
                        return found_name
                    block_lines = [line]
                else:
                    block_lines.append(line)
            # Check last block
            return self._check_uac2_block(block_lines)
        except Exception as e:
            log.debug("UAC2 source search failed: %s", e)
        return None

    def _check_uac2_block(self, lines: list[str]) -> str | None:
        """Check if a pw-cli node block is the UAC2 capture source."""
        has_uac2 = False
        node_name = None
        for line in lines:
            stripped = line.strip()
            if "node.nick" in stripped and "UAC2" in stripped:
                has_uac2 = True
            if "node.name" in stripped and "=" in stripped:
                node_name = stripped.split("=", 1)[1].strip().strip('"')
        if has_uac2 and node_name:
            log.info("found UAC2 source: %s", node_name)
            return node_name
        return None

    def start(self):
        """Start capturing audio."""
        if self._running:
            return
        self._running = True

        try:
            cmd = [
                "pw-cat", "--record", "--format", "s16",
                "--rate", str(SAMPLE_RATE),
                "--channels", str(CHANNELS),
            ]
            # Try to target UAC2 Gadget source (retry — PipeWire may still be starting)
            uac2 = None
            for attempt in range(5):
                uac2 = self._find_uac2_source()
                if uac2:
                    break
                log.debug("UAC2 not found yet, retry %d/5", attempt + 1)
                import time
                time.sleep(2)
            if uac2:
                cmd += ["--target", uac2]
            cmd.append("-")

            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            log.info("pw-cat capture started (target=%s)", uac2 or "default")
        except FileNotFoundError:
            log.warning("pw-cat not found — using dummy data")
            self._dummy = True
            self._thread = threading.Thread(target=self._dummy_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._running = False
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        log.info("capture stopped")

    def _read_loop(self):
        while self._running and self._proc and self._proc.stdout:
            try:
                data = self._proc.stdout.read(CHUNK_BYTES)
                if not data:
                    break
                self._process_chunk(data)
            except Exception as e:
                log.warning("read error: %s", e)
                break
        self._running = False

    def _process_chunk(self, data: bytes):
        n_samples = len(data) // BYTES_PER_SAMPLE
        if n_samples < 2:
            return

        if HAS_NUMPY:
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            left = samples[0::2]
            right = samples[1::2]

            rms_l = float(np.sqrt(np.mean(left ** 2)))
            rms_r = float(np.sqrt(np.mean(right ** 2)))

            # FFT on mono mix
            mono = (left + right) * 0.5
            fft_data = np.abs(np.fft.rfft(mono)) / len(mono)
            spectrum = self._compute_bands(fft_data)
        else:
            # Fallback without numpy
            fmt = f"<{n_samples}h"
            raw = struct.unpack(fmt, data[:n_samples * 2])
            left = raw[0::2]
            right = raw[1::2]
            rms_l = math.sqrt(sum(s * s for s in left) / len(left)) / 32768.0
            rms_r = math.sqrt(sum(s * s for s in right) / len(right)) / 32768.0
            spectrum = [0.0] * NUM_BANDS

        with self._lock:
            self.level_l = rms_l
            self.level_r = rms_r
            self.peak_l = max(self.peak_l, rms_l)
            self.peak_r = max(self.peak_r, rms_r)
            self.spectrum = spectrum

    def _compute_bands(self, fft_data) -> list[float]:
        """Map FFT bins to NUM_BANDS logarithmic frequency bands."""
        n = len(fft_data)
        if n < NUM_BANDS:
            return [0.0] * NUM_BANDS
        bands = []
        for i in range(NUM_BANDS):
            lo = int(n * (2 ** (i / NUM_BANDS * 10) - 1) / (2 ** 10 - 1))
            hi = int(n * (2 ** ((i + 1) / NUM_BANDS * 10) - 1) / (2 ** 10 - 1))
            lo = max(1, min(lo, n - 1))
            hi = max(lo + 1, min(hi, n))
            val = float(np.max(fft_data[lo:hi]))
            # Convert to dB-ish scale (0..1)
            db = max(0.0, min(1.0, 1.0 + math.log10(val + 1e-10) / 3.0))
            bands.append(db)
        return bands

    def _dummy_loop(self):
        """Generate dummy data for development."""
        import time
        import random
        t = 0.0
        while self._running:
            t += 0.02
            with self._lock:
                self.level_l = 0.3 + 0.2 * math.sin(t * 2.0) + random.random() * 0.05
                self.level_r = 0.3 + 0.2 * math.sin(t * 2.3) + random.random() * 0.05
                self.peak_l = max(self.peak_l, self.level_l)
                self.peak_r = max(self.peak_r, self.level_r)
                self.spectrum = [
                    max(0.0, min(1.0, 0.5 * math.sin(t * (1 + i * 0.3)) + 0.5 + random.random() * 0.1))
                    for i in range(NUM_BANDS)
                ]
            time.sleep(0.02)

    def get_data(self) -> dict:
        """Get current audio data (thread-safe)."""
        with self._lock:
            data = {
                "level_l": self.level_l,
                "level_r": self.level_r,
                "peak_l": self.peak_l,
                "peak_r": self.peak_r,
                "spectrum": list(self.spectrum),
            }
            # Decay peaks
            self.peak_l *= 0.98
            self.peak_r *= 0.98
            return data


class PipeWireManager:
    """Control PipeWire via wpctl and manage audio routing."""

    def __init__(self):
        self._loopback_procs: dict[str, subprocess.Popen] = {}
        self._sinks_cache: list[dict] = []
        self._uac2_source: str | None = None

    # ── ALSA device discovery ──

    # Cards to exclude from the add-device list
    _EXCLUDE_NICKS = {"bcm2835 Headphones", "vc4-hdmi-0", "vc4-hdmi-1", "UAC2_Gadget"}

    def list_alsa_playback_devices(self) -> list[dict]:
        """List ALSA playback devices via aplay -l.
        Returns: [{"card_num": 4, "card_name": "B10Pro",
                   "long_name": "B10Pro", "description": "USB Audio"}]
        """
        try:
            out = subprocess.check_output(
                ["aplay", "-l"], timeout=5, text=True, stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.warning("aplay -l failed: %s", e)
            return []

        devices: list[dict] = []
        # "card 4: B10Pro [B10Pro], device 0: USB Audio [USB Audio]"
        for m in re.finditer(
            r"^card\s+(\d+):\s+(\S+)\s+\[(.+?)\],\s+device\s+\d+:\s+(.+?)\s+\[",
            out, re.MULTILINE,
        ):
            card_num = int(m.group(1))
            card_name = m.group(2)
            long_name = m.group(3)
            description = m.group(4)
            devices.append({
                "card_num": card_num,
                "card_name": card_name,
                "long_name": long_name,
                "description": description,
            })
        return devices

    def list_pw_audio_devices(self) -> list[dict]:
        """List PipeWire Audio/Device entries.
        Returns: [{"id": 48, "nick": "B10Pro", "device_name": "alsa_card.usb-..."}]
        """
        try:
            out = subprocess.check_output(
                ["pw-cli", "ls", "Device"], timeout=5, text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.warning("pw-cli ls Device failed: %s", e)
            return []

        devices: list[dict] = []
        lines = out.splitlines()
        block: list[str] = []
        for line in lines:
            if line.strip().startswith("id "):
                dev = self._parse_pw_device_block(block)
                if dev:
                    devices.append(dev)
                block = [line]
            else:
                block.append(line)
        dev = self._parse_pw_device_block(block)
        if dev:
            devices.append(dev)
        return devices

    @staticmethod
    def _parse_pw_device_block(lines: list[str]) -> dict | None:
        props: dict[str, str] = {}
        dev_id = None
        for line in lines:
            s = line.strip()
            if s.startswith("id "):
                m = re.match(r"id\s+(\d+)", s)
                if m:
                    dev_id = int(m.group(1))
            if "=" in s and not s.startswith("id "):
                key, _, val = s.partition("=")
                key = key.strip().strip("*").strip()
                val = val.strip().strip('"')
                props[key] = val
        if props.get("media.class") != "Audio/Device":
            return None
        if props.get("device.api") != "alsa":
            return None
        return {
            "id": dev_id,
            "nick": props.get("device.nick", ""),
            "device_name": props.get("device.name", ""),
        }

    def list_addable_devices(self) -> list[dict]:
        """Return playback devices available to add as output.
        Includes ALSA (USB) and Bluetooth sinks.
        Returns: [{"card_name": "B10Pro", "long_name": "B10Pro",
                   "pw_device_id": 48, "pw_device_name": "alsa_card.usb-...",
                   "is_bluez": False}]
        """
        alsa = self.list_alsa_playback_devices()
        pw_devs = self.list_pw_audio_devices()

        # Build nick → pw_device map
        nick_map = {d["nick"]: d for d in pw_devs}

        result: list[dict] = []
        for a in alsa:
            # Skip internal devices
            if a["long_name"] in self._EXCLUDE_NICKS:
                continue
            pw = nick_map.get(a["long_name"])
            if not pw:
                continue
            result.append({
                "card_name": a["card_name"],
                "long_name": a["long_name"],
                "pw_device_id": pw["id"],
                "pw_device_name": pw["device_name"],
                "is_bluez": False,
            })

        # Add Bluetooth sinks (bluez_output.* in PipeWire)
        self.list_sinks()
        for s in self._sinks_cache:
            node_name = s.get("node_name", "")
            if not node_name.startswith("bluez_output."):
                continue
            display = s.get("description") or s.get("nick") or node_name
            result.append({
                "card_name": node_name,
                "long_name": display,
                "pw_device_id": s.get("id"),
                "pw_device_name": node_name,
                "is_bluez": True,
            })

        return result

    def ensure_sink_profile(self, pw_device_id: int, pw_device_name: str = "") -> str | None:
        """Ensure the PipeWire device has a Sink-capable profile.
        Tries each profile with Audio/Sink until one produces a working sink
        (audio.channels > 0). Returns node_name or None.
        """
        # Check if a sink already exists for this device
        self.list_sinks()
        existing = self._find_sink_for_device(pw_device_id)
        if existing:
            return existing

        # No sink — try each profile that has Audio/Sink
        candidates = self._find_sink_profile_indices(pw_device_id)
        if not candidates:
            log.warning("no sink-capable profile for device %d", pw_device_id)
            return None

        for profile_idx in candidates:
            log.info("trying device %d profile index %d", pw_device_id, profile_idx)
            try:
                subprocess.run(
                    ["wpctl", "set-profile", str(pw_device_id), str(profile_idx)],
                    timeout=5, check=True,
                )
            except Exception as e:
                log.warning("set-profile failed for device %d: %s", pw_device_id, e)
                continue

            # Wait for sink to appear
            for _ in range(10):
                time.sleep(0.3)
                self.list_sinks()
                found = self._find_sink_for_device(pw_device_id)
                if found:
                    log.info("sink found on profile %d: %s", profile_idx, found)
                    return found

            log.info("profile %d: no sink appeared, trying next", profile_idx)

        log.warning("no sink found for device %d", pw_device_id)
        return None

    @staticmethod
    def _find_sink_profile_indices(pw_device_id: int) -> list[int]:
        """Find all profile indices that include Audio/Sink for the device.
        Returns indices sorted: non-pro-audio first (pro-audio is often broken).
        """
        try:
            out = subprocess.check_output(
                ["pw-cli", "enum-params", str(pw_device_id), "EnumProfile"],
                timeout=5, text=True, stderr=subprocess.DEVNULL,
            )
        except Exception:
            return []

        pro_audio: list[int] = []
        other: list[int] = []
        blocks = re.split(r"^(?=\s*Object:)", out, flags=re.MULTILINE)
        for block in blocks:
            if "Audio/Sink" not in block:
                continue
            m = re.search(r"Profile:index.*?\n\s+Int\s+(\d+)", block)
            if not m:
                continue
            idx = int(m.group(1))
            if idx == 0:  # "off"
                continue
            if "pro-audio" in block:
                pro_audio.append(idx)
            else:
                other.append(idx)
        # Prefer non-pro-audio profiles (analog-stereo etc.)
        return other + pro_audio

    def _find_sink_for_device(self, pw_device_id: int) -> str | None:
        """Find a sink belonging to a PipeWire device.
        Uses wpctl status to get sink IDs, then wpctl inspect to match device.id.
        """
        sink_ids = self._list_sink_ids_from_status()
        for sid in sink_ids:
            try:
                raw = subprocess.check_output(
                    ["wpctl", "inspect", str(sid)], timeout=3,
                    stderr=subprocess.DEVNULL,
                )
                out = raw.decode("utf-8", errors="replace")
                dev_id = None
                node_name = None
                for line in out.splitlines():
                    s = line.strip()
                    if "device.id" in s and "=" in s:
                        dev_id = s.split("=", 1)[1].strip().strip('"')
                    if "node.name" in s and "=" in s:
                        node_name = s.split("=", 1)[1].strip().strip('"')
                if dev_id == str(pw_device_id) and node_name:
                    return node_name
            except Exception:
                pass
        return None

    @staticmethod
    def _list_sink_ids_from_status() -> list[int]:
        """Parse wpctl status to get all Sink node IDs."""
        try:
            out = subprocess.check_output(
                ["wpctl", "status"], timeout=5, text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return []
        ids: list[int] = []
        in_sinks = False
        for line in out.splitlines():
            stripped = line.strip()
            if "Sinks:" in stripped:
                in_sinks = True
                continue
            if in_sinks:
                if "Sources:" in stripped or "Filters:" in stripped or "Streams:" in stripped:
                    in_sinks = False
                    continue
                # " *   73. XROUND..." or "     35. Built-in..."
                m = re.search(r"(\d+)\.", stripped)
                if m:
                    ids.append(int(m.group(1)))
        return ids

    # ── Sink discovery ──

    def list_sinks(self) -> list[dict]:
        """Return all Audio/Sink nodes.
        Returns: [{"id": 73, "node_name": "alsa_output.usb-...",
                   "nick": "...", "description": "..."}]
        """
        try:
            out = subprocess.check_output(
                ["pw-cli", "ls", "Node"], timeout=5, text=True,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            log.warning("list_sinks failed: %s", e)
            return []

        sinks: list[dict] = []
        lines = out.splitlines()
        block: list[str] = []
        for line in lines:
            if line.strip().startswith("id "):
                sink = self._parse_sink_block(block)
                if sink:
                    sinks.append(sink)
                block = [line]
            else:
                block.append(line)
        sink = self._parse_sink_block(block)
        if sink:
            sinks.append(sink)

        self._sinks_cache = sinks
        return sinks

    @staticmethod
    def _parse_sink_block(lines: list[str]) -> dict | None:
        """Parse a pw-cli node block into a sink dict if it's Audio/Sink."""
        props: dict[str, str] = {}
        node_id = None
        for line in lines:
            s = line.strip()
            if s.startswith("id "):
                # "id 73, type PipeWire:Interface:Node/3, ..."
                m = re.match(r"id\s+(\d+)", s)
                if m:
                    node_id = int(m.group(1))
            if "=" in s and not s.startswith("id "):
                key, _, val = s.partition("=")
                key = key.strip().strip("*").strip()
                val = val.strip().strip('"')
                props[key] = val
        node_name = props.get("node.name", "")
        if not node_name:
            return None
        media_class = props.get("media.class", "")
        # BT sinks may not have media.class in pw-cli ls Node output
        if media_class != "Audio/Sink" and not node_name.startswith("bluez_output."):
            return None
        return {
            "id": node_id,
            "node_name": node_name,
            "nick": props.get("node.nick", ""),
            "description": props.get("node.description", ""),
        }

    def resolve_node_name(self, node_name: str) -> int | None:
        """node_name → current wpctl ID. Uses cached sink list."""
        if not self._sinks_cache:
            self.list_sinks()
        for s in self._sinks_cache:
            if s["node_name"] == node_name:
                return s["id"]
        # Cache miss — refresh once
        self.list_sinks()
        for s in self._sinks_cache:
            if s["node_name"] == node_name:
                return s["id"]
        return None

    # ── Per-sink volume/mute ──

    def get_sink_volume(self, wpctl_id: int) -> tuple[float, bool]:
        """wpctl get-volume <id> → (volume 0.0-1.0, muted)."""
        try:
            out = subprocess.check_output(
                ["wpctl", "get-volume", str(wpctl_id)],
                timeout=2, text=True,
            )
            parts = out.strip().split()
            vol = float(parts[1]) if len(parts) >= 2 else 0.5
            muted = "[MUTED]" in out
            return (vol, muted)
        except Exception as e:
            log.warning("get_sink_volume(%d) failed: %s", wpctl_id, e)
            return (0.5, False)

    def set_sink_volume(self, wpctl_id: int, volume: float):
        """Set volume on a specific sink (0.0-1.0)."""
        vol = max(0.0, min(1.0, volume))
        try:
            subprocess.run(
                ["wpctl", "set-volume", str(wpctl_id), f"{vol:.2f}"],
                timeout=2, check=True,
            )
        except Exception as e:
            log.warning("set_sink_volume(%d) failed: %s", wpctl_id, e)

    def set_sink_mute(self, wpctl_id: int, muted: bool):
        """Set mute state on a specific sink."""
        try:
            subprocess.run(
                ["wpctl", "set-mute", str(wpctl_id), "1" if muted else "0"],
                timeout=2, check=True,
            )
        except Exception as e:
            log.warning("set_sink_mute(%d) failed: %s", wpctl_id, e)

    # ── Multi-sink routing ──

    def _find_uac2_source(self) -> str | None:
        """Find and cache the UAC2 gadget source node name."""
        if self._uac2_source:
            return self._uac2_source
        self._uac2_source = self._find_node_name("UAC2")
        return self._uac2_source

    def start_routing(self, targets: list[str] | None = None):
        """Start pw-loopback for each target node_name.
        If targets is None, reads from config output_devices.
        Resolves node names and ensures sink profiles before starting.
        """
        source = self._find_uac2_source()
        if not source:
            log.info("routing: no UAC2 source found, skipping")
            return

        if targets is None:
            devices = cfg.get("output_devices", [])
            if not devices:
                log.info("routing: no output devices configured, no loopback started")
                return
            # Pass 1: resolve all node names (may trigger profile switches)
            config_changed = False
            resolved_targets: list[str] = []
            for d in devices:
                node_name = d.get("node_name", "")
                pw_device_name = d.get("pw_device_name", "")
                # BT sinks (bluez_output.*) don't need resolution
                if node_name.startswith("bluez_output."):
                    resolved_targets.append(node_name)
                    continue
                # Verify node exists; if not, resolve via device
                resolved = self.resolve_node_name(node_name)
                if not resolved and pw_device_name:
                    new_name = self._resolve_by_device_name(pw_device_name)
                    if new_name and new_name != node_name:
                        log.info("routing: node_name updated %s → %s", node_name, new_name)
                        d["node_name"] = new_name
                        node_name = new_name
                        config_changed = True
                resolved_targets.append(node_name)
            if config_changed:
                cfg.set("output_devices", devices)
            # Allow PipeWire to stabilize after profile switches
            time.sleep(1)
            # Pass 2: start all loopbacks
            for node_name in resolved_targets:
                self._start_loopback(source, node_name, node_name)
            # Pass 3: apply saved volume/mute to each sink
            time.sleep(0.5)
            for d in devices:
                node_name = d.get("node_name", "")
                wpctl_id = self.resolve_node_name(node_name)
                if wpctl_id:
                    self.set_sink_volume(wpctl_id, d.get("volume", 0.8))
                    self.set_sink_mute(wpctl_id, d.get("muted", False))
            if config_changed:
                cfg.set("output_devices", devices)
            return

        for node_name in targets:
            self._start_loopback(source, node_name, node_name)

    def _resolve_by_device_name(self, pw_device_name: str) -> str | None:
        """Find a sink by PipeWire device name, ensuring profile if needed."""
        pw_devs = self.list_pw_audio_devices()
        for d in pw_devs:
            if d["device_name"] == pw_device_name:
                return self.ensure_sink_profile(d["id"], pw_device_name)
        return None

    def _start_loopback(self, source: str, sink: str | None, key: str):
        """Start a single pw-loopback process."""
        if key in self._loopback_procs:
            return
        cmd = [
            "pw-loopback",
            "-C", source,
            "--channels", "2",
            "--latency", "50",
        ]
        if sink:
            cmd += ["-P", sink]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self._loopback_procs[key] = proc
            log.info("loopback started: %s → %s (pid=%d)",
                     source, sink or "default", proc.pid)
        except Exception as e:
            log.warning("loopback start failed (%s): %s", sink or "default", e)

    def add_route(self, node_name: str, card_name: str = "",
                  pw_device_name: str = "") -> bool:
        """Add routing to a single sink. Returns True on success."""
        source = self._find_uac2_source()
        if not source:
            log.warning("add_route: no UAC2 source")
            return False
        # Remove default loopback if present
        if "__default__" in self._loopback_procs:
            self._stop_loopback("__default__")
        self._start_loopback(source, node_name, node_name)
        return node_name in self._loopback_procs

    def remove_route(self, node_name: str):
        """Stop routing to a single sink."""
        if node_name in self._loopback_procs:
            self._stop_loopback(node_name)
            return
        # Key mismatch (e.g. profile changed node_name) — find by -P target in proc.args
        for key, proc in list(self._loopback_procs.items()):
            try:
                if node_name in (proc.args or []):
                    self._stop_loopback(key)
                    return
            except Exception:
                pass
        log.warning("remove_route: no loopback found for %s", node_name)

    def _stop_loopback(self, key: str):
        proc = self._loopback_procs.pop(key, None)
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.info("loopback stopped: %s", key)

    def stop_routing(self):
        """Stop all pw-loopback processes."""
        for key in list(self._loopback_procs):
            self._stop_loopback(key)
        log.info("all routing stopped")

    # ── Legacy node finder ──

    def _find_node_name(self, nick_pattern: str) -> str | None:
        """Find a PipeWire node name by nick pattern."""
        try:
            out = subprocess.check_output(
                ["pw-cli", "ls", "Node"], timeout=5, text=True,
                stderr=subprocess.DEVNULL,
            )
            lines = out.splitlines()
            block: list[str] = []
            for line in lines:
                if line.strip().startswith("id "):
                    result = self._match_node_block(block, nick_pattern)
                    if result:
                        return result
                    block = [line]
                else:
                    block.append(line)
            return self._match_node_block(block, nick_pattern)
        except Exception:
            return None

    @staticmethod
    def _match_node_block(lines: list[str], nick_pattern: str) -> str | None:
        has_nick = False
        node_name = None
        for line in lines:
            s = line.strip()
            if "node.nick" in s and nick_pattern in s:
                has_nick = True
            if "node.name" in s and "=" in s:
                node_name = s.split("=", 1)[1].strip().strip('"')
        return node_name if has_nick else None

    # ── Legacy master volume (kept for backward compat) ──

    def get_volume(self) -> int:
        """Get current master volume as 0-100."""
        try:
            out = subprocess.check_output(
                ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                timeout=2, text=True,
            )
            parts = out.strip().split()
            if len(parts) >= 2:
                return int(float(parts[1]) * 100)
        except Exception as e:
            log.warning("get_volume failed: %s", e)
        return 50

    def set_volume(self, percent: int):
        """Set master volume (0-100)."""
        val = max(0, min(100, percent)) / 100.0
        try:
            subprocess.run(
                ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{val:.2f}"],
                timeout=2, check=True,
            )
        except Exception as e:
            log.warning("set_volume failed: %s", e)

    def set_mute(self, muted: bool):
        """Set mute state."""
        state = "1" if muted else "0"
        try:
            subprocess.run(
                ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", state],
                timeout=2, check=True,
            )
        except Exception as e:
            log.warning("set_mute failed: %s", e)

    def toggle_mute(self):
        try:
            subprocess.run(
                ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
                timeout=2, check=True,
            )
        except Exception as e:
            log.warning("toggle_mute failed: %s", e)
