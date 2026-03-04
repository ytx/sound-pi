"""Sound-Pi main application — entry point and main loop."""

import signal
import sys
import os

# Ensure py/ is on the path when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

from logger import get_logger
import config
from display import Display
from touch import Touch, TOUCH_DOWN, TOUCH_UP, TOUCH_MOVE
from managers.audio import AudioCapture, PipeWireManager
from managers.gpio import (GpioManager, EVT_ROTATE_CW, EVT_ROTATE_CCW,
                           EVT_BUTTON_SHORT, EVT_BUTTON_LONG)
from managers.hid import HidController
from screens.vu_meter import VuMeterScreen
from screens.dual_vu_meter import DualVuMeterScreen
from screens.spectrum import SpectrumScreen
from screens.mixer import MixerScreen
from screens.bluetooth_settings import BluetoothSettingsScreen
from screens.wifi_settings import WifiSettingsScreen
from screens.system import SystemScreen
from screens.develop import DevelopScreen
from ui.menu import Menu
from ui.volume_overlay import VolumeOverlay, MuteOverlay

log = get_logger("app")

FPS = 30
VOLUME_STEP = 5

# Main menu: visualization screens (top-left tap)
MAIN_MENU_ITEMS = [
    ("VU Meter", "vu_meter", "icon_vu_meter.png"),
    ("Dual VU", "dual_vu_meter", "icon_dual_vu_meter.png"),
    ("Spectrum", "spectrum", "icon_spectrum.png"),
    ("Mixer", "mixer", "icon_mixer.png"),
    ("", None, ""),
    ("", None, ""),
]

# Settings menu: system/config screens (top-right tap)
SETTINGS_MENU_ITEMS = [
    ("System", "system", "icon_system.png"),
    ("Bluetooth", "bluetooth_settings", "icon_bluetooth.png"),
    ("WiFi", "wifi_settings", "icon_wifi.png"),
    ("", None, ""),
    ("", None, ""),
    ("Develop", "develop", "icon_develop.png"),
]

MAIN_MENU_REGION = pygame.Rect(0, 0, 100, 100)
SETTINGS_MENU_REGION = pygame.Rect(380, 0, 100, 100)


class App:
    def __init__(self):
        self._running = False
        self._clock = pygame.time.Clock()

        # Core systems
        self._display = Display()
        self._touch = Touch()
        self._audio_capture = AudioCapture()
        self._pipewire = PipeWireManager()
        self._gpio = GpioManager()
        self._hid = HidController()

        # Config
        config.load()
        self._volume = config.get("master_volume", 80)
        self._muted = config.get("muted", False)

        # Screens
        self._screens: dict = {}
        self._register_screens()
        self._current_screen_id = config.get("last_screen", "vu_meter")
        if self._current_screen_id not in self._screens:
            self._current_screen_id = "vu_meter"

        # Menus
        self._main_menu = Menu(MAIN_MENU_ITEMS, MAIN_MENU_REGION)
        self._settings_menu = Menu(SETTINGS_MENU_ITEMS, SETTINGS_MENU_REGION)

        # Overlays
        self._volume_overlay = VolumeOverlay()
        self._mute_overlay = MuteOverlay()

    def _register_screens(self):
        screens = [
            VuMeterScreen(self._audio_capture),
            DualVuMeterScreen(self._audio_capture),
            SpectrumScreen(self._audio_capture),
            MixerScreen(self._pipewire),
            BluetoothSettingsScreen(),
            WifiSettingsScreen(),
            SystemScreen(),
            DevelopScreen(self._audio_capture, self._gpio),
        ]
        for s in screens:
            self._screens[s.name] = s

    def _switch_screen(self, screen_id: str):
        if screen_id not in self._screens or screen_id == self._current_screen_id:
            return
        current = self._screens.get(self._current_screen_id)
        if current:
            current.on_exit()
        self._current_screen_id = screen_id
        self._screens[screen_id].on_enter()
        config.set("last_screen", screen_id)
        log.info("switched to %s", screen_id)

    def run(self):
        log.info("starting Sound-Pi")
        self._running = True

        # Signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Start subsystems
        self._audio_capture.start()
        self._pipewire.start_routing()
        self._gpio.start()
        self._screens[self._current_screen_id].on_enter()

        try:
            while self._running:
                dt = self._clock.tick(FPS) / 1000.0
                self._process_events()
                self._process_gpio()
                self._update(dt)
                self._draw()
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _signal_handler(self, signum, frame):
        log.info("signal %d received, shutting down", signum)
        self._running = False

    def _process_events(self):
        # pygame events (for quit in window mode)
        for ev in pygame.event.get([pygame.QUIT]):
            if ev.type == pygame.QUIT:
                self._running = False

        # Touch events
        for event_type, x, y in self._touch.poll():
            self._handle_touch(event_type, x, y)

    def _handle_touch(self, event_type: str, x: int, y: int):
        if event_type != TOUCH_DOWN:
            # Forward move/up to current screen
            screen = self._screens.get(self._current_screen_id)
            if screen:
                screen.on_touch(x, y, event_type)
            return

        # Menu handling — if either menu is visible, handle its touch
        for menu in (self._main_menu, self._settings_menu):
            if menu.visible:
                selected = menu.on_touch(x, y)
                if selected:
                    self._switch_screen(selected)
                menu.hide()
                return

        # Check if current screen has an active overlay (e.g. mixer add-device)
        screen = self._screens.get(self._current_screen_id)
        if screen and getattr(screen, '_adding', False):
            screen.on_touch(x, y, event_type)
            return

        # Top-left tap → main menu
        if MAIN_MENU_REGION.collidepoint(x, y):
            self._settings_menu.hide()
            self._main_menu.show()
            return

        # Top-right tap → settings menu
        if SETTINGS_MENU_REGION.collidepoint(x, y):
            self._main_menu.hide()
            self._settings_menu.show()
            return

        # Forward to current screen
        if screen:
            screen.on_touch(x, y, event_type)

    def _process_gpio(self):
        mixer = self._screens["mixer"]
        for evt in self._gpio.poll_events():
            if evt in (EVT_ROTATE_CW, EVT_ROTATE_CCW):
                slot = mixer.get_selected_slot()
                if slot and slot.wpctl_id:
                    delta = (VOLUME_STEP / 100.0) if evt == EVT_ROTATE_CW else -(VOLUME_STEP / 100.0)
                    slot.volume = max(0.0, min(1.0, slot.volume + delta))
                    self._pipewire.set_sink_volume(slot.wpctl_id, slot.volume)
                    self._volume_overlay.show(int(slot.volume * 100))
                    self._gpio.set_led_brightness(slot.volume)
                    mixer.save_config()
                else:
                    # No device selected — fallback to master volume
                    if evt == EVT_ROTATE_CW:
                        self._volume = min(100, self._volume + VOLUME_STEP)
                    else:
                        self._volume = max(0, self._volume - VOLUME_STEP)
                    self._pipewire.set_volume(self._volume)
                    config.set("master_volume", self._volume)
                    self._volume_overlay.show(self._volume)
                    self._gpio.set_led_brightness(self._volume / 100.0)
            elif evt == EVT_BUTTON_SHORT:
                self._hid.play_pause()
            elif evt == EVT_BUTTON_LONG:
                slot = mixer.get_selected_slot()
                if slot and slot.wpctl_id:
                    slot.muted = not slot.muted
                    self._pipewire.set_sink_mute(slot.wpctl_id, slot.muted)
                    self._mute_overlay.show(slot.muted)
                    mixer.save_config()
                else:
                    self._muted = not self._muted
                    self._pipewire.set_mute(self._muted)
                    config.set("muted", self._muted)
                    self._mute_overlay.show(self._muted)

    def _update(self, dt: float):
        screen = self._screens.get(self._current_screen_id)
        if screen:
            screen.update(dt)
        self._volume_overlay.update(dt)
        self._mute_overlay.update(dt)

    def _draw(self):
        surface = self._display.surface
        screen = self._screens.get(self._current_screen_id)
        if screen:
            screen.draw(surface)

        # Overlays (drawn on top)
        self._main_menu.draw(surface, self._current_screen_id)
        self._settings_menu.draw(surface, self._current_screen_id)
        self._volume_overlay.draw(surface)
        self._mute_overlay.draw(surface)

        self._display.flip()

    def _shutdown(self):
        log.info("shutting down")
        config.persist()
        self._audio_capture.stop()
        self._pipewire.stop_routing()
        self._gpio.stop()
        self._hid.close()
        self._touch.close()
        self._display.close()
        pygame.quit()
        log.info("bye")


def main():
    # NOTE: Do NOT call pygame.init() here — it would init the display
    # subsystem before Display can set SDL_VIDEODRIVER=dummy for fbdev mode.
    # Display.__init__() handles pygame.display.init() with the correct driver.
    # Init only non-display subsystems here.
    pygame.font.init()
    app = App()
    app.run()


if __name__ == "__main__":
    main()
