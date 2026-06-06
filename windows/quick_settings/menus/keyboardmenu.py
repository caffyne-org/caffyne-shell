from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from snippets import ClippingScrolledWindow
from .menu import QSAppletPage
from services.singletons import wm


class KeyboardButton(Button):
    def __init__(self, name: str, index: int, **kwargs):
        super().__init__(
            style_classes=(
                ["qs-kb-menu-button", "qs-checkmark-active"]
                if name == wm.keyboard_layouts.current_name
                else ["qs-kb-menu-button"]
            ),
            v_align="center",
            child=Label(label=name, v_expand=True, v_align="center"),
            on_clicked=lambda *_: wm.keyboard_layouts.switch_layout(str(index)),
            **kwargs,
        )


class KeyboardMenu(QSAppletPage):
    def __init__(self, parent=None, stack=None, **kwargs):
        self.layouts = Box(orientation="v", spacing=6)

        super().__init__(
            title="Keyboard",
            stack=stack,
            child=ClippingScrolledWindow(
                style_classes=["scrollable"],
                style="min-width: 324px; min-height: 276px;",
                max_content_size=(324, 276),
                child=self.layouts,
                overlay_scroll=True,
            ),
            **kwargs,
        )

        wm.keyboard_layouts.connect("notify::names", lambda *_: self._update_layouts())
        wm.keyboard_layouts.connect("notify::current-name", lambda *_: self._update_layouts())
        self._update_layouts()

    def _update_layouts(self):
        names = wm.keyboard_layouts.names or []
        self.layouts.children = [
            KeyboardButton(name, i) for i, name in enumerate(names)
        ]