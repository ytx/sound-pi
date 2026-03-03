"""Framebuffer display manager.

Detects ili9486 SPI LCD via sysfs, mmaps /dev/fbN for direct writes.
Falls back to a normal pygame window on dev machines without the LCD.
"""

import os
import mmap
from pathlib import Path

import pygame

from logger import get_logger

log = get_logger("display")

WIDTH, HEIGHT = 480, 320
BPP = 4  # 32bpp BGRX
STRIDE = WIDTH * BPP
FB_SIZE = STRIDE * HEIGHT


def _find_ili9486_fb() -> str | None:
    """Search sysfs for an ili9486 framebuffer device."""
    fb_base = Path("/sys/class/graphics")
    if not fb_base.exists():
        return None
    for fb_dir in sorted(fb_base.iterdir()):
        name_file = fb_dir / "name"
        if name_file.exists():
            name = name_file.read_text().strip()
            if "ili9486" in name.lower():
                dev = f"/dev/{fb_dir.name}"
                log.info("found ili9486 fb: %s (%s)", dev, name)
                return dev
    return None


class Display:
    """Manages pygame surface and optional fbdev output."""

    def __init__(self):
        self._fb_fd = None
        self._fb_map: mmap.mmap | None = None
        self._use_fbdev = False
        self.surface: pygame.Surface | None = None

        fb_dev = _find_ili9486_fb()
        if fb_dev and os.path.exists(fb_dev):
            try:
                self._fb_fd = os.open(fb_dev, os.O_RDWR)
                self._fb_map = mmap.mmap(self._fb_fd, FB_SIZE)
                self._use_fbdev = True
                log.info("fbdev mode: %s", fb_dev)
            except Exception as e:
                log.warning("fbdev open failed: %s — falling back to window", e)
                self._use_fbdev = False

        if self._use_fbdev:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            pygame.display.init()
            pygame.display.set_mode((1, 1))
            self.surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA, 32)
            self._hide_vt_cursor()
        else:
            pygame.display.init()
            self.surface = pygame.display.set_mode((WIDTH, HEIGHT))
            pygame.display.set_caption("Sound-Pi")
            log.info("window mode: %dx%d", WIDTH, HEIGHT)

    def flip(self):
        """Push the current surface to the display."""
        if self._use_fbdev:
            raw = self.surface.get_buffer().raw
            self._fb_map.seek(0)
            self._fb_map.write(raw)
        else:
            pygame.display.flip()

    def _hide_vt_cursor(self):
        """Disable the VT console cursor so it doesn't blink over the framebuffer."""
        import subprocess
        # setterm to hide cursor on tty1
        try:
            subprocess.run(
                ["sudo", "setterm", "--cursor", "off", "--term", "linux"],
                stdin=open("/dev/tty1"), stdout=open("/dev/tty1", "w"),
                timeout=2)
        except Exception:
            pass
        # Disable fbcon cursor blink (requires root)
        try:
            subprocess.run(
                ["sudo", "sh", "-c", "echo 0 > /sys/class/graphics/fbcon/cursor_blink"],
                timeout=2)
        except Exception:
            pass
        # Clear tty1 screen
        try:
            subprocess.run(
                ["sudo", "sh", "-c", "echo -ne '\\033[2J' > /dev/tty1"],
                timeout=2)
        except Exception:
            pass
        log.info("VT cursor hidden")

    def _restore_vt_cursor(self):
        """Re-enable the VT console cursor."""
        import subprocess
        try:
            subprocess.run(
                ["sudo", "setterm", "--cursor", "on", "--term", "linux"],
                stdin=open("/dev/tty1"), stdout=open("/dev/tty1", "w"),
                timeout=2)
        except Exception:
            pass
        try:
            subprocess.run(
                ["sudo", "sh", "-c", "echo 1 > /sys/class/graphics/fbcon/cursor_blink"],
                timeout=2)
        except Exception:
            pass

    def close(self):
        if self._use_fbdev:
            self._restore_vt_cursor()
        if self._fb_map:
            self._fb_map.close()
        if self._fb_fd is not None:
            os.close(self._fb_fd)
            self._fb_fd = None
        log.info("display closed")
