"""Analog needle VU meter screen."""

import math
import pygame

from screens.base import Screen
from ui.widgets import BLACK, WHITE, GRAY, GREEN, YELLOW, RED, draw_text

# Meter geometry
CENTER_X, CENTER_Y = 240, 280
RADIUS = 220
NEEDLE_LEN = 200
ARC_START = math.radians(220)  # left limit
ARC_END = math.radians(320)    # right limit

# Needle physics
ATTACK = 0.3    # fast attack
RELEASE = 0.08  # slow release
PEAK_DECAY = 0.98


class VuMeterScreen(Screen):
    name = "vu_meter"

    def __init__(self, audio_capture):
        self._audio = audio_capture
        self._needle_pos = 0.0  # 0..1
        self._peak_pos = 0.0

    def update(self, dt: float):
        data = self._audio.get_data()
        # Use mono level (average L+R)
        target = (data["level_l"] + data["level_r"]) * 0.5
        # Clamp and apply VU-style ballistics
        target = min(1.0, target * 2.5)  # boost for visibility

        if target > self._needle_pos:
            self._needle_pos += (target - self._needle_pos) * ATTACK
        else:
            self._needle_pos += (target - self._needle_pos) * RELEASE

        # Peak hold
        if self._needle_pos > self._peak_pos:
            self._peak_pos = self._needle_pos
        else:
            self._peak_pos *= PEAK_DECAY

    def draw(self, surface: pygame.Surface):
        surface.fill(BLACK)

        # Draw arc scale
        self._draw_arc(surface)

        # Draw scale markings
        self._draw_scale(surface)

        # Draw peak marker
        self._draw_needle_at(surface, self._peak_pos, RED, 2)

        # Draw main needle
        self._draw_needle_at(surface, self._needle_pos, WHITE, 3)

        # Draw pivot
        pygame.draw.circle(surface, GRAY, (CENTER_X, CENTER_Y), 10)

        # Label
        draw_text(surface, "VU", 240, 20, WHITE, 28, center=True)

        # dB readout
        db = self._to_db(self._needle_pos)
        draw_text(surface, f"{db:+.1f} dB", 240, 55, GRAY, 16, center=True)

    def _draw_arc(self, surface: pygame.Surface):
        """Draw the colored arc behind the needle."""
        segments = 60
        for i in range(segments):
            frac = i / segments
            angle = ARC_START + (ARC_END - ARC_START) * frac
            next_angle = ARC_START + (ARC_END - ARC_START) * (i + 1) / segments

            if frac < 0.6:
                color = GREEN
            elif frac < 0.85:
                color = YELLOW
            else:
                color = RED

            x1 = CENTER_X + int(math.cos(angle) * (RADIUS - 15))
            y1 = CENTER_Y - int(math.sin(angle) * (RADIUS - 15))
            x2 = CENTER_X + int(math.cos(next_angle) * (RADIUS - 15))
            y2 = CENTER_Y - int(math.sin(next_angle) * (RADIUS - 15))
            pygame.draw.line(surface, color, (x1, y1), (x2, y2), 4)

    def _draw_scale(self, surface: pygame.Surface):
        """Draw dB scale markings."""
        marks = [
            (0.0, "-20"), (0.2, "-10"), (0.4, "-5"),
            (0.6, "0"), (0.75, "+3"), (0.85, "+6"),
            (1.0, "+10"),
        ]
        for frac, label in marks:
            angle = ARC_START + (ARC_END - ARC_START) * frac
            x_inner = CENTER_X + int(math.cos(angle) * (RADIUS - 30))
            y_inner = CENTER_Y - int(math.sin(angle) * (RADIUS - 30))
            x_outer = CENTER_X + int(math.cos(angle) * (RADIUS - 5))
            y_outer = CENTER_Y - int(math.sin(angle) * (RADIUS - 5))
            pygame.draw.line(surface, WHITE, (x_inner, y_inner), (x_outer, y_outer), 2)

            x_text = CENTER_X + int(math.cos(angle) * (RADIUS + 5))
            y_text = CENTER_Y - int(math.sin(angle) * (RADIUS + 5))
            draw_text(surface, label, x_text, y_text, GRAY, 12, center=True)

    def _draw_needle_at(self, surface: pygame.Surface, pos: float,
                        color: tuple, width: int):
        angle = ARC_START + (ARC_END - ARC_START) * pos
        x = CENTER_X + int(math.cos(angle) * NEEDLE_LEN)
        y = CENTER_Y - int(math.sin(angle) * NEEDLE_LEN)
        pygame.draw.line(surface, color, (CENTER_X, CENTER_Y), (x, y), width)

    def _to_db(self, pos: float) -> float:
        if pos <= 0.001:
            return -40.0
        return 20.0 * math.log10(pos)
