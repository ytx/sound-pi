"""GPIO manager: rotary encoder via gpiomon, LED via sysfs PWM.

Uses libgpiod v2 CLI (gpioget/gpiomon with -c/--chip, -e/--edges).
"""

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
PWM_CHANNEL = PWM_CHIP / "pwm1"  # pin13 = PWM0_1 → channel 1
PWM_PERIOD_NS = 5_000  # 5us = 200kHz (above audible range to avoid audio noise)

# Events
EVT_ROTATE_CW = "rotate_cw"
EVT_ROTATE_CCW = "rotate_ccw"
EVT_BUTTON_SHORT = "button_short"
EVT_BUTTON_LONG = "button_long"

ENCODER_DEBOUNCE_S = 0.005  # 5ms — ignore rotation events within this interval
BUTTON_DEBOUNCE_S = 0.05   # 50ms — ignore button edges within this interval


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

        # Last known pin states (tracked from gpiomon events)
        self.pin_states: dict[int, int | None] = {
            CLK_PIN: None, DT_PIN: None, SW_PIN: None,
        }

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
        """Monitor rotary encoder CLK+DT with gpiomon (libgpiod v2)."""
        try:
            self._encoder_proc = subprocess.Popen(
                [
                    "gpiomon", "-c", "gpiochip0",
                    "-e", "both", "-b", "pull-up",
                    "--format", "%o %e",
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
        """Parse gpiomon v2 output: '<offset> <edge_type>'
        edge_type: 1=rising, 2=falling
        """
        last_event_time = 0.0
        while self._running and self._encoder_proc:
            line = self._encoder_proc.stdout.readline()
            if not line:
                break
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            try:
                offset = int(parts[0])
                edge = int(parts[1])
            except (ValueError, IndexError):
                continue

            # Track pin state: rising=1, falling=0
            pin_val = 1 if edge == 1 else 0
            self.pin_states[offset] = pin_val

            if offset == CLK_PIN and edge == 2:  # falling
                now = time.monotonic()
                if now - last_event_time < ENCODER_DEBOUNCE_S:
                    continue
                dt_val = self.pin_states.get(DT_PIN)
                if dt_val is not None:
                    evt = EVT_ROTATE_CW if dt_val == 1 else EVT_ROTATE_CCW
                    with self._lock:
                        self._events.append(evt)
                    last_event_time = now

    def _start_button(self):
        """Monitor rotary encoder switch (libgpiod v2)."""
        try:
            self._button_proc = subprocess.Popen(
                [
                    "gpiomon", "-c", "gpiochip0",
                    "-e", "both", "-b", "pull-up",
                    "--format", "%o %e",
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
        """Parse gpiomon v2 output for button press/release.
        edge_type: 1=rising, 2=falling
        Debounce: ignore edges within BUTTON_DEBOUNCE_S of the previous edge.
        Emit EVT_BUTTON_SHORT on rising (release) only.
        """
        press_time = None
        last_edge_time = 0.0
        while self._running and self._button_proc:
            line = self._button_proc.stdout.readline()
            if not line:
                break
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            try:
                edge = int(parts[1])
            except (ValueError, IndexError):
                continue

            now = time.monotonic()
            if now - last_edge_time < BUTTON_DEBOUNCE_S:
                continue
            last_edge_time = now

            # Track pin state
            self.pin_states[SW_PIN] = 1 if edge == 1 else 0

            if edge == 2:  # falling = press
                press_time = now
            elif edge == 1 and press_time is not None:  # rising = release
                with self._lock:
                    self._events.append(EVT_BUTTON_SHORT)
                press_time = None

    def _read_pin(self, pin: int) -> int | None:
        """Read GPIO pin value using gpioget v2.
        Output format: '"<pin>"=active' or '"<pin>"=inactive'
        """
        try:
            out = subprocess.check_output(
                ["gpioget", "-c", "gpiochip0", "-b", "pull-up", str(pin)],
                timeout=1, text=True,
            )
            # Parse v2 output: "19"=active → 1, "19"=inactive → 0
            return 0 if "inactive" in out else 1
        except Exception:
            return None

    def _setup_pwm(self):
        """Set up sysfs hardware PWM for LED."""
        try:
            export = PWM_CHIP / "export"
            if not PWM_CHANNEL.exists() and export.exists():
                export.write_text("1")
                # Wait for udev to create the directory
                for _ in range(10):
                    if PWM_CHANNEL.exists():
                        break
                    time.sleep(0.1)

            if not PWM_CHANNEL.exists():
                log.warning("PWM channel not found")
                return

            # Wait for udev to set permissions (root:gpio)
            period_path = PWM_CHANNEL / "period"
            for _ in range(20):
                if os.access(period_path, os.W_OK):
                    break
                time.sleep(0.1)
            else:
                log.warning("PWM permission timeout")
                return

            period_path.write_text(str(PWM_PERIOD_NS))
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
