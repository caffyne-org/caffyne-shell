from .base import ProgressButton
from snippets import Icon
from fabric.utils import invoke_repeater
import psutil
import threading
from gi.repository import GLib

class CPUIndicatorButton(ProgressButton):
    """Circular variant — scale with icon inside + optional percent label."""
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=lambda size: Icon(icon_name="cpu", icon_size=size),
            label="0%",
            variant=variant or "icon+label",
            **kwargs,
        )
        self._cpu = 0.0
        threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        while True:
            self._cpu = psutil.cpu_percent(interval=1.0)
            GLib.idle_add(self._apply)

    def _apply(self):
        self._update_label(f"{round(self._cpu)}%")
        self._update_value(round(self._cpu))
        return False