from .base import BaseButton
from snippets import Icon
from services.singletons import edit_mode
class DashButton(BaseButton):
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=Icon(icon_name="caffyne"),
            label="Dash",
            variant=variant or "icon+label",
            **kwargs,
        )
        self.connect("button-release-event", self._on_click)

    def _on_click(self, _widget, event):
        if not edit_mode.edit_mode:
            if event.button != 1:
                return False
            import services.singletons as singletons
            if singletons.bar_manager:
                singletons.bar_manager.toggle("Dash")
                self.get_parent().remove_style_class("active")
            return True