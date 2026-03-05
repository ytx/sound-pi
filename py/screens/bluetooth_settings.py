"""Bluetooth settings screen — scan, pair, connect, disconnect BT devices."""

import re
import threading

import pygame

from logger import get_logger
from managers.bluetooth import BluetoothManager, BTDevice
from screens.base import Screen
from touch import TOUCH_DOWN
from ui.widgets import (BLACK, WHITE, GRAY, DARK_GRAY, GREEN, CYAN, RED, BLUE,
                        draw_text)

log = get_logger("bt_screen")

ROW_HEIGHT = 42
SECTION_HEIGHT = 24
LIST_Y = 42
LIST_BOTTOM = 310
MAX_VISIBLE = (LIST_BOTTOM - LIST_Y) // ROW_HEIGHT  # 6 rows

BTN_X = 370
BTN_W = 90
BTN_H = 28
DEL_W = 28

_MAC_RE = re.compile(r'^([0-9A-F]{2}[:-]){2,5}[0-9A-F]{2}$', re.IGNORECASE)


def _is_addr_only(name: str) -> bool:
    """True if the name looks like a MAC address (no useful name)."""
    return bool(_MAC_RE.match(name.strip()))


class BluetoothSettingsScreen(Screen):
    name = "bluetooth_settings"

    def __init__(self, bt: BluetoothManager):
        self._bt = bt
        self._devices: list[BTDevice] = []
        self._scroll_offset: int = 0
        self._status_msg: str = ""
        self._status_timer: float = 0
        self._busy: bool = False
        self._refresh_timer: float = 0

    def on_enter(self):
        self._bt.refresh_devices()
        self._devices = self._bt.get_devices()

    def on_exit(self):
        self._bt.scan_stop()

    def update(self, dt: float):
        # Status message auto-clear
        if self._status_timer > 0:
            self._status_timer -= dt
            if self._status_timer <= 0:
                self._status_msg = ""

        # Refresh device list periodically during scan
        self._refresh_timer -= dt
        if self._refresh_timer <= 0:
            self._refresh_timer = 2.0
            self._devices = self._bt.get_devices()

    # ── Drawing ──

    def draw(self, surface: pygame.Surface):
        surface.fill(BLACK)

        # Header
        draw_text(surface, "BLUETOOTH", 200, 15, WHITE, 20, center=True)

        # Scan button (below menu region y=100)
        scanning = self._bt.is_scanning
        scan_label = "Stop" if scanning else "Scan"
        scan_color = RED if scanning else BLUE
        pygame.draw.rect(surface, scan_color, (380, 104, 90, 30), border_radius=6)
        draw_text(surface, scan_label, 425, 119, WHITE, 16, center=True)

        # Split devices into paired and discovered
        paired = [d for d in self._devices if d.paired]
        discovered = [d for d in self._devices if not d.paired]

        # Sort: connected first within paired
        paired.sort(key=lambda d: (not d.connected, d.name))
        discovered.sort(key=lambda d: (_is_addr_only(d.name), d.name))

        # Build row list: (section_header | device)
        rows: list[tuple[str, BTDevice | None]] = []
        if paired:
            rows.append(("Paired", None))
            for d in paired:
                rows.append(("", d))
        if discovered:
            rows.append(("Discovered", None))
            for d in discovered:
                rows.append(("", d))

        if not rows:
            msg = "Scanning..." if scanning else "No devices found"
            draw_text(surface, msg, 240, 160, GRAY, 16, center=True)

        # Draw visible rows
        y = LIST_Y
        for i, (header, dev) in enumerate(rows):
            if i < self._scroll_offset:
                continue
            if y + ROW_HEIGHT > LIST_BOTTOM:
                break

            if header:
                # Section header
                draw_text(surface, f"-- {header} --", 10, y + 4, GRAY, 13)
                y += SECTION_HEIGHT
                continue

            self._draw_device_row(surface, dev, y)
            y += ROW_HEIGHT

        # Status message
        if self._status_msg:
            draw_text(surface, self._status_msg, 240, 306, CYAN, 14, center=True)

    def _draw_device_row(self, surface: pygame.Surface, dev: BTDevice, y: int):
        # Status dot
        if dev.connected:
            dot_color = GREEN
        elif dev.paired:
            dot_color = CYAN
        else:
            dot_color = WHITE
        pygame.draw.circle(surface, dot_color, (16, y + ROW_HEIGHT // 2), 5)

        # Device name (truncated)
        name = dev.name[:20]
        draw_text(surface, name, 28, y + 4, WHITE, 15)

        # Status text
        if dev.connected:
            status = "Connected"
            status_color = GREEN
        elif dev.paired:
            status = "Paired"
            status_color = CYAN
        else:
            status = "Found"
            status_color = GRAY
        draw_text(surface, status, 28, y + 22, status_color, 12)

        # Action button
        if dev.connected:
            btn_label = "Discon"
            btn_color = RED
        elif dev.paired:
            btn_label = "Connect"
            btn_color = CYAN
        else:
            btn_label = "Pair"
            btn_color = BLUE

        btn_x = BTN_X
        btn_y = y + (ROW_HEIGHT - BTN_H) // 2

        # Delete button for paired + not connected
        if dev.paired and not dev.connected:
            del_x = BTN_X + BTN_W + 4
            pygame.draw.rect(surface, DARK_GRAY, (del_x, btn_y, DEL_W, BTN_H), border_radius=4)
            pygame.draw.rect(surface, RED, (del_x, btn_y, DEL_W, BTN_H), 1, border_radius=4)
            draw_text(surface, "x", del_x + DEL_W // 2, btn_y + BTN_H // 2, RED, 14, center=True)
            # Shift action button left to make room
            btn_x = BTN_X - 4

        pygame.draw.rect(surface, btn_color, (btn_x, btn_y, BTN_W, BTN_H), border_radius=6)
        draw_text(surface, btn_label, btn_x + BTN_W // 2, btn_y + BTN_H // 2,
                  WHITE, 14, center=True)

    # ── Touch handling ──

    def on_touch(self, x: int, y: int, event_type: str):
        if event_type != TOUCH_DOWN or self._busy:
            return

        # Scan button
        if 380 <= x <= 470 and 104 <= y <= 134:
            if self._bt.is_scanning:
                self._bt.scan_stop()
            else:
                self._bt.scan_start()
            return

        # Device rows
        paired = [d for d in self._devices if d.paired]
        discovered = [d for d in self._devices if not d.paired]
        paired.sort(key=lambda d: (not d.connected, d.name))
        discovered.sort(key=lambda d: (_is_addr_only(d.name), d.name))

        rows: list[tuple[str, BTDevice | None]] = []
        if paired:
            rows.append(("Paired", None))
            for d in paired:
                rows.append(("", d))
        if discovered:
            rows.append(("Discovered", None))
            for d in discovered:
                rows.append(("", d))

        # Find which row was tapped
        row_y = LIST_Y
        for i, (header, dev) in enumerate(rows):
            if i < self._scroll_offset:
                continue
            if row_y + ROW_HEIGHT > LIST_BOTTOM:
                break

            if header:
                row_y += SECTION_HEIGHT
                continue

            if row_y <= y <= row_y + ROW_HEIGHT and dev:
                btn_y_pos = row_y + (ROW_HEIGHT - BTN_H) // 2

                # Delete button (paired + not connected)
                if dev.paired and not dev.connected:
                    del_x = BTN_X + BTN_W + 4
                    if del_x <= x <= del_x + DEL_W and btn_y_pos <= y <= btn_y_pos + BTN_H:
                        self._do_action(dev, "remove")
                        return

                # Action button
                btn_x = BTN_X - 4 if (dev.paired and not dev.connected) else BTN_X
                if btn_x <= x <= btn_x + BTN_W and btn_y_pos <= y <= btn_y_pos + BTN_H:
                    if dev.connected:
                        self._do_action(dev, "disconnect")
                    elif dev.paired:
                        self._do_action(dev, "connect")
                    else:
                        self._do_action(dev, "pair")
                    return

            row_y += ROW_HEIGHT

    def _do_action(self, dev: BTDevice, action: str):
        self._busy = True
        label = {"pair": "Pairing", "connect": "Connecting",
                 "disconnect": "Disconnecting", "remove": "Removing"}
        self._status_msg = f"{label.get(action, action)}..."
        self._status_timer = 30  # will be replaced on completion

        def worker():
            try:
                if action == "pair":
                    ok, msg = self._bt.pair(dev.address)
                    if ok:
                        ok2, msg2 = self._bt.connect(dev.address)
                        msg = msg2 if ok2 else f"Paired, connect failed: {msg2}"
                elif action == "connect":
                    ok, msg = self._bt.connect(dev.address)
                elif action == "disconnect":
                    ok, msg = self._bt.disconnect(dev.address)
                elif action == "remove":
                    ok, msg = self._bt.remove(dev.address)
                else:
                    msg = "Unknown action"

                self._status_msg = msg
                self._status_timer = 3.0
                self._devices = self._bt.get_devices()
            except Exception as e:
                self._status_msg = str(e)
                self._status_timer = 3.0
            finally:
                self._busy = False

        threading.Thread(target=worker, daemon=True).start()
