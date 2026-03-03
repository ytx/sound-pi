"""WiFi settings screen (placeholder)."""

import pygame

from screens.base import Screen
from ui.widgets import BLACK, WHITE, GRAY, draw_text


class WifiSettingsScreen(Screen):
    name = "wifi_settings"

    def draw(self, surface: pygame.Surface):
        surface.fill(BLACK)
        draw_text(surface, "WIFI", 240, 15, WHITE, 24, center=True)
        draw_text(surface, "Coming soon", 240, 160, GRAY, 18, center=True)
