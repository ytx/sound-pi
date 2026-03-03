"""Volume bar overlay with auto-hide."""

import pygame

from ui.widgets import BLACK, WHITE, GRAY, GREEN, YELLOW, draw_text, draw_bar, level_color, get_font


class VolumeOverlay:
    """Shows current volume as a horizontal bar, fades after 2 seconds."""

    def __init__(self):
        self._visible = False
        self._timer: float = 0.0
        self._volume: int = 0
        self._alpha: int = 255
        self.SHOW_DURATION = 2.0  # seconds

    def show(self, volume: int):
        self._volume = volume
        self._timer = self.SHOW_DURATION
        self._visible = True
        self._alpha = 255

    def update(self, dt: float):
        if not self._visible:
            return
        self._timer -= dt
        if self._timer <= 0:
            self._visible = False
            return
        # Fade in last 0.5s
        if self._timer < 0.5:
            self._alpha = int(255 * (self._timer / 0.5))

    def draw(self, surface: pygame.Surface):
        if not self._visible:
            return

        overlay = pygame.Surface((300, 60), pygame.SRCALPHA)

        # Background
        pygame.draw.rect(overlay, (0, 0, 0, min(200, self._alpha)),
                         (0, 0, 300, 60), border_radius=10)

        # Volume bar
        bar_x, bar_y, bar_w, bar_h = 15, 30, 220, 16
        val = self._volume / 100.0
        pygame.draw.rect(overlay, (40, 40, 40, self._alpha),
                         (bar_x, bar_y, bar_w, bar_h))
        fill_w = int(bar_w * val)
        if fill_w > 0:
            color = level_color(val)
            r, g, b = color
            pygame.draw.rect(overlay, (r, g, b, self._alpha),
                             (bar_x, bar_y, fill_w, bar_h))

        # Text
        font = get_font(18)
        label = font.render(f"Vol: {self._volume}%", True, (255, 255, 255, self._alpha))
        overlay.blit(label, (15, 6))

        # Center on screen
        surface.blit(overlay, (90, 130))


class MuteOverlay:
    """Shows mute state briefly."""

    def __init__(self):
        self._visible = False
        self._timer: float = 0.0
        self._muted: bool = False

    def show(self, muted: bool):
        self._muted = muted
        self._timer = 1.5
        self._visible = True

    def update(self, dt: float):
        if not self._visible:
            return
        self._timer -= dt
        if self._timer <= 0:
            self._visible = False

    def draw(self, surface: pygame.Surface):
        if not self._visible:
            return

        overlay = pygame.Surface((200, 50), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (0, 0, 0, 200), (0, 0, 200, 50), border_radius=10)

        text = "MUTED" if self._muted else "UNMUTED"
        color = (200, 0, 0) if self._muted else GREEN
        font = get_font(24)
        rendered = font.render(text, True, color)
        rect = rendered.get_rect(center=(100, 25))
        overlay.blit(rendered, rect)

        surface.blit(overlay, (140, 135))
