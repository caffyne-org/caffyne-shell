from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from snippets import Icon
from .hacktk.hacktk import HackedStack


class AppletPage(Box):
    def __init__(
        self,
        child: Box,
        first: bool = False,
        stack=None,
        header_right_children=None,
        header_left_children=None,
        title: str | None = None,
        label: Label | None = None,
        **kwargs,
    ):
        self.is_first = first
        self.header_right_children = header_right_children
        self.header_left_children = header_left_children
        self.header_label = label if label else Label(
            label=title or "",
            style="padding: 8px 10px; font-size: 14px;",
        )

        super().__init__(
            style_classes=["applet-menu"],
            orientation="v",
            children=[child],
            **kwargs,
        )


class Applet(Box):
    def __init__(self, main_menu: AppletPage, **kwargs):
        self.main_menu = main_menu

        self._back_button = Button(
            style_classes=["applet-misc-button"],
            child=Icon(icon_name="chevron-left"),
            on_clicked=lambda *_: self._stack.set_visible_child_name("main"),
        )
        self._back_button.set_visible(False)

        self._title_slot = Box()
        self._right_slot = Box()
        self._left_extra_slot = Box()

        self.header = CenterBox(
            start_children=Box(
                spacing=0,
                children=[self._back_button, self._left_extra_slot, self._title_slot],
            ),
            end_children=self._right_slot,
        )

        self._stack = HackedStack(
            style_classes=["applet-stack"],
            transition_type="slide-left-right",
            bezier_curve=(0.34, 1.3, 0.64, 1.0),
            duration=0.45,
        )
        self._stack.add_named(main_menu, "main")
        self._stack.connect("notify::visible-child", self._on_page_changed)

        super().__init__(
            orientation="v",
            spacing=12,
            children=[self.header, self._stack],
            **kwargs,
        )

        self.connect("realize", self._on_realise)
        self._update_header(main_menu)

    def _on_realise(self, *_):
        self.get_toplevel().connect("notify::visible", self._on_visibility_changed)

    def _on_visibility_changed(self, *_):
        self._stack.set_visible_child(self.main_menu)

    def _update_header(self, page: AppletPage):
        self._back_button.set_visible(not page.is_first)

        # Update title
        for child in self._title_slot.get_children():
            self._title_slot.remove(child)
        self._title_slot.add(page.header_label)
        self._title_slot.show_all()

        # Update left extra slot
        for child in self._left_extra_slot.get_children():
            self._left_extra_slot.remove(child)
        if page.header_left_children:
            self._left_extra_slot.add(page.header_left_children)
            self._left_extra_slot.show_all()

        # Update right slot
        for child in self._right_slot.get_children():
            self._right_slot.remove(child)
        if page.header_right_children:
            self._right_slot.add(page.header_right_children)
            self._right_slot.show_all()

    def _on_page_changed(self, *_):
        page = self._stack.get_visible_child()
        if isinstance(page, AppletPage):
            self._update_header(page)

    def add_menu(self, name: str, menu) -> None:
        self._stack.add_named(menu(stack=self._stack), name)

    def set_visible_child_name(self, name: str) -> None:
        self._stack.set_visible_child_name(name)

    def set_visible_child(self, child) -> None:
        self._stack.set_visible_child(child)

    def get_visible_child(self):
        return self._stack.get_visible_child()

    def get_visible_child_name(self) -> str:
        return self._stack.get_visible_child_name()

    def get_child_by_name(self, name):
        return self._stack.get_child_by_name(name)

    def add_named(self, widget, name: str) -> None:
        self._stack.add_named(widget, name)