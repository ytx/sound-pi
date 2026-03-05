"""Output control screen — multi-device routing with per-device volume."""

from dataclasses import dataclass

import pygame

import config as cfg
from config import persist as persist_config
from logger import get_logger
from screens.base import Screen
from ui.widgets import (BLACK, WHITE, GRAY, DARK_GRAY, CYAN, RED,
                        draw_text, draw_vslider)

log = get_logger("mixer")

MAX_SLOTS = 4

# Layout constants
SLOT_WIDTH = 100
SLOT_X_START = 10
SLOT_X_GAP = 110  # 10 + 100
HEADER_Y = 16
NICK_Y = 46
SLIDER_Y = 68
SLIDER_H = 150
SLIDER_W = 40
PERCENT_Y = 224
MUTE_Y = 246
REMOVE_Y = 272
# Add-device overlay
OVERLAY_X = 40
OVERLAY_Y = 40
OVERLAY_W = 400
OVERLAY_ROW_H = 50


@dataclass
class OutputSlot:
    node_name: str | None = None
    nick: str = ""
    wpctl_id: int | None = None
    volume: float = 0.8
    muted: bool = False
    _pw_device_name: str = ""
    _card_name: str = ""


class MixerScreen(Screen):
    name = "mixer"

    def __init__(self, pipewire_mgr):
        self._pw = pipewire_mgr
        self._slots: list[OutputSlot] = [OutputSlot() for _ in range(MAX_SLOTS)]
        self._selected: int = 0
        self._adding: bool = False
        self._available_sinks: list[dict] = []
        self._dragging_slot: int | None = None

    def on_enter(self):
        """Load config and resolve wpctl IDs."""
        devices = cfg.get("output_devices", [])
        for i in range(MAX_SLOTS):
            if i < len(devices):
                d = devices[i]
                self._slots[i].node_name = d.get("node_name")
                self._slots[i].volume = d.get("volume", 0.8)
                self._slots[i].muted = d.get("muted", False)
                self._slots[i]._pw_device_name = d.get("pw_device_name", "")
                self._slots[i]._card_name = d.get("card_name", "")
            else:
                self._slots[i] = OutputSlot()
        self._resolve_ids()

    def _resolve_ids(self):
        """Resolve node_name → wpctl_id for all active slots.
        If sink not found, try finding by pw_device_name (handles node_name changes).
        """
        config_changed = False
        for slot in self._slots:
            if not slot.node_name:
                continue
            wpctl_id = self._pw.resolve_node_name(slot.node_name)
            if not wpctl_id and slot._pw_device_name:
                # Sink missing — find by device name (node_name may have changed)
                pw_devs = self._pw.list_pw_audio_devices()
                for d in pw_devs:
                    if d["device_name"] == slot._pw_device_name:
                        node_name = self._pw.ensure_sink_profile(d["id"])
                        if node_name and node_name != slot.node_name:
                            old = slot.node_name
                            slot.node_name = node_name
                            config_changed = True
                            # Update routing if active
                            self._pw.remove_route(old)
                            self._pw.add_route(node_name)
                            log.info("node_name updated: %s → %s", old, node_name)
                        wpctl_id = self._pw.resolve_node_name(node_name) if node_name else None
                        break
            slot.wpctl_id = wpctl_id
            if wpctl_id:
                for s in self._pw._sinks_cache:
                    if s["node_name"] == slot.node_name:
                        slot.nick = s.get("nick") or s.get("description", "")[:10]
                        break
            else:
                slot.nick = "(offline)"
        if config_changed:
            self.save_config()
            persist_config()

    def save_config(self):
        """Persist current slot config."""
        devices = []
        for slot in self._slots:
            if slot.node_name:
                devices.append({
                    "node_name": slot.node_name,
                    "pw_device_name": slot._pw_device_name,
                    "card_name": slot._card_name,
                    "volume": round(slot.volume, 2),
                    "muted": slot.muted,
                })
        cfg.set("output_devices", devices)

    def get_selected_slot(self) -> OutputSlot | None:
        """Return the selected slot if it has an active device."""
        slot = self._slots[self._selected]
        if slot.node_name and slot.wpctl_id:
            return slot
        return None

    # ── Drawing ──

    def draw(self, surface: pygame.Surface):
        surface.fill(BLACK)

        if self._adding:
            self._draw_add_overlay(surface)
            return

        # Header
        draw_text(surface, "OUTPUT CONTROL", 200, HEADER_Y, WHITE, 20, center=True)

        # Slots
        for i in range(MAX_SLOTS):
            self._draw_slot(surface, i)

    def _draw_slot(self, surface: pygame.Surface, idx: int):
        slot = self._slots[idx]
        x = SLOT_X_START + idx * SLOT_X_GAP
        is_selected = (idx == self._selected)
        border_color = CYAN if is_selected else GRAY

        # Slot border
        pygame.draw.rect(surface, border_color,
                         (x - 2, NICK_Y - 4, SLOT_WIDTH + 4, 280), 1, border_radius=4)

        if not slot.node_name:
            # Empty slot — show "+" to indicate tappable
            draw_text(surface, "+", x + SLOT_WIDTH // 2, SLIDER_Y + SLIDER_H // 2,
                      GRAY, 28, center=True)
            return

        # Nick (truncated)
        nick = slot.nick[:8] if slot.nick else "?"
        draw_text(surface, nick, x + SLOT_WIDTH // 2, NICK_Y + 2,
                  CYAN if is_selected else WHITE, 13, center=True)

        # Vertical slider
        slider_x = x + (SLOT_WIDTH - SLIDER_W) // 2
        draw_vslider(surface, slider_x, SLIDER_Y, SLIDER_W, SLIDER_H,
                     slot.volume, muted=slot.muted)

        # Percentage
        pct = f"{int(slot.volume * 100)}%"
        draw_text(surface, pct, x + SLOT_WIDTH // 2, PERCENT_Y,
                  GRAY if slot.muted else WHITE, 14, center=True)

        # Mute button
        mute_color = RED if slot.muted else GRAY
        pygame.draw.rect(surface, mute_color, (x + 20, MUTE_Y, 60, 20), border_radius=3)
        draw_text(surface, "M", x + SLOT_WIDTH // 2, MUTE_Y + 10, WHITE, 14, center=True)

        # Remove button
        pygame.draw.rect(surface, DARK_GRAY, (x + 20, REMOVE_Y, 60, 16), border_radius=3)
        draw_text(surface, "x", x + SLOT_WIDTH // 2, REMOVE_Y + 8, RED, 13, center=True)

    def _draw_add_overlay(self, surface: pygame.Surface):
        """Draw the device-add overlay."""
        # Background dim
        dim = pygame.Surface((480, 320), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 180))
        surface.blit(dim, (0, 0))

        # Panel
        n = len(self._available_sinks)
        h = max(80, OVERLAY_ROW_H * n + 50)
        pygame.draw.rect(surface, DARK_GRAY, (OVERLAY_X, OVERLAY_Y, OVERLAY_W, h), border_radius=8)
        pygame.draw.rect(surface, CYAN, (OVERLAY_X, OVERLAY_Y, OVERLAY_W, h), 1, border_radius=8)

        draw_text(surface, "Add Output Device", OVERLAY_X + OVERLAY_W // 2, OVERLAY_Y + 14,
                  WHITE, 16, center=True)

        if not self._available_sinks:
            draw_text(surface, "No available devices", OVERLAY_X + OVERLAY_W // 2, OVERLAY_Y + 50,
                      GRAY, 14, center=True)
        else:
            for i, dev in enumerate(self._available_sinks):
                y = OVERLAY_Y + 36 + i * OVERLAY_ROW_H
                label = dev.get("long_name", dev.get("card_name", "?"))[:30]
                row_h = OVERLAY_ROW_H - 6
                pygame.draw.rect(surface, (60, 60, 60), (OVERLAY_X + 10, y, OVERLAY_W - 20, row_h),
                                 border_radius=6)
                draw_text(surface, label, OVERLAY_X + OVERLAY_W // 2, y + row_h // 2, WHITE, 16, center=True)

    # ── Touch handling ──

    def on_touch(self, x: int, y: int, event_type: str):
        if self._adding:
            if event_type == "down":
                self._handle_add_touch(x, y)
            return

        if event_type == "down":
            self._dragging_slot = None

            # Per-slot touches
            for i in range(MAX_SLOTS):
                sx = SLOT_X_START + i * SLOT_X_GAP
                if sx - 2 <= x <= sx + SLOT_WIDTH + 2:
                    slot = self._slots[i]
                    if not slot.node_name:
                        # Empty slot tapped → open add overlay
                        self._selected = i
                        self._open_add_overlay()
                        return

                    # Mute button
                    if sx + 20 <= x <= sx + 80 and MUTE_Y <= y <= MUTE_Y + 20:
                        slot.muted = not slot.muted
                        if slot.wpctl_id:
                            self._pw.set_sink_mute(slot.wpctl_id, slot.muted)
                        self.save_config()
                        return

                    # Remove button
                    if sx + 20 <= x <= sx + 80 and REMOVE_Y <= y <= REMOVE_Y + 16:
                        self._remove_device(i)
                        return

                    # Slider area — start drag
                    slider_x = sx + (SLOT_WIDTH - SLIDER_W) // 2
                    if slider_x <= x <= slider_x + SLIDER_W and SLIDER_Y <= y <= SLIDER_Y + SLIDER_H:
                        self._selected = i
                        self._dragging_slot = i
                        self._apply_slider_touch(i, y)
                        return

                    # Anywhere else in slot → select
                    self._selected = i
                    return

        elif event_type == "move":
            if self._dragging_slot is not None:
                self._apply_slider_touch(self._dragging_slot, y)

        elif event_type == "up":
            self._dragging_slot = None

    def _apply_slider_touch(self, idx: int, y: int):
        """Map touch y to volume and apply."""
        slot = self._slots[idx]
        if not slot.node_name:
            return
        # y=SLIDER_Y → volume 1.0, y=SLIDER_Y+SLIDER_H → volume 0.0
        ratio = 1.0 - (y - SLIDER_Y) / SLIDER_H
        slot.volume = max(0.0, min(1.0, ratio))
        if slot.wpctl_id:
            self._pw.set_sink_volume(slot.wpctl_id, slot.volume)
        self.save_config()

    def _handle_add_touch(self, x: int, y: int):
        """Handle touch inside add-device overlay."""
        n = len(self._available_sinks)
        h = max(80, OVERLAY_ROW_H * n + 50)
        if not (OVERLAY_X <= x <= OVERLAY_X + OVERLAY_W and OVERLAY_Y <= y <= OVERLAY_Y + h):
            self._adding = False
            return

        # Check which row was tapped
        for i, sink in enumerate(self._available_sinks):
            row_y = OVERLAY_Y + 36 + i * OVERLAY_ROW_H
            if row_y <= y <= row_y + OVERLAY_ROW_H:
                self._add_device(sink)
                self._adding = False
                return

    def _open_add_overlay(self):
        """Show the add-device overlay with ALSA playback devices."""
        all_devs = self._pw.list_addable_devices()
        # Filter out already-added devices
        used = {s._pw_device_name for s in self._slots if s.node_name and s._pw_device_name}
        self._available_sinks = [d for d in all_devs if d["pw_device_name"] not in used]
        self._adding = True

    def _add_device(self, dev: dict):
        """Add a device: ensure sink profile, resolve sink, start routing."""
        slot = self._slots[self._selected]
        if slot.node_name is not None:
            log.warning("slot %d not empty", self._selected)
            return

        pw_device_id = dev["pw_device_id"]
        pw_device_name = dev["pw_device_name"]
        nick = dev["long_name"]
        is_bluez = dev.get("is_bluez", False)

        if is_bluez:
            # BT sinks are already active — use pw_device_name as node_name
            node_name = pw_device_name
        else:
            # Ensure the device has an Audio/Sink (switch profile if needed)
            node_name = self._pw.ensure_sink_profile(pw_device_id)
            if not node_name:
                log.warning("failed to get sink for device %s", nick)
                return

        # Resolve wpctl ID
        wpctl_id = self._pw.resolve_node_name(node_name)

        slot.node_name = node_name
        slot.nick = nick[:10]
        slot.wpctl_id = wpctl_id
        slot.volume = 0.8
        slot.muted = False
        slot._pw_device_name = pw_device_name
        slot._card_name = dev.get("card_name", "")

        self._pw.add_route(node_name, card_name=slot._card_name,
                           pw_device_name=pw_device_name)
        if slot.wpctl_id:
            self._pw.set_sink_volume(slot.wpctl_id, slot.volume)
        self.save_config()
        persist_config()
        log.info("added output: %s (%s) → slot %d", nick, node_name, self._selected)

    def _remove_device(self, idx: int):
        """Remove a device from a slot."""
        slot = self._slots[idx]
        if slot.node_name:
            self._pw.remove_route(slot.node_name)
            log.info("removed output: %s from slot %d", slot.node_name, idx)
        self._slots[idx] = OutputSlot()
        self.save_config()
        persist_config()
