from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button

class SettingRow(Box):
    def __init__(self, name, settings, active, on_changed, **kwargs):
            self.on_changed = on_changed
            super().__init__(
                style_classes=["app-row"],
                children=[
                    Label(h_expand=True, h_align="start", label=name),
                    Box(style_classes=["option-selection-container"],
                        spacing=6,
                        children=[
                            Button(
                                label=setting,
                                style_classes=["option-selection-button", "active"] if setting == active else ["option-selection-button"],
                                on_clicked=lambda button: self.on_setting_changed(button),
                            ) for setting in settings
                        ]
                    )
                ]
            ) 
    def on_setting_changed(self, button):
        for child in self.children[1].children:
                child.remove_style_class("active")
        button.add_style_class("active")
        self.on_changed(button.get_label())