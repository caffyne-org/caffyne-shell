from fabric.widgets.label import Label
from snippets import Icon
from .button import QSButton

class KeyboardButton(QSButton):
    def __init__(self, stack):
        super().__init__(
            icon = Icon(
                icon_name="keyboard",
                pixel_size=16
            ),
            label = Label(
                label = "Keyboard"
            ),
            menu_name="kb",
            stack = stack,
            on_activate=lambda _: stack.set_visible_child_name("kb"),
            )