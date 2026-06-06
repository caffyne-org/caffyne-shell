from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.grid import Grid
from snippets import Icon, HackedStack, AnimatedScroll

class DashHeader(CenterBox):
    """
    Single shared header for the whole Dash.

    Left:   [current-page icon btn]  [peer icon + label btn]
    Center: search entry (hidden unless the active page needs it)
    Right:  [vertical-switch btn]
    """

    def __init__(self):
        self._entry = Entry(h_expand=True, h_align="fill", placeholder="Type to search...")
        self._entry_box = Box(
            style_classes=["launcher-search"],
            spacing=8,
            visible=False,
            children=[
                Icon(icon_name="magnifying-glass-duotone", icon_size=16),
                self._entry,
            ],
        )
        self._entry.connect("focus-in-event", lambda *_: self._entry_box.add_style_class("focused"))
        self._entry.connect("focus-out-event", lambda *_: self._entry_box.remove_style_class("focused"))
        self._left_box = Box(style_classes=["dash-header-button-container"], orientation="h", spacing=4)
        self._right_box = Box(style_classes=["dash-header-button-container"], orientation="h", spacing=4)

        super().__init__(
            h_expand=False,
            h_align="center",
            style="min-width: 1104px",
            start_children=self._left_box,
            center_children=self._entry_box,
            end_children=self._right_box,
        )
    def update(
        self,
        *,
        current_icon: str,
        peer_icon: str,
        peer_label: str,
        peer_h_callback,
        v_icon: str,
        v_callback,
        show_search: bool = False,
        current_on_left: bool = True,
        h_switcher_on_right: bool = False,
    ):
        for child in self._left_box.get_children():
            self._left_box.remove(child)
        for child in self._right_box.get_children():
            self._right_box.remove(child)

        current_btn = Button(
            style_classes=["dash-header-button", "active"],
            child=Icon(icon_name=current_icon),
        )
        peer_btn = Button(
            style_classes=["dash-header-button"],
            child=Box(
                orientation="h",
                spacing=6,
                children=[
                    Icon(icon_name=peer_icon),
                    Label(label=peer_label),
                ],
            ),
            on_pressed=lambda _: peer_h_callback(),
        )

        if h_switcher_on_right:

            v_btn = Button(
                style_classes=["dash-header-button"],
                child=Icon(icon_name=v_icon),
                on_pressed=lambda _: v_callback(),
            )
            self._left_box.add(v_btn)
            self._left_box.show_all()

            if current_on_left:
                self._right_box.add(current_btn)
                self._right_box.add(peer_btn)
            else:
                self._right_box.add(peer_btn)
                self._right_box.add(current_btn)
            self._right_box.show_all()
        else:

            if current_on_left:
                self._left_box.add(current_btn)
                self._left_box.add(peer_btn)
            else:
                self._left_box.add(peer_btn)
                self._left_box.add(current_btn)
            self._left_box.show_all()

            v_btn = Button(
                style_classes=["dash-header-button"],
                child=Icon(icon_name=v_icon),
                on_pressed=lambda _: v_callback(),
            )
            self._right_box.add(v_btn)
            self._right_box.show_all()

        self._entry_box.set_visible(show_search)
        if not show_search:
            self._entry.set_text("")

class DashGrid(Grid):
    def __init__(self, children):
        super().__init__(

            column_homogeneous=False,
            column_spacing=12,
            row_spacing=12,
        )
        for child in children:
            self.attach_flow(child, 6)

class DashPage(Box):
    """Grid-based page — no header of its own."""

    def __init__(self, grid_children):
        self.grid = DashGrid(children=grid_children)
        self.scroll = AnimatedScroll(
            h_expand=False,
            h_align="center",
            style_classes=["dash-grid"],
            child=self.grid,
            max_content_size=(1104, 604),
            fade_distance=56,
            overlay_scroll=True,
            kinetic_scroll=True,
        )
        super().__init__(
            orientation="v",
            v_align="center",
            spacing=60,
            children=[
                self.scroll
            ],
        )

class DashGroup(HackedStack):
    def __init__(self, transition_type):
        super().__init__(
            style_classes=["dash-stack"],
            h_expand=False,
            h_align="center",
            transition_type=transition_type,
            bezier_curve=(0.34, 1.4, 0.64, 1.0),
            duration=0.5,
        )