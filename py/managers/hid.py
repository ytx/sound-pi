"""USB HID Consumer Control output via /dev/hidg0."""

import os
from logger import get_logger

log = get_logger("hid")

HID_DEVICE = "/dev/hidg0"

# Consumer Control usage IDs (2 bytes, little-endian)
KEY_PLAY_PAUSE = b"\xcd\x00"
KEY_NEXT = b"\xb5\x00"
KEY_PREV = b"\xb6\x00"
KEY_VOLUME_UP = b"\xe9\x00"
KEY_VOLUME_DOWN = b"\xea\x00"
KEY_MUTE = b"\xe2\x00"
KEY_RELEASE = b"\x00\x00"


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

    def _send(self, key: bytes):
        if self._stub:
            log.debug("stub HID: %s", key.hex())
            return
        try:
            os.write(self._fd, key)
            os.write(self._fd, KEY_RELEASE)
        except Exception as e:
            log.warning("HID write failed: %s", e)

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
