import time
from gi.repository import GLib
from .base import BaseButton
from snippets import Icon
 
class CalendarButton(BaseButton):
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=Icon(icon_name="calendar-blank", icon_size=16),
            label=self._get_label(),
            variant=variant or "icon+label",
            **kwargs,
        )
        GLib.timeout_add(1000, self._tick)
 
    def _get_label(self) -> str:
        return time.strftime("%a, %b %-d")
 
    def _tick(self):
        self._update_label(self._get_label())
        return True