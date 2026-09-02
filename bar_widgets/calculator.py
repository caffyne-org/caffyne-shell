from .base import BaseButton
from snippets import Icon
 
class CalculatorButton(BaseButton):
    VARIANTS = []
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(icon=Icon(icon_name="calculator", icon_size=16), variant=variant or "icon", **kwargs)