"""Base class for all screens."""

import pygame


class Screen:
    """Abstract screen base class."""

    name: str = "base"

    def update(self, dt: float):
        """Update state. dt is seconds since last frame."""
        pass

    def draw(self, surface: pygame.Surface):
        """Draw the screen contents."""
        pass

    def on_touch(self, x: int, y: int, event_type: str):
        """Handle a touch event. event_type is 'down', 'move', or 'up'."""
        pass

    def on_enter(self):
        """Called when this screen becomes active."""
        pass

    def on_exit(self):
        """Called when leaving this screen."""
        pass
