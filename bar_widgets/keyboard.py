from .base import BaseButton
from snippets import Icon
from services.singletons import wm
 
class KeyboardButton(BaseButton):
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=Icon(icon_name="keyboard", icon_size=16),
            label="",
            variant=variant or "icon+label",
            **kwargs,
        )
        if wm.is_available:
            wm.keyboard_layouts.connect(
                "notify::current-name",
                lambda obj, _: self._update_label(obj.current_name or ""),
            )
            self._update_label(wm.keyboard_layouts.current_name or "")
 