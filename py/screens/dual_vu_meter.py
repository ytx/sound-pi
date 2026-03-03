"""Dual L/R VU meter screen — image-based rendering."""

import math
import pygame

from screens.base import Screen
from ui.assets import load_image
from ui.widgets import BLACK, WHITE, GRAY, RED, draw_text

# Meter positions
LEFT_CX, LEFT_CY = 120, 230
RIGHT_CX, RIGHT_CY = 360, 230

ARC_START_DEG = 140
ARC_END_DEG = 40
SWEEP = ARC_START_DEG - ARC_END_DEG

ATTACK = 0.3
RELEASE = 0.08
PEAK_DECAY = 0.98


class _MeterState:
    def __init__(self):
        self.needle = 0.0
        self.peak = 0.0

    def update(self, target: float):
        target = min(1.0, target * 30.0)
        if target > self.needle:
            self.needle += (target - self.needle) * ATTACK
        else:
            self.needle += (target - self.needle) * RELEASE
        if self.needle > self.peak:
            self.peak = self.needle
        else:
            self.peak *= PEAK_DECAY


class DualVuMeterScreen(Screen):
    name = "dual_vu_meter"

    def __init__(self, audio_capture):
        self._audio = audio_capture
        self._left = _MeterState()
        self._right = _MeterState()
        self._bg: pygame.Surface | None = None
        self._needle_img: pygame.Surface | None = None
        self._loaded = False

    def _load_assets(self):
        if self._loaded:
            return
        self._bg = load_image("dual_vu_bg.png")
        self._needle_img = load_image("dual_vu_needle.png")
        self._loaded = True

    def update(self, dt: float):
        data = self._audio.get_data()
        self._left.update(data["level_l"])
        self._right.update(data["level_r"])

    def draw(self, surface: pygame.Surface):
        self._load_assets()
        surface.fill(BLACK)

        draw_text(surface, "DUAL VU", 240, 12, WHITE, 24, center=True)

        self._draw_meter(surface, LEFT_CX, LEFT_CY, self._left, "L")
        self._draw_meter(surface, RIGHT_CX, RIGHT_CY, self._right, "R")

    def _draw_meter(self, surface: pygame.Surface, cx: int, cy: int,
                    state: _MeterState, label: str):
        # Background image
        if self._bg:
            bw, bh = self._bg.get_size()
            surface.blit(self._bg, (cx - bw // 2, cy - bh + 25))

        # Peak needle (line)
        self._draw_needle_line(surface, cx, cy, state.peak, RED, 1)

        # Main needle
        if self._needle_img:
            angle_deg = ARC_START_DEG - state.needle * SWEEP
            rotation = angle_deg - 90
            rotated = pygame.transform.rotate(self._needle_img, rotation)
            angle_rad = math.radians(angle_deg)
            half_h = self._needle_img.get_height() / 2
            img_cx = cx + math.cos(angle_rad) * half_h
            img_cy = cy - math.sin(angle_rad) * half_h
            rect = rotated.get_rect(center=(int(img_cx), int(img_cy)))
            surface.blit(rotated, rect)
        else:
            self._draw_needle_line(surface, cx, cy, state.needle, WHITE, 2)

        # Label
        draw_text(surface, label, cx, cy - 160, WHITE, 18, center=True)

    def _draw_needle_line(self, surface: pygame.Surface, cx: int, cy: int,
                          pos: float, color: tuple, width: int):
        angle_deg = ARC_START_DEG - pos * SWEEP
        angle_rad = math.radians(angle_deg)
        length = 130
        x = cx + int(math.cos(angle_rad) * length)
        y = cy - int(math.sin(angle_rad) * length)
        pygame.draw.line(surface, color, (cx, cy), (x, y), width)
