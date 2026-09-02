from .button import QSButton
from fabric.widgets.label import Label
from snippets import Icon
from services.singletons import theme_service
from user_options import user_options
class DarkModeButton(QSButton):
    def __init__(self):
        super().__init__(
            icon = Icon(
                icon_name="drop-half-bottom",
                pixel_size=16
            ),
            label = Label(
                label = "Dark Mode"
            ),

            on_activate=lambda _: self._handle_click(True),
            on_deactivate=lambda _ : self._handle_click(False),
        )
        setattr(self, "active", user_options.theme.is_dark)
        theme_service.connect("notify::is-dark", self._on_theme_changed)
    def _on_theme_changed(self, *args):
        setattr(self, "active", user_options.theme.is_dark)
    def _handle_click(self, bool):
        theme_service.apply_dark(bool)
        user_options.save()
        setattr(self, "active", user_options.theme.is_dark)