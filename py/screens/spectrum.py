"""32-band spectrum analyzer screen — with gradient bar texture."""

import pygame

from screens.base import Screen
from ui.assets import load_image
from ui.widgets import BLACK, WHITE, GRAY, draw_text

NUM_BANDS = 32
SMOOTHING = 0.4
PEAK_DECAY = 0.98

# Layout
BAR_AREA_X = 20
BAR_AREA_Y = 50
BAR_AREA_W = 440
BAR_AREA_H = 240
BAR_GAP = 2
BAR_W = (BAR_AREA_W - BAR_GAP * (NUM_BANDS - 1)) // NUM_BANDS


class SpectrumScreen(Screen):
    name = "spectrum"

    def __init__(self, audio_capture):
        self._audio = audio_capture
        self._bars: list[float] = [0.0] * NUM_BANDS
        self._peaks: list[float] = [0.0] * NUM_BANDS
        self._bar_tex: pygame.Surface | None = None
        self._loaded = False

    def _load_assets(self):
        if self._loaded:
            return
        tex = load_image("spectrum_bar.png")
        if tex:
            # Scale to bar width x area height
            self._bar_tex = pygame.transform.scale(tex, (BAR_W, BAR_AREA_H))
        self._loaded = True

    def update(self, dt: float):
        data = self._audio.get_data()
        spectrum = data["spectrum"]

        for i in range(NUM_BANDS):
            target = spectrum[i] if i < len(spectrum) else 0.0
            self._bars[i] += (target - self._bars[i]) * SMOOTHING
            if self._bars[i] > self._peaks[i]:
                self._peaks[i] = self._bars[i]
            else:
                self._peaks[i] *= PEAK_DECAY

    def draw(self, surface: pygame.Surface):
        self._load_assets()
        surface.fill(BLACK)

        draw_text(surface, "SPECTRUM", 240, 15, WHITE, 24, center=True)

        for i in range(NUM_BANDS):
            x = BAR_AREA_X + i * (BAR_W + BAR_GAP)
            val = self._bars[i]
            bar_h = int(BAR_AREA_H * val)

            if bar_h > 0 and self._bar_tex:
                # Clip texture to show only bottom bar_h pixels
                src_rect = pygame.Rect(0, BAR_AREA_H - bar_h, BAR_W, bar_h)
                dest_y = BAR_AREA_Y + BAR_AREA_H - bar_h
                surface.blit(self._bar_tex, (x, dest_y), src_rect)
            elif bar_h > 0:
                # Fallback: solid green
                pygame.draw.rect(surface, (0, 200, 0),
                                 (x, BAR_AREA_Y + BAR_AREA_H - bar_h, BAR_W, bar_h))

            # Peak marker
            if self._peaks[i] > 0.01:
                peak_y = BAR_AREA_Y + BAR_AREA_H - int(BAR_AREA_H * self._peaks[i])
                pygame.draw.rect(surface, WHITE, (x, peak_y, BAR_W, 2))

        # Bottom border
        pygame.draw.line(surface, GRAY,
                         (BAR_AREA_X, BAR_AREA_Y + BAR_AREA_H),
                         (BAR_AREA_X + BAR_AREA_W, BAR_AREA_Y + BAR_AREA_H), 1)

        # Frequency labels
        labels = ["100", "500", "1k", "5k", "20k"]
        positions = [0, 8, 16, 24, 31]
        for label, pos in zip(labels, positions):
            x = BAR_AREA_X + pos * (BAR_W + BAR_GAP) + BAR_W // 2
            draw_text(surface, label, x, BAR_AREA_Y + BAR_AREA_H + 8, GRAY, 11, center=True)
