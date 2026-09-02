from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.widgets.label import Label
from snippets import Icon, HackedStack, ClippingScrolledWindow
class AppPage(ClippingScrolledWindow):
    def __init__(self, name: str, title: str, items, **kwargs):
        self.name = name
        super().__init__(
            child=Box(
                style_classes=["app-page"],
                orientation="v",
                spacing=32,
                children=[
                    Label(h_align="start", style_classes=["app-page-title"], label=title)
                ] + items,
                **kwargs,
            )
        )

class AppSection(Stack):

    def __init__(
        self,
        name: str,
        icon: str,
        label: str,
        pages: list,
        **kwargs,
    ):
        # if len(pages) != 3:
        #     raise ValueError("AppSection requires exactly 3 AppPage instances.")

        self.name = name
        self.icon_name = icon
        self.label = label
        self._pages = pages
        self._current_index = 0

        super().__init__(orientation="v", spacing=8, **kwargs)

        for page in pages:
            self.add_named(page, page.name)

        self._show_page(0)

        self.sidebar_item = SidebarItem(
            icon_name=icon,
            label=label,
        )


    def _show_page(self, index: int):
        self._current_index = index
        self.set_visible_child_name(self._pages[index].name)


    @property
    def page_names(self) -> tuple[str, str, str]:
        return tuple(p.name for p in self._pages)

    def show_page(self, index: int):
        """Switch to page 0, 1, or 2."""
        self._show_page(index)

    def get_current_index(self) -> int:
        return self._current_index

class SidebarItem(Button):
    def __init__(self, icon_name: str, label: str, **kwargs):
        super().__init__(
            orientation="h",
            style_classes=["app-sidebar-item"],
            child=Box(
                spacing=8,
                children=[
                    Box(
                        children=[Icon(icon_name)],
                        style_classes=["app-sidebar-item-icon"],
                    ),
                    Box(
                    children=[Button(label=label, style_classes=["app-sidebar-item-label"])],
                    style_classes=["app-sidebar-item-label-box"],
                ),
            ]),
            **kwargs,
        )

class AppSidebar(Revealer):
    def __init__(self, **kwargs):
        self._box = Box(style_classes=["app-sidebar"], v_expand=True, v_align="fill", orientation="v", spacing=8)
        super().__init__(
            v_expand=True,
            v_align="fill",
            child=self._box,
            orientation="v",
            spacing=8,
            child_revealed=True,
            **kwargs,
        )
    def toggle(self):
        self.set_reveal_child(not self.get_reveal_child())
    def add_item(self, item: SidebarItem):
        self._box.add(item)

class AppHeader(CenterBox):

    def __init__(self, sidebar: AppSidebar, app, **kwargs):
        self._app = app

        self._page_buttons = [
            Button(
                label="",
                style_classes=["header-page-btn"],
                on_pressed=lambda _, i=i: self._app.show_page(i),
            )
            for i in range(3)
        ]

        super().__init__(
            orientation="h",
            spacing=8,
            style_classes=["app-header"],
            start_children=Button(
                style_classes=["app-header-button"],
                child=Icon("sidebar"),
                on_pressed=lambda *_: sidebar.toggle(),
            ),
            center_children=self._page_buttons,
            end_children=Button(
                style_classes=["app-header-button"],
                child=Icon("x"),
                on_pressed=lambda *_: app.toggle(),
            ),
            **kwargs,
        )

    def update_for_section(self, section: AppSection):
        names = section.page_names
        for i, btn in enumerate(self._page_buttons):
            if i < len(names):
                btn.set_label(names[i])
                btn.set_no_show_all(False)
                btn.show()
            else:
                btn.set_label("")
                btn.set_no_show_all(True)
                btn.hide()

        self._highlight(section.get_current_index())

    def highlight_page(self, index: int):
        self._highlight(index)


    def _highlight(self, index: int):
        for i, btn in enumerate(self._page_buttons):
            btn.remove_style_class("active")
            if i == index:
                btn.add_style_class("active")