"""Dual L/R VU meter screen."""

import math
import pygame

from screens.base import Screen
from ui.widgets import BLACK, WHITE, GRAY, GREEN, YELLOW, RED, draw_text

# Meter geometry — two smaller meters side by side
LEFT_CX, LEFT_CY = 130, 260
RIGHT_CX, RIGHT_CY = 350, 260
RADIUS = 150
NEEDLE_LEN = 135
ARC_START = math.radians(220)
ARC_END = math.radians(320)

ATTACK = 0.3
RELEASE = 0.08
PEAK_DECAY = 0.98


class _MeterState:
    def __init__(self):
        self.needle = 0.0
        self.peak = 0.0

    def update(self, target: float):
        target = min(1.0, target * 2.5)
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

    def update(self, dt: float):
        data = self._audio.get_data()
        self._left.update(data["level_l"])
        self._right.update(data["level_r"])

    def draw(self, surface: pygame.Surface):
        surface.fill(BLACK)

        self._draw_meter(surface, LEFT_CX, LEFT_CY, self._left, "L")
        self._draw_meter(surface, RIGHT_CX, RIGHT_CY, self._right, "R")

        draw_text(surface, "DUAL VU", 240, 15, WHITE, 24, center=True)

    def _draw_meter(self, surface: pygame.Surface, cx: int, cy: int,
                    state: _MeterState, label: str):
        # Arc
        segments = 40
        for i in range(segments):
            frac = i / segments
            angle = ARC_START + (ARC_END - ARC_START) * frac
            next_angle = ARC_START + (ARC_END - ARC_START) * (i + 1) / segments
            color = GREEN if frac < 0.6 else (YELLOW if frac < 0.85 else RED)
            x1 = cx + int(math.cos(angle) * (RADIUS - 10))
            y1 = cy - int(math.sin(angle) * (RADIUS - 10))
            x2 = cx + int(math.cos(next_angle) * (RADIUS - 10))
            y2 = cy - int(math.sin(next_angle) * (RADIUS - 10))
            pygame.draw.line(surface, color, (x1, y1), (x2, y2), 3)

        # Scale marks
        for frac in (0.0, 0.2, 0.4, 0.6, 0.75, 0.85, 1.0):
            angle = ARC_START + (ARC_END - ARC_START) * frac
            xi = cx + int(math.cos(angle) * (RADIUS - 22))
            yi = cy - int(math.sin(angle) * (RADIUS - 22))
            xo = cx + int(math.cos(angle) * (RADIUS - 5))
            yo = cy - int(math.sin(angle) * (RADIUS - 5))
            pygame.draw.line(surface, WHITE, (xi, yi), (xo, yo), 1)

        # Peak needle
        pa = ARC_START + (ARC_END - ARC_START) * state.peak
        px = cx + int(math.cos(pa) * NEEDLE_LEN)
        py = cy - int(math.sin(pa) * NEEDLE_LEN)
        pygame.draw.line(surface, RED, (cx, cy), (px, py), 1)

        # Main needle
        na = ARC_START + (ARC_END - ARC_START) * state.needle
        nx = cx + int(math.cos(na) * NEEDLE_LEN)
        ny = cy - int(math.sin(na) * NEEDLE_LEN)
        pygame.draw.line(surface, WHITE, (cx, cy), (nx, ny), 2)

        # Pivot
        pygame.draw.circle(surface, GRAY, (cx, cy), 6)

        # Label
        draw_text(surface, label, cx, cy - RADIUS - 5, WHITE, 18, center=True)
