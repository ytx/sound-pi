"""Analog needle VU meter screen — image-based rendering."""

import math
import pygame

from screens.base import Screen
from ui.assets import load_image
from ui.widgets import BLACK, WHITE, GRAY, RED, draw_text

# Meter geometry
CENTER_X, CENTER_Y = 240, 280
ARC_START_DEG = 140  # left limit
ARC_END_DEG = 40     # right limit
SWEEP = ARC_START_DEG - ARC_END_DEG  # 100 degrees

# Needle physics
ATTACK = 0.3
RELEASE = 0.08
PEAK_DECAY = 0.98


class VuMeterScreen(Screen):
    name = "vu_meter"

    def __init__(self, audio_capture):
        self._audio = audio_capture
        self._needle_pos = 0.0
        self._peak_pos = 0.0
        self._bg: pygame.Surface | None = None
        self._needle_img: pygame.Surface | None = None
        self._pivot_img: pygame.Surface | None = None
        self._loaded = False

    def _load_assets(self):
        if self._loaded:
            return
        self._bg = load_image("vu_bg.png")
        self._needle_img = load_image("vu_needle.png")
        self._pivot_img = load_image("vu_pivot.png")
        self._loaded = True

    def update(self, dt: float):
        data = self._audio.get_data()
        import math
        rms = (data["level_l"] + data["level_r"]) * 0.5
        # dB scale: -40dB → 0.0, 0dB → 1.0
        target = max(0.0, min(1.0, 1.0 + math.log10(rms + 1e-10) / 1.6))

        if target > self._needle_pos:
            self._needle_pos += (target - self._needle_pos) * ATTACK
        else:
            self._needle_pos += (target - self._needle_pos) * RELEASE

        if self._needle_pos > self._peak_pos:
            self._peak_pos = self._needle_pos
        else:
            self._peak_pos *= PEAK_DECAY

    def draw(self, surface: pygame.Surface):
        self._load_assets()

        # Background
        if self._bg:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill(BLACK)

        # Peak needle (thin, red)
        self._draw_needle(surface, self._peak_pos, is_peak=True)

        # Main needle
        self._draw_needle(surface, self._needle_pos, is_peak=False)

        # Pivot overlay
        if self._pivot_img:
            pw, ph = self._pivot_img.get_size()
            surface.blit(self._pivot_img, (CENTER_X - pw // 2, CENTER_Y - ph // 2))

        # dB readout
        db = self._to_db(self._needle_pos)
        draw_text(surface, f"{db:+.1f} dB", 240, 55, GRAY, 16, center=True)

    def _draw_needle(self, surface: pygame.Surface, pos: float, is_peak: bool):
        angle_deg = ARC_START_DEG - pos * SWEEP  # 140 → 40

        if self._needle_img and not is_peak:
            # Rotate needle image (pygame rotates CCW, image points up = 0°)
            # Needle image points up (90° in math coords)
            # We need it at angle_deg from horizontal
            # pygame rotation: 0° = no rotation (right), CCW positive
            rotation = angle_deg - 90  # adjust: image "up" is 90°
            rotated = pygame.transform.rotate(self._needle_img, rotation)
            # Image center must be halfway from pivot toward tip
            angle_rad = math.radians(angle_deg)
            half_h = self._needle_img.get_height() / 2
            img_cx = CENTER_X + math.cos(angle_rad) * half_h
            img_cy = CENTER_Y - math.sin(angle_rad) * half_h
            rect = rotated.get_rect(center=(int(img_cx), int(img_cy)))
            surface.blit(rotated, rect)
        else:
            # Fallback / peak: draw as line
            angle_rad = math.radians(angle_deg)
            length = 200 if not is_peak else 200
            x = CENTER_X + int(math.cos(angle_rad) * length)
            y = CENTER_Y - int(math.sin(angle_rad) * length)
            color = RED if is_peak else WHITE
            width = 1 if is_peak else 2
            pygame.draw.line(surface, color, (CENTER_X, CENTER_Y), (x, y), width)

    def _to_db(self, pos: float) -> float:
        if pos <= 0.001:
            return -40.0
        return 20.0 * math.log10(pos)
