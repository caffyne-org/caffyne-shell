from fabric.widgets.box import Box
from fabric.widgets.label import Label
from snippets import SmoothSwitch


class SwitchRow(Box):
    def __init__(self, name, toggled, on_toggle, **kwargs):
            super().__init__(
                style_classes=["app-row"],
                children=[
                    Label(h_expand=True, h_align="start", label=name),
                    SmoothSwitch(v_expand=True, v_align="center", style_classes=["dash-switch"], width=48, on_user_toggle=on_toggle)
                ]
            ) 
            self.children[1].set_active(toggled)