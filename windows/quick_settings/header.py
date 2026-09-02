from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from snippets import Icon
from icons import BatteryIcon
from services.singletons import battery

class QSHeader(CenterBox):
    def __init__(self, stack, **kwargs):
        super().__init__(
            start_children=Button(
                style_classes=["applet-misc-button", "battery"],
                child=BatteryIcon(size=16, percent=True) if battery and battery.available else Icon(icon_name="lightning"),
                on_clicked=lambda *_: stack.set_visible_child_name("power"),
            ),
            end_children= Button(
                style_classes=["applet-misc-button"],
                child=Icon(icon_name="power", icon_size=16),
                on_clicked=lambda *_: stack.set_visible_child_name("logout"),
            ),
            **kwargs,
        )