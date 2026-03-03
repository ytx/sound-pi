"""Mixer screen — input/output volume control (placeholder)."""

import pygame

from screens.base import Screen
from ui.widgets import (BLACK, WHITE, GRAY, GREEN, DARK_GRAY,
                        draw_text, draw_bar, draw_button)


class MixerScreen(Screen):
    name = "mixer"

    def __init__(self, pipewire_mgr):
        self._pw = pipewire_mgr
        self._volume = 80

    def on_enter(self):
        self._volume = self._pw.get_volume()

    def draw(self, surface: pygame.Surface):
        surface.fill(BLACK)
        draw_text(surface, "MIXER", 240, 15, WHITE, 24, center=True)

        # Master volume
        draw_text(surface, "Master", 30, 70, WHITE, 18)
        draw_bar(surface, 120, 70, 300, 20, self._volume / 100.0, GREEN)
        draw_text(surface, f"{self._volume}%", 430, 70, WHITE, 18)

        draw_text(surface, "Tap +/- to adjust", 240, 180, GRAY, 14, center=True)

        # +/- buttons
        draw_button(surface, 140, 220, 80, 50, "  -  ")
        draw_button(surface, 260, 220, 80, 50, "  +  ")

    def on_touch(self, x: int, y: int, event_type: str):
        if event_type != "down":
            return
        if 140 <= x <= 220 and 220 <= y <= 270:
            self._volume = max(0, self._volume - 5)
            self._pw.set_volume(self._volume)
        elif 260 <= x <= 340 and 220 <= y <= 270:
            self._volume = min(100, self._volume + 5)
            self._pw.set_volume(self._volume)
