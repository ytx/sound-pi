"""Common UI widgets for pygame screens."""

import os
import pygame

# Color palette
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (80, 80, 80)
DARK_GRAY = (40, 40, 40)
GREEN = (0, 200, 0)
YELLOW = (200, 200, 0)
RED = (200, 0, 0)
CYAN = (0, 200, 200)
ORANGE = (255, 140, 0)
BLUE = (40, 100, 200)

# Font path
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_FONT_PATH = os.path.join(_ASSETS_DIR, "fonts", "SpaceMono-Italic.ttf")

# Fonts (initialized lazily)
_fonts: dict[int, pygame.font.Font] = {}


def get_font(size: int) -> pygame.font.Font:
    if size not in _fonts:
        pygame.font.init()
        if os.path.exists(_FONT_PATH):
            _fonts[size] = pygame.font.Font(_FONT_PATH, size)
        else:
            _fonts[size] = pygame.font.SysFont("monospace", size)
    return _fonts[size]


def draw_text(surface: pygame.Surface, text: str, x: int, y: int,
              color=WHITE, size: int = 16, center: bool = False):
    """Draw text on surface."""
    font = get_font(size)
    rendered = font.render(text, True, color)
    if center:
        rect = rendered.get_rect(center=(x, y))
        surface.blit(rendered, rect)
    else:
        surface.blit(rendered, (x, y))
    return rendered.get_rect()


def draw_bar(surface: pygame.Surface, x: int, y: int, w: int, h: int,
             value: float, color=GREEN, bg=DARK_GRAY):
    """Draw a horizontal bar (value 0..1)."""
    pygame.draw.rect(surface, bg, (x, y, w, h))
    fill_w = int(w * max(0.0, min(1.0, value)))
    if fill_w > 0:
        pygame.draw.rect(surface, color, (x, y, fill_w, h))
    pygame.draw.rect(surface, GRAY, (x, y, w, h), 1)


def draw_vbar(surface: pygame.Surface, x: int, y: int, w: int, h: int,
              value: float, color=GREEN, bg=DARK_GRAY):
    """Draw a vertical bar (value 0..1, fills from bottom)."""
    pygame.draw.rect(surface, bg, (x, y, w, h))
    fill_h = int(h * max(0.0, min(1.0, value)))
    if fill_h > 0:
        pygame.draw.rect(surface, color, (x, y + h - fill_h, w, fill_h))


def draw_button(surface: pygame.Surface, x: int, y: int, w: int, h: int,
                text: str, active: bool = False):
    """Draw a button."""
    color = CYAN if active else GRAY
    pygame.draw.rect(surface, color, (x, y, w, h), border_radius=6)
    pygame.draw.rect(surface, WHITE, (x, y, w, h), 1, border_radius=6)
    draw_text(surface, text, x + w // 2, y + h // 2, WHITE, 16, center=True)


def draw_vslider(surface: pygame.Surface, x: int, y: int, w: int, h: int,
                 value: float, color=CYAN, bg=DARK_GRAY, muted: bool = False):
    """Draw a vertical slider (value 0.0-1.0, fills from bottom).
    muted=True draws in gray."""
    fill_color = GRAY if muted else color
    pygame.draw.rect(surface, bg, (x, y, w, h))
    fill_h = int(h * max(0.0, min(1.0, value)))
    if fill_h > 0:
        pygame.draw.rect(surface, fill_color, (x, y + h - fill_h, w, fill_h))
    pygame.draw.rect(surface, GRAY, (x, y, w, h), 1)


def level_color(value: float) -> tuple[int, int, int]:
    """Return green/yellow/red based on level."""
    if value < 0.6:
        return GREEN
    elif value < 0.85:
        return YELLOW
    return RED
