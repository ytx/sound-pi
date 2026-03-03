"""GPIO manager: rotary encoder via gpiomon, LED via sysfs PWM."""

import os
import subprocess
import threading
import time
from pathlib import Path

from logger import get_logger

log = get_logger("gpio")

# Rotary encoder pins
CLK_PIN = 19
DT_PIN = 20
SW_PIN = 26

# sysfs PWM for LED
PWM_CHIP = Path("/sys/class/pwm/pwmchip0")
PWM_CHANNEL = PWM_CHIP / "pwm0"
PWM_PERIOD_NS = 1_000_000  # 1ms = 1kHz

# Events
EVT_ROTATE_CW = "rotate_cw"
EVT_ROTATE_CCW = "rotate_ccw"
EVT_BUTTON_SHORT = "button_short"
EVT_BUTTON_LONG = "button_long"

LONG_PRESS_MS = 600


class GpioManager:
    """Rotary encoder and LED PWM control."""

    def __init__(self):
        self._events: list[str] = []
        self._lock = threading.Lock()
        self._running = False
        self._encoder_proc: subprocess.Popen | None = None
        self._encoder_thread: threading.Thread | None = None
        self._button_proc: subprocess.Popen | None = None
        self._button_thread: threading.Thread | None = None
        self._pwm_enabled = False
        self._stub = False

    def start(self):
        self._running = True
        if not self._detect_gpio():
            log.info("GPIO not available — stub mode")
            self._stub = True
            return

        self._start_encoder()
        self._start_button()
        self._setup_pwm()

    def _detect_gpio(self) -> bool:
        try:
            subprocess.run(["gpioget", "--help"], capture_output=True, timeout=2)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _start_encoder(self):
        """Monitor rotary encoder CLK+DT with gpiomon."""
        try:
            self._encoder_proc = subprocess.Popen(
                [
                    "gpiomon", "--chip", "gpiochip0",
                    "--falling-edge", "--rising-edge",
                    str(CLK_PIN), str(DT_PIN),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._encoder_thread = threading.Thread(target=self._encoder_loop, daemon=True)
            self._encoder_thread.start()
            log.info("encoder monitoring started (CLK=%d, DT=%d)", CLK_PIN, DT_PIN)
        except Exception as e:
            log.warning("encoder start failed: %s", e)

    def _encoder_loop(self):
        last_clk = None
        while self._running and self._encoder_proc:
            line = self._encoder_proc.stdout.readline()
            if not line:
                break
            # gpiomon output: "EVENT offset TIMESTAMP edge"
            parts = line.strip().split()
            if len(parts) < 3:
                continue
            try:
                offset = int(parts[1])
                edge = parts[-1]  # "RISING" or "FALLING"
            except (ValueError, IndexError):
                continue

            if offset == CLK_PIN and edge == "FALLING":
                # Read DT state
                dt_val = self._read_pin(DT_PIN)
                if dt_val is not None:
                    evt = EVT_ROTATE_CW if dt_val == 1 else EVT_ROTATE_CCW
                    with self._lock:
                        self._events.append(evt)

    def _start_button(self):
        """Monitor rotary encoder switch."""
        try:
            self._button_proc = subprocess.Popen(
                [
                    "gpiomon", "--chip", "gpiochip0",
                    "--falling-edge", "--rising-edge",
                    str(SW_PIN),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._button_thread = threading.Thread(target=self._button_loop, daemon=True)
            self._button_thread.start()
            log.info("button monitoring started (SW=%d)", SW_PIN)
        except Exception as e:
            log.warning("button start failed: %s", e)

    def _button_loop(self):
        press_time = None
        while self._running and self._button_proc:
            line = self._button_proc.stdout.readline()
            if not line:
                break
            parts = line.strip().split()
            if len(parts) < 3:
                continue
            edge = parts[-1]
            if edge == "FALLING":
                press_time = time.monotonic()
            elif edge == "RISING" and press_time is not None:
                duration_ms = (time.monotonic() - press_time) * 1000
                evt = EVT_BUTTON_LONG if duration_ms >= LONG_PRESS_MS else EVT_BUTTON_SHORT
                with self._lock:
                    self._events.append(evt)
                press_time = None

    def _read_pin(self, pin: int) -> int | None:
        try:
            out = subprocess.check_output(
                ["gpioget", "gpiochip0", str(pin)],
                timeout=1, text=True,
            )
            return int(out.strip())
        except Exception:
            return None

    def _setup_pwm(self):
        """Set up sysfs hardware PWM for LED."""
        try:
            export = PWM_CHIP / "export"
            if not PWM_CHANNEL.exists() and export.exists():
                export.write_text("0")
                # Wait for udev
                for _ in range(10):
                    if PWM_CHANNEL.exists():
                        break
                    time.sleep(0.1)

            if PWM_CHANNEL.exists():
                (PWM_CHANNEL / "period").write_text(str(PWM_PERIOD_NS))
                (PWM_CHANNEL / "duty_cycle").write_text("0")
                (PWM_CHANNEL / "enable").write_text("1")
                self._pwm_enabled = True
                log.info("PWM enabled")
        except Exception as e:
            log.warning("PWM setup failed: %s", e)

    def set_led_brightness(self, brightness: float):
        """Set LED brightness (0.0 to 1.0)."""
        if not self._pwm_enabled:
            return
        duty = int(max(0.0, min(1.0, brightness)) * PWM_PERIOD_NS)
        try:
            (PWM_CHANNEL / "duty_cycle").write_text(str(duty))
        except Exception:
            pass

    def poll_events(self) -> list[str]:
        """Get and clear pending GPIO events."""
        with self._lock:
            events = list(self._events)
            self._events.clear()
        return events

    def stop(self):
        self._running = False
        for proc in (self._encoder_proc, self._button_proc):
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
        if self._pwm_enabled:
            try:
                (PWM_CHANNEL / "enable").write_text("0")
            except Exception:
                pass
        log.info("gpio stopped")
