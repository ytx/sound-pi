"""Developer tools screen."""

import subprocess
import threading
import time

import pygame

from screens.base import Screen
from managers.audio import AudioCapture
from managers.gpio import GpioManager, CLK_PIN, DT_PIN, SW_PIN
from ui.widgets import (BLACK, WHITE, GRAY, CYAN, GREEN, RED, ORANGE,
                        draw_text, draw_bar)
from logger import get_logger

log = get_logger("develop")

TEST_SOUND = "/usr/share/sounds/alsa/Front_Center.wav"


class DevelopScreen(Screen):
    name = "develop"

    def __init__(self, audio: AudioCapture, gpio: GpioManager):
        self._audio = audio
        self._gpio = gpio

        # LED test state
        self._led_testing = False
        self._led_thread: threading.Thread | None = None

        # Sound test state
        self._sound_proc: subprocess.Popen | None = None

        # GPIO pin readings
        self._clk_val: int | None = None
        self._dt_val: int | None = None
        self._sw_val: int | None = None
        self._gpio_timer = 0.0

        # Status message
        self._status = ""

        # Buttons
        self._btn_led = pygame.Rect(20, 260, 130, 36)
        self._btn_play = pygame.Rect(170, 260, 130, 36)
        self._btn_stop = pygame.Rect(320, 260, 130, 36)

    def on_enter(self):
        self._status = ""
        self._read_gpio_pins()

    def on_exit(self):
        self._stop_all()

    def _read_gpio_pins(self):
        if self._gpio._stub:
            return
        self._clk_val = self._gpio._read_pin(CLK_PIN)
        self._dt_val = self._gpio._read_pin(DT_PIN)
        self._sw_val = self._gpio._read_pin(SW_PIN)

    def _start_led_test(self):
        if self._led_testing:
            return
        self._led_testing = True
        self._status = "LED test running..."
        self._led_thread = threading.Thread(target=self._led_cycle, daemon=True)
        self._led_thread.start()

    def _led_cycle(self):
        try:
            # Ramp up
            for i in range(0, 101, 2):
                if not self._led_testing:
                    break
                self._gpio.set_led_brightness(i / 100.0)
                time.sleep(0.02)
            # Ramp down
            for i in range(100, -1, -2):
                if not self._led_testing:
                    break
                self._gpio.set_led_brightness(i / 100.0)
                time.sleep(0.02)
            self._gpio.set_led_brightness(0.0)
        except Exception as e:
            log.warning("LED test error: %s", e)
        finally:
            self._led_testing = False
            self._status = "LED test done"

    def _start_sound_test(self):
        if self._sound_proc and self._sound_proc.poll() is None:
            return
        try:
            self._sound_proc = subprocess.Popen(
                ["pw-play", TEST_SOUND],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._status = "Playing test sound..."
        except Exception as e:
            self._status = f"Play error: {e}"
            log.warning("sound test error: %s", e)

    def _stop_all(self):
        self._led_testing = False
        if self._sound_proc and self._sound_proc.poll() is None:
            self._sound_proc.terminate()
            self._sound_proc = None
        self._status = "Stopped"

    def update(self, dt: float):
        self._gpio_timer += dt
        if self._gpio_timer >= 0.5:
            self._gpio_timer = 0.0
            self._read_gpio_pins()

        # Check if sound finished
        if self._sound_proc and self._sound_proc.poll() is not None:
            self._sound_proc = None
            if self._status == "Playing test sound...":
                self._status = "Playback finished"

    def draw(self, surface: pygame.Surface):
        import math

        surface.fill(BLACK)
        draw_text(surface, "Develop", 240, 16, WHITE, 24, center=True)

        y = 50

        # GPIO section
        draw_text(surface, "GPIO Pins", 20, y, CYAN, 16)
        y += 24
        pin_str = (f"CLK({CLK_PIN})={self._fmt_pin(self._clk_val)}  "
                   f"DT({DT_PIN})={self._fmt_pin(self._dt_val)}  "
                   f"SW({SW_PIN})={self._fmt_pin(self._sw_val)}")
        draw_text(surface, pin_str, 20, y, WHITE, 14)
        y += 24

        led_str = "LED: testing..." if self._led_testing else "LED: idle"
        draw_text(surface, led_str, 20, y, ORANGE if self._led_testing else GRAY, 14)
        y += 30

        # Audio section
        draw_text(surface, "Audio Levels", 20, y, CYAN, 16)
        y += 24

        db_l = self._to_db(self._audio.level_l)
        db_r = self._to_db(self._audio.level_r)
        draw_text(surface, f"L: {db_l:+6.1f} dB", 20, y, WHITE, 14)
        draw_bar(surface, 160, y + 2, 280, 12, self._audio.level_l, GREEN)
        y += 22
        draw_text(surface, f"R: {db_r:+6.1f} dB", 20, y, WHITE, 14)
        draw_bar(surface, 160, y + 2, 280, 12, self._audio.level_r, GREEN)
        y += 22

        peak_l = self._to_db(self._audio.peak_l)
        peak_r = self._to_db(self._audio.peak_r)
        draw_text(surface, f"Peak L: {peak_l:+.1f} dB  R: {peak_r:+.1f} dB", 20, y, GRAY, 12)
        y += 22

        # pw-cat status
        pw_status = "running" if self._audio._proc and self._audio._proc.poll() is None else "stopped"
        draw_text(surface, f"pw-cat: {pw_status}", 20, y, WHITE, 14)
        y += 20

        # Status
        if self._status:
            draw_text(surface, self._status, 240, 240, ORANGE, 14, center=True)

        # Buttons
        self._draw_btn(surface, self._btn_led, "LED Test", self._led_testing)
        self._draw_btn(surface, self._btn_play, "Play Sound",
                       self._sound_proc is not None and self._sound_proc.poll() is None)
        self._draw_btn(surface, self._btn_stop, "Stop", False)

    def _draw_btn(self, surface, rect, text, active):
        color = CYAN if active else GRAY
        pygame.draw.rect(surface, color, rect, border_radius=6)
        pygame.draw.rect(surface, WHITE, rect, 1, border_radius=6)
        draw_text(surface, text, rect.centerx, rect.centery, WHITE, 14, center=True)

    def on_touch(self, x: int, y: int, event_type: str):
        if event_type != "down":
            return

        if self._btn_led.collidepoint(x, y):
            self._start_led_test()
        elif self._btn_play.collidepoint(x, y):
            self._start_sound_test()
        elif self._btn_stop.collidepoint(x, y):
            self._stop_all()

    @staticmethod
    def _fmt_pin(val: int | None) -> str:
        return str(val) if val is not None else "?"

    @staticmethod
    def _to_db(level: float) -> float:
        import math
        if level <= 0:
            return -60.0
        return max(-60.0, 20.0 * math.log10(level))
