import time
from gi.repository import GLib
from .base import BaseButton
from snippets import Icon
 
class ClockButton(BaseButton):
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=Icon(icon_name="clock", icon_size=16),
            label=self._get_label(),
            variant=variant or "icon+label",
            **kwargs,
        )

        self.add_style_class("clock")
        GLib.timeout_add(1000, self._tick)
 
    def _get_label(self) -> str:
        return time.strftime("%H:%M")
 
    def _tick(self):
        self._update_label(self._get_label())
        return True