from fabric.widgets.box import Box
from fabric.widgets.label import Label
from snippets import Icon
from services.singletons import battery

class BatteryIcon(Box):
    def __init__(self, size: int, percent: bool, **kwargs):
        self._icon = Icon(
            icon_name=self._get_battery_icon(),
            icon_size=size,
        )
        self._label = Label(label=self._get_label())

        super().__init__(
            spacing=4,
            children=(
                [self._icon, self._label] if percent else [self._icon]
            ),
            **kwargs,
        )

        battery.connect("changed", self._update)

    def _update(self, *_):
        self._icon.icon_name = self._get_battery_icon()
        self._label.set_label(self._get_label())

    def _get_label(self) -> str:
        if not battery.available:
            return ""
        return f"{round(battery.percent)}%"

    def _get_battery_icon(self) -> str:
        if not battery.available:
            return "battery-vertical-empty"
        if battery.charging or battery.charged:
            return "battery-charging-vertical"
        p = battery.percent
        if p > 80:
            return "battery-vertical-full"
        elif p > 60:
            return "battery-vertical-high"
        elif p > 40:
            return "battery-vertical-medium"
        elif p > 20:
            return "battery-vertical-low"
        else:
            return "battery-vertical-lower"