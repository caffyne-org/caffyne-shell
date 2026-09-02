from fabric.widgets.box import Box
from fabric.widgets.label import Label

class InfoRow(Box):
    def __init__(self, name, info, **kwargs):
            super().__init__(
                style_classes=["app-row"],
                children=[
                    Label(h_expand=True, h_align="start", label=name),
                    Label(h_expand=True, h_align="end", label=info)
                ]
            )