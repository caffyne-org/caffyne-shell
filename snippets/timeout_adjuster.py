from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from snippets import Icon

class TimeoutAdjuster(Box):
    def __init__(
        self,
        initial_minutes: int,
        icon_name: str = "",
        on_change: callable | None = None,
        label_visible: bool = True,
        **kwargs,
    ):
        self.minutes = initial_minutes
        self.on_change = on_change

        self.minutes_label = Label(
            label=f"{self.minutes}m",
            style_classes=["timeout-minutes"],
            h_align="center",
            h_expand=True,
            visible=label_visible,
        )

        super().__init__(
            style_classes=["timeout-adjuster"],
            h_align="center",
            h_expand=True,
            spacing=1,
            children=[Box(
                spacing=8,
                children=[
                    child for child in [
                        Icon(style_classes=["timeout-adjust-icon"], icon_name=icon_name, icon_size=16) if icon_name else None,
                        Button(
                            h_expand=True,
                            h_align="start",
                            style_classes=["timeout-adjust-button", "left"],
                            child=Icon(icon_name="minus", icon_size=16, h_align="start", h_expand=True),
                            on_clicked=lambda *_: self._adjust(-1),
                        ),
                    ] if child is not None
                ],
            ),
            self.minutes_label,
            Button(
                h_expand=True,
                h_align="end",
                style_classes=["timeout-adjust-button", "right"],
                child=Icon(icon_name="plus", icon_size=16, h_align="end", h_expand=True),
                on_clicked=lambda *_: self._adjust(1),
            ),
            ],
            **kwargs,
        )

    def set_minutes(self, minutes: int):
        self.minutes = max(1, minutes)
        self.minutes_label.set_label(f"{self.minutes}m")
        if self.on_change:
            self.on_change(self.minutes)
            
    def _adjust(self, delta: int):
        self.minutes = max(1, self.minutes + delta)
        self.minutes_label.set_label(f"{self.minutes}m")
        if self.on_change:
            self.on_change(self.minutes)