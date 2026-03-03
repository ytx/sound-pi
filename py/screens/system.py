"""System information screen."""

import os
import socket
import subprocess
import time

import pygame

from screens.base import Screen
from ui.widgets import (BLACK, WHITE, GRAY, CYAN, RED, ORANGE,
                        draw_text, draw_button, draw_bar)
from logger import get_logger

log = get_logger("system")

def _find_app_dir():
    """Find the application root directory (parent of screens/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP_DIR = _find_app_dir()

CONFIRM_TIMEOUT = 2.0  # seconds to confirm reboot/shutdown


class SystemScreen(Screen):
    name = "system"

    def __init__(self):
        self._hostname = socket.gethostname()
        self._git_branch = ""
        self._mem_available_mb = 0
        self._mem_total_mb = 0
        self._cpu_percent = 0.0
        self._disk_used_pct = 0.0
        self._disk_total_gb = 0.0
        self._disk_used_gb = 0.0

        # CPU calculation state
        self._prev_idle = 0
        self._prev_total = 0

        # Update timer
        self._update_timer = 0.0

        # Confirm state for reboot/shutdown
        self._confirm_action: str | None = None  # "reboot" or "shutdown"
        self._confirm_time = 0.0

        # Button rects (set in draw)
        self._btn_reboot = pygame.Rect(290, 230, 160, 36)
        self._btn_shutdown = pygame.Rect(290, 274, 160, 36)

    def on_enter(self):
        self._refresh_info()

    def _refresh_info(self):
        # Git branch: try VERSION file first, then git command
        self._git_branch = "?"
        version_file = os.path.join(APP_DIR, "VERSION")
        if os.path.exists(version_file):
            try:
                self._git_branch = open(version_file).read().strip()
            except Exception:
                pass
        if self._git_branch == "?":
            try:
                result = subprocess.run(
                    ["git", "-C", APP_DIR, "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    self._git_branch = result.stdout.strip()
            except Exception:
                pass

        # Memory from /proc/meminfo
        try:
            with open("/proc/meminfo") as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        meminfo[parts[0].rstrip(":")] = int(parts[1])
            self._mem_total_mb = meminfo.get("MemTotal", 0) // 1024
            self._mem_available_mb = meminfo.get("MemAvailable", 0) // 1024
        except Exception:
            pass

        # CPU from /proc/stat
        try:
            with open("/proc/stat") as f:
                line = f.readline()
            fields = [int(x) for x in line.split()[1:]]
            idle = fields[3]
            total = sum(fields)
            if self._prev_total > 0:
                d_total = total - self._prev_total
                d_idle = idle - self._prev_idle
                self._cpu_percent = (1.0 - d_idle / max(d_total, 1)) * 100.0
            self._prev_idle = idle
            self._prev_total = total
        except Exception:
            pass

        # Disk
        try:
            st = os.statvfs("/")
            total_bytes = st.f_blocks * st.f_frsize
            free_bytes = st.f_bfree * st.f_frsize
            used_bytes = total_bytes - free_bytes
            self._disk_total_gb = total_bytes / (1024 ** 3)
            self._disk_used_gb = used_bytes / (1024 ** 3)
            self._disk_used_pct = used_bytes / max(total_bytes, 1) * 100.0
        except Exception:
            pass

    def update(self, dt: float):
        self._update_timer += dt
        if self._update_timer >= 1.0:
            self._update_timer = 0.0
            self._refresh_info()

        # Expire confirm
        if self._confirm_action and (time.monotonic() - self._confirm_time) > CONFIRM_TIMEOUT:
            self._confirm_action = None

    def draw(self, surface: pygame.Surface):
        surface.fill(BLACK)
        draw_text(surface, "System", 240, 16, WHITE, 24, center=True)

        y = 48
        gap = 28

        # Info rows
        draw_text(surface, f"Host:   {self._hostname}", 20, y, WHITE, 16)
        y += gap
        draw_text(surface, f"Branch: {self._git_branch}", 20, y, WHITE, 16)
        y += gap

        mem_pct = (1.0 - self._mem_available_mb / max(self._mem_total_mb, 1)) * 100
        draw_text(surface, f"Memory: {self._mem_available_mb} / {self._mem_total_mb} MB free", 20, y, WHITE, 16)
        y += gap - 4
        draw_bar(surface, 20, y, 240, 12, mem_pct / 100.0,
                 color=ORANGE if mem_pct > 80 else CYAN)
        y += gap

        draw_text(surface, f"CPU:    {self._cpu_percent:.1f}%", 20, y, WHITE, 16)
        y += gap - 4
        draw_bar(surface, 20, y, 240, 12, self._cpu_percent / 100.0,
                 color=RED if self._cpu_percent > 80 else CYAN)
        y += gap

        draw_text(surface, f"Disk:   {self._disk_used_gb:.1f} / {self._disk_total_gb:.1f} GB "
                  f"({self._disk_used_pct:.0f}%)", 20, y, WHITE, 16)
        y += gap - 4
        draw_bar(surface, 20, y, 240, 12, self._disk_used_pct / 100.0,
                 color=RED if self._disk_used_pct > 90 else CYAN)

        # Buttons
        is_reboot_confirm = self._confirm_action == "reboot"
        is_shutdown_confirm = self._confirm_action == "shutdown"

        reboot_label = "Tap again to Reboot" if is_reboot_confirm else "Reboot"
        shutdown_label = "Tap again to Shutdown" if is_shutdown_confirm else "Shutdown"

        r = self._btn_reboot
        color = ORANGE if is_reboot_confirm else GRAY
        pygame.draw.rect(surface, color, r, border_radius=6)
        pygame.draw.rect(surface, WHITE, r, 1, border_radius=6)
        draw_text(surface, reboot_label, r.centerx, r.centery, WHITE,
                  13 if is_reboot_confirm else 16, center=True)

        r = self._btn_shutdown
        color = RED if is_shutdown_confirm else GRAY
        pygame.draw.rect(surface, color, r, border_radius=6)
        pygame.draw.rect(surface, WHITE, r, 1, border_radius=6)
        draw_text(surface, shutdown_label, r.centerx, r.centery, WHITE,
                  13 if is_shutdown_confirm else 16, center=True)

    def on_touch(self, x: int, y: int, event_type: str):
        if event_type != "down":
            return

        now = time.monotonic()

        if self._btn_reboot.collidepoint(x, y):
            if self._confirm_action == "reboot" and (now - self._confirm_time) <= CONFIRM_TIMEOUT:
                log.info("reboot confirmed")
                subprocess.Popen(["sudo", "reboot"])
            else:
                self._confirm_action = "reboot"
                self._confirm_time = now
            return

        if self._btn_shutdown.collidepoint(x, y):
            if self._confirm_action == "shutdown" and (now - self._confirm_time) <= CONFIRM_TIMEOUT:
                log.info("shutdown confirmed")
                subprocess.Popen(["sudo", "shutdown", "-h", "now"])
            else:
                self._confirm_action = "shutdown"
                self._confirm_time = now
            return

        # Tap elsewhere clears confirm
        self._confirm_action = None
