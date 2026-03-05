"""USB HID Consumer Control output via /dev/hidg0.

Report descriptor (1-byte bitmap):
  bit 0: Play/Pause
  bit 1: Scan Next Track
  bit 2: Scan Previous Track
  bits 3-7: padding (const)
"""

import os
import time
from logger import get_logger

log = get_logger("hid")

HID_DEVICE = "/dev/hidg0"

# 1-byte bitmap reports matching the gadget report descriptor
KEY_PLAY_PAUSE = b"\x01"   # bit 0
KEY_NEXT = b"\x02"         # bit 1
KEY_PREV = b"\x04"         # bit 2
KEY_RELEASE = b"\x00"

# Max retries for EAGAIN on non-blocking write
_WRITE_RETRIES = 3
_WRITE_RETRY_DELAY = 0.005  # 5ms


class HidController:
    """Send USB HID Consumer Control key events."""

    def __init__(self):
        self._fd = None
        self._stub = False

        if os.path.exists(HID_DEVICE):
            try:
                self._fd = os.open(HID_DEVICE, os.O_WRONLY | os.O_NONBLOCK)
                log.info("HID device opened: %s", HID_DEVICE)
            except Exception as e:
                log.warning("HID open failed: %s — stub mode", e)
                self._stub = True
        else:
            log.info("HID device not found — stub mode")
            self._stub = True

    def _write_retry(self, data: bytes):
        """Write to HID fd, retrying on EAGAIN."""
        for i in range(_WRITE_RETRIES):
            try:
                os.write(self._fd, data)
                return True
            except BlockingIOError:
                time.sleep(_WRITE_RETRY_DELAY)
            except Exception as e:
                log.warning("HID write failed: %s", e)
                return False
        log.warning("HID write failed: EAGAIN after %d retries", _WRITE_RETRIES)
        return False

    def _send(self, key: bytes):
        if self._stub:
            log.debug("stub HID: %s", key.hex())
            return
        if self._write_retry(key):
            time.sleep(_WRITE_RETRY_DELAY)
            self._write_retry(KEY_RELEASE)

    def play_pause(self):
        self._send(KEY_PLAY_PAUSE)

    def next_track(self):
        self._send(KEY_NEXT)

    def prev_track(self):
        self._send(KEY_PREV)

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        log.info("HID closed")
