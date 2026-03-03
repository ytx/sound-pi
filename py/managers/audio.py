"""PipeWire audio manager and capture."""

import subprocess
import threading
import struct
import math

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

    def start(self):
        """Start capturing audio."""
        if self._running:
            return
        self._running = True

        try:
            self._proc = subprocess.Popen(
                [
                    "pw-cat", "--record", "--format", "s16",
                    "--rate", str(SAMPLE_RATE),
                    "--channels", str(CHANNELS),
                    "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            self._thread = threading.Thread(target=self._read_loop, daemon=True)
            self._thread.start()
            log.info("pw-cat capture started")
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
    """Control PipeWire via wpctl."""

    def get_volume(self) -> int:
        """Get current master volume as 0-100."""
        try:
            out = subprocess.check_output(
                ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                timeout=2, text=True,
            )
            # "Volume: 0.80" or "Volume: 0.80 [MUTED]"
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
