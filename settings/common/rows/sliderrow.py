from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from snippets import FlatScale

class SliderRow(Box):
    def __init__(self, name, value, on_changed: None = None, on_released: None = None, value_formatter: None = None,
                 min_value: float = 0.2, max_value: float = 1.0, step: float = 0.05, **kwargs):
            self.scale = FlatScale(
                style_classes=["scale"],
                min_value=min_value,
                max_value=max_value,
                step=step,
                value=value,
                on_value_changed=on_changed if on_changed else None,
                value_formatter=value_formatter if value_formatter else (lambda val: f"{round(val * 100)}%"),
                h_expand=True,
            )
            super().__init__(
                style_classes=["app-row"],
                children=[
                    Label(h_expand=True, h_align="start", label=name),
                    Box(style="min-width: 224px;", children=[self.scale])
                ]
            )
            if on_released:
                self.scale.connect("button-release-event", on_released)
