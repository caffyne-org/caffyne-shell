from .button import QSButton
from snippets import Icon
from services.singletons import night_mode

class NightModeButton(QSButton):
    def __init__(self):
        super().__init__(
            icon=Icon(icon_name="moon"),
            on_activate=lambda _: self.set_active(True),
            on_deactivate=lambda _: self.set_active(False)
        )

        setattr(self, "active", night_mode.enabled)

    def set_active(self, value: bool):
        night_mode.enabled = value
        setattr(self, "active", value),