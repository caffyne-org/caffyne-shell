from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from snippets import AnimatedScroll, HackedStack
from typing import Callable

SINGLE_TAB_HEIGHT = 276
MULTI_TAB_HEIGHT  = 228

class TabMenu(AnimatedScroll):
    """A scrollable container for tab content."""
    def __init__(self, child, width: int = 324, height: int = MULTI_TAB_HEIGHT, **kwargs):
        self._width = width
        super().__init__(
            style_classes=["scrollable"],
            style=f"min-width: {width}px; min-height: {height}px;",
            child=child,
            max_content_size=(width, height),
            overlay_scroll=True,
            kinetic_scroll=True,
            **kwargs,
        )

    def set_height(self, height: int):
        self.set_style(f"min-width: {self._width}px; min-height: {height}px;")
        self.set_max_content_size((self._width, height))


class TabStack(Box):
    """A tabbed interface with switcher buttons and stack navigation."""
    def __init__(
        self,
        transition_type: str = "slide-left-right",
        transition_duration: int = 200,
        **kwargs,
    ):
        self.tab_switcher = Box(
            spacing=6,
            h_align="center",
            style_classes=["qs-device-switcher"],
        )
        self.tab_stack = HackedStack(
            style_classes=["applet-stack"],
            transition_type=transition_type,
            bezier_curve=(0.34, 1.3, 0.64, 1.0),
            duration=0.45,
        )
        self._tab_buttons: list[tuple[str, Button, Callable | None]] = []

        super().__init__(
            orientation="v",
            spacing=12,
            children=[self.tab_switcher, self.tab_stack],
            **kwargs,
        )

    def _tab_menus(self) -> list[TabMenu]:
        menus = []
        for name, _, _ in self._tab_buttons:
            child = self.tab_stack.get_child_by_name(name)
            if isinstance(child, TabMenu):
                menus.append(child)
        return menus

    def _sync_switcher_visibility(self):
        single = len(self._tab_buttons) == 1
        self.tab_switcher.set_visible(not single)
        height = SINGLE_TAB_HEIGHT if single else MULTI_TAB_HEIGHT
        for menu in self._tab_menus():
            menu.set_height(height)

    def add_tab(
        self,
        name: str,
        label: str,
        content,
        on_switch: Callable[[str], None] | None = None,
    ) -> Button:
        self.tab_stack.add_named(content, name)

        is_first = len(self._tab_buttons) == 0
        tab_button = Button(
            style_classes=["qs-device-switcher-button"] + (["active"] if is_first else []),
            child=Label(label=label, ellipsization="end"),
            on_clicked=lambda *_: self.switch_to_tab(name),
            h_expand=True,
            h_align="fill",
        )

        self._tab_buttons.append((name, tab_button, on_switch))
        self.tab_switcher.add(tab_button)

        if is_first:
            self.tab_stack.set_visible_child_name(name)

        self._update_button_widths()
        self._sync_switcher_visibility()
        return tab_button

    def switch_to_tab(self, name: str):
        for tab_name, button, on_switch in self._tab_buttons:
            if tab_name == name:
                button.add_style_class("active")
                if on_switch:
                    on_switch(name)
            else:
                button.remove_style_class("active")
        self.tab_stack.set_visible_child_name(name)

    def remove_tab(self, name):
        for i, (tab_name, button, _) in enumerate(self._tab_buttons):
            if tab_name == name:
                self.tab_switcher.remove(button)
                button.destroy()
                self._tab_buttons.pop(i)
                break

        child = self.tab_stack.get_child_by_name(name)
        if child:
            self.tab_stack.remove(child)
            child.destroy()

        self._update_button_widths()
        self._sync_switcher_visibility()

    def clear_tabs(self):
        for name, button, _ in self._tab_buttons:
            self.tab_switcher.remove(button)
            child = self.tab_stack.get_child_by_name(name)
            if child:
                self.tab_stack.remove(child)
        self._tab_buttons.clear()
        self._update_button_widths()
        self._sync_switcher_visibility()

    def _update_button_widths(self):
        count = len(self._tab_buttons)
        if not count:
            return
        if count == 1:
            _, button, _ = self._tab_buttons[0]
            button.set_style("")
            return
        button_width = 318 / count
        for _, button, _ in self._tab_buttons:
            button.set_style(f"min-width: {button_width}px;")