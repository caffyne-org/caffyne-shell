from .base import BaseButton
from snippets import Icon
 
class LauncherButton(BaseButton):

    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=Icon(icon_name="magnifying-glass"),
            label="Launch",
            variant=variant or "icon+label",
            **kwargs,
        )