"""Asset loader for image files."""

import os
import pygame

from logger import get_logger

log = get_logger("assets")

_IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "assets", "images")
_cache: dict[str, pygame.Surface] = {}


def load_image(name: str) -> pygame.Surface | None:
    """Load a PNG from assets/images/ with alpha. Returns None if not found."""
    if name in _cache:
        return _cache[name]
    path = os.path.join(_IMAGES_DIR, name)
    if not os.path.exists(path):
        log.warning("asset not found: %s", path)
        return None
    try:
        surf = pygame.image.load(path).convert_alpha()
        _cache[name] = surf
        log.info("loaded %s (%dx%d)", name, surf.get_width(), surf.get_height())
        return surf
    except Exception as e:
        log.warning("failed to load %s: %s", name, e)
        return None
