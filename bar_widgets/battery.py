from .base import ProgressButton
from services.singletons import battery
from icons import BatteryIcon
from snippets import Icon
from gi.repository import GLib
 
class BatteryButton(ProgressButton):
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=lambda size: BatteryIcon(size, False) if battery.available else Icon(icon_name="lightning", icon_size=size),
            label=f"0%" if battery.available else None,
            variant=variant or "icon+label",
            **kwargs,
        )
        battery.connect("changed", self._update)
        if battery.available:
            GLib.timeout_add(1000, self._update)

    def _update(self, *_):
        bat = battery.percent
        self._update_label(f"{round(bat)}%")
        self._update_value(bat)
        return False