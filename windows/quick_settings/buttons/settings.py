from fabric.widgets.button import Button
from snippets import Icon

class SettingsButton(Button):
    def __init__(self, stack, **kwargs):
        super().__init__(
            style_classes=["applet-misc-button"],
            child=Icon(icon_name="gear", icon_size=16),
            on_clicked=lambda *_: stack.set_visible_child_name("power"),
            **kwargs,
        )