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
        # Method 1: ANSI escape to hide cursor on current tty
        try:
            with open("/dev/tty0", "w") as tty:
                tty.write("\033[?25l")  # hide cursor
                tty.write("\033[2J")    # clear screen
        except Exception:
            pass
        # Method 2: Disable fbcon cursor blink globally
        try:
            Path("/sys/class/graphics/fbcon/cursor_blink").write_text("0")
        except Exception:
            pass
        log.info("VT cursor hidden")

    def _restore_vt_cursor(self):
        """Re-enable the VT console cursor."""
        try:
            with open("/dev/tty0", "w") as tty:
                tty.write("\033[?25h")
        except Exception:
            pass
        try:
            Path("/sys/class/graphics/fbcon/cursor_blink").write_text("1")
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
