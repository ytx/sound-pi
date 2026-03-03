"""3x2 tile menu overlay with icons."""

import pygame

from ui.assets import load_image
from ui.widgets import BLACK, WHITE, GRAY, CYAN, DARK_GRAY, draw_text

COLS, ROWS = 3, 2
MARGIN = 10
TILE_W = (480 - MARGIN * (COLS + 1)) // COLS
TILE_H = (320 - MARGIN * (ROWS + 1)) // ROWS


class Menu:
    """3x2 tile menu for screen selection.

    items: [(label, screen_id_or_none, icon_filename), ...]
           screen_id=None means blank/disabled tile.
    tap_region: pygame.Rect area that opens this menu.
    """

    def __init__(self, items: list[tuple[str, str | None, str]],
                 tap_region: pygame.Rect):
        self.items = items
        self.tap_region = tap_region
        self.visible = False
        self._icons: dict[str, pygame.Surface | None] = {}
        self._icons_loaded = False

    def _load_icons(self):
        if self._icons_loaded:
            return
        for _, screen_id, icon_file in self.items:
            if screen_id and icon_file:
                self._icons[screen_id] = load_image(icon_file)
        self._icons_loaded = True

    def toggle(self):
        self.visible = not self.visible

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def draw(self, surface: pygame.Surface, current_screen: str):
        if not self.visible:
            return
        self._load_icons()

        # Dim background
        overlay = pygame.Surface((480, 320), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        for i, (label, screen_id, _) in enumerate(self.items):
            col = i % COLS
            row = i // COLS
            x = MARGIN + col * (TILE_W + MARGIN)
            y = MARGIN + row * (TILE_H + MARGIN)

            # Blank tile
            if not screen_id:
                pygame.draw.rect(surface, (30, 30, 30), (x, y, TILE_W, TILE_H),
                                 border_radius=8)
                pygame.draw.rect(surface, (50, 50, 50),
                                 (x, y, TILE_W, TILE_H), 1, border_radius=8)
                continue

            is_current = screen_id == current_screen
            bg_color = CYAN if is_current else DARK_GRAY
            pygame.draw.rect(surface, bg_color, (x, y, TILE_W, TILE_H), border_radius=8)
            pygame.draw.rect(surface, WHITE if is_current else GRAY,
                             (x, y, TILE_W, TILE_H), 2, border_radius=8)

            # Icon
            icon = self._icons.get(screen_id)
            if icon:
                iw, ih = icon.get_size()
                icon_y = y + (TILE_H - ih - 20) // 2
                surface.blit(icon, (x + (TILE_W - iw) // 2, icon_y))
                # Label below icon
                draw_text(surface, label, x + TILE_W // 2, icon_y + ih + 12,
                          WHITE, 16, center=True)
            else:
                draw_text(surface, label, x + TILE_W // 2, y + TILE_H // 2,
                          WHITE, 20, center=True)

    def on_touch(self, x: int, y: int) -> str | None:
        """Returns screen_id if a non-blank tile was tapped, else None."""
        if not self.visible:
            return None

        for i, (label, screen_id, _) in enumerate(self.items):
            if not screen_id:
                continue
            col = i % COLS
            row = i // COLS
            tx = MARGIN + col * (TILE_W + MARGIN)
            ty = MARGIN + row * (TILE_H + MARGIN)
            if tx <= x <= tx + TILE_W and ty <= y <= ty + TILE_H:
                return screen_id
        return None
