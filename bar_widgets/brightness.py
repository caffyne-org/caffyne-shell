from .base import StatButton
from gi.repository import GLib
from services.singletons import brightness
from snippets import Icon
 
class BrightnessButton(StatButton):
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        icon_name = "seal" if brightness.backend else "seal-warning"
        self._current_brightness = brightness.screen_brightness
        super().__init__(
            icon=lambda size: Icon(icon_name=icon_name, icon_size=size),
            label=self._get_label(),
            variant=variant or "icon+label",
            **kwargs,
        )
        brightness.connect("screen", self._on_brightness_changed)
        if brightness.backend:
            GLib.timeout_add(1000, lambda: self._on_brightness_changed(None, percent=brightness.screen_brightness * 100 // brightness.max_screen))
    def _get_label(self) -> str:
        raw = brightness.screen_brightness
        if raw < 0 or brightness.max_screen == 0:
            return "N/A"
        return f"{int((raw / brightness.max_screen) * 100)}%"
 
    def _on_brightness_changed(self, _, percent: int):
        self._update_label(f"{percent}%")
        self._update_value(percent)

    def _adjust(self, direction: int):
        step = max(1, round(brightness.max_screen / 100))
        new_val = int(max(0, min(brightness.max_screen, self._current_brightness - (step * direction))))
        self._current_brightness = new_val
        brightness.screen_brightness = new_val