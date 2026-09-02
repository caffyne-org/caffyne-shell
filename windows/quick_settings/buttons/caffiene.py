from .button import QSButton
from snippets import Icon
from services.singletons import idle

class CaffieneButton(QSButton):
    def __init__(self, **kwargs):
        super().__init__(
            icon=Icon(icon_name="coffee"),
            on_activate=lambda _: idle.stop(),
            on_deactivate=lambda _: idle.start(),
            **kwargs,
        )

        idle.connect(
            "notify::active",
            lambda obj, _: setattr(self, "active", not obj.active),
        )
        self.active = not idle.active