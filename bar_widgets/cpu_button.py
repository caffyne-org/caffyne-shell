from .base import ProgressButton
from snippets import Icon
from fabric.utils import invoke_repeater
import psutil
 
class CPUIndicatorButton(ProgressButton):
    """Circular variant — scale with icon inside + optional percent label."""
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=lambda size: Icon(icon_name="cpu-duotone", icon_size=size),
            label="0%",
            variant=variant or "icon+label",
            **kwargs,
        )
        invoke_repeater(1_000, self._update)
 
    def _update(self):
        cpu = psutil.cpu_percent()
        self._update_label(f"{round(cpu)}%")
        self._update_value(round(cpu))
        return True