from .base import BaseButton
from snippets import Icon
 
class SessionButton(BaseButton):
    VARIANTS = []
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(icon=Icon(icon_name="power", icon_size=16), variant=variant or "icon", **kwargs)
 