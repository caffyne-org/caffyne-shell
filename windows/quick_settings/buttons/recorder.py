from fabric.widgets.label import Label
from snippets import Icon
from services.singletons import recorder, wm
from .button import QSButton
 
class RecordButton(QSButton):
    def __init__(self, **kwargs):
        super().__init__(
            icon=Icon(icon_name="record", icon_size=16),
            label=Label(label="Screen Record"),
            on_activate=lambda _: recorder.start(output=wm.active_output),
            on_deactivate=lambda _: recorder.stop(),
            **kwargs,
        )
 
        recorder.connect(
            "notify::active",
            lambda obj, _: setattr(self, "active", obj.active),
        )
        self.active = recorder.active
 