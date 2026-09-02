from fabric.widgets.window import Window
from fabric.widgets.box import Box
from fabric.widgets.stack import Stack
from snippets import ClippingBox
from .components import AppHeader, AppSidebar, AppSection


class SectionContainer(Stack):
    def __init__(self, **kwargs):
        super().__init__(v_expand=True, v_align="fill", h_expand=True, h_align="fill", style_classes=["app-section-container"], transition_type="crossfade", **kwargs)

    def add_section(self, section: AppSection):
        self.add_named(section, section.name)

    def show_section(self, name: str):
        self.set_visible_child_name(name)


class App(Window):
    def __init__(self, **kwargs):
        self._sections: list[AppSection] = []
        self._active_section: AppSection | None = None

        self.sidebar = AppSidebar()
        self.header = AppHeader(sidebar=self.sidebar, app=self)
        self.section_container = SectionContainer()

        super().__init__(
            title="caffyne-shell-app",
            keyboard_mode="on-demand",
            child=Box(
                style_classes=["app-window"],
                orientation="v",
                spacing=0,
                children=[
                    self.header,
                    Box(
                        orientation="h",
                        v_expand=True,
                        v_align="fill",
                        children=[self.sidebar, self.section_container],
                    ),
                ],
            ),
            **kwargs,
        )

    def add_section(self, section: AppSection):
        self._sections.append(section)

        section.sidebar_item.connect("pressed", lambda *_: self.activate_section(section.name))

        self.sidebar.add_item(section.sidebar_item)
        self.section_container.add_section(section)

        if len(self._sections) == 1:
            self.activate_section(section.name)

    def activate_section(self, name: str):
        section = self._find_section(name)
        if section is None:
            return

        self._active_section = section
        self.section_container.show_section(name)
        self.header.update_for_section(section)

        for s in self._sections:
            s.sidebar_item.remove_style_class("active")
            if s.name == name:
                s.sidebar_item.add_style_class("active")

    def show_page(self, index: int):
        if self._active_section is None:
            return
        self._active_section.show_page(index)
        self.header.highlight_page(index)

    def _find_section(self, name: str) -> AppSection | None:
        return next((s for s in self._sections if s.name == name), None)