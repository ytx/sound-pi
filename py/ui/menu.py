"""3x2 tile menu overlay."""

import pygame

from ui.widgets import BLACK, WHITE, GRAY, CYAN, DARK_GRAY, draw_text

# Menu region: top-left 100x100 tap opens menu
MENU_TAP_REGION = pygame.Rect(0, 0, 100, 100)

# Screen tiles
MENU_ITEMS = [
    ("VU Meter", "vu_meter"),
    ("Dual VU", "dual_vu_meter"),
    ("Spectrum", "spectrum"),
    ("Mixer", "mixer"),
    ("Bluetooth", "bluetooth_settings"),
    ("WiFi", "wifi_settings"),
]

COLS, ROWS = 3, 2
MARGIN = 10
TILE_W = (480 - MARGIN * (COLS + 1)) // COLS
TILE_H = (320 - MARGIN * (ROWS + 1)) // ROWS


class Menu:
    """3x2 tile menu for screen selection."""

    def __init__(self):
        self.visible = False
        self._selected: str | None = None

    def toggle(self):
        self.visible = not self.visible

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def draw(self, surface: pygame.Surface, current_screen: str):
        if not self.visible:
            return

        # Dim background
        overlay = pygame.Surface((480, 320), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        for i, (label, screen_id) in enumerate(MENU_ITEMS):
            col = i % COLS
            row = i // COLS
            x = MARGIN + col * (TILE_W + MARGIN)
            y = MARGIN + row * (TILE_H + MARGIN)

            is_current = screen_id == current_screen
            bg_color = CYAN if is_current else DARK_GRAY
            pygame.draw.rect(surface, bg_color, (x, y, TILE_W, TILE_H), border_radius=8)
            pygame.draw.rect(surface, WHITE if is_current else GRAY,
                             (x, y, TILE_W, TILE_H), 2, border_radius=8)
            draw_text(surface, label, x + TILE_W // 2, y + TILE_H // 2,
                      WHITE, 20, center=True)

    def on_touch(self, x: int, y: int) -> str | None:
        """Returns screen_id if a tile was tapped, else None."""
        if not self.visible:
            return None

        for i, (label, screen_id) in enumerate(MENU_ITEMS):
            col = i % COLS
            row = i // COLS
            tx = MARGIN + col * (TILE_W + MARGIN)
            ty = MARGIN + row * (TILE_H + MARGIN)
            if tx <= x <= tx + TILE_W and ty <= y <= ty + TILE_H:
                return screen_id
        return None
