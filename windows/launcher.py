from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.stack import Stack
from snippets import Applet, AppletPage, Icon, AnimatedScroll, HackedStack
from utils.dispatch import dispatch_app
from gi.repository import Gdk, GLib
from thefuzz import process, fuzz
from fabric.utils import get_desktop_applications, get_relative_path, DesktopApp
from fabric.widgets.grid import Grid
from user_options import user_options
import json
import os

USAGE_FILE = get_relative_path("../config/launcher_usage.json")

def load_usage() -> dict:
    try:
        with open(USAGE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_usage(usage: dict):
    os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
    with open(USAGE_FILE, "w") as f:
        json.dump(usage, f)

def increment_usage(app: DesktopApp):
    usage = load_usage()
    key = app.name or app.display_name
    usage[key] = usage.get(key, 0) + 1
    save_usage(usage)

def get_usage_count(app: DesktopApp, usage: dict) -> int:
    key = app.name or app.display_name
    return usage.get(key, 0)

class LauncherAppItem(Button):
    def __init__(self, app: DesktopApp, launcher):
        self._app = app
        self._launcher = launcher
        self.box = Box(
            style_classes=["launcher-app"],
            orientation="h",
            spacing=10,
            children=[
                Image(icon_name=app.icon_name, icon_size=28),
                Box(
                    orientation="v",
                    children=[
                        Label(
                            label=app.display_name or "",
                            h_align="start",
                            ellipsization="end",
                            max_chars_width=30,
                            style="font-size: 14px;",
                        ),
                        Label(
                            label=app.description or "",
                            h_align="start",
                            ellipsization="end",
                            max_chars_width=35,
                            style="font-size: 11px; opacity: 0.7;",
                        ),
                    ],
                ),
            ],
        )
        super().__init__(
            on_clicked=lambda *_: self.launch(),
            child=self.box
        )
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("focus-in-event", self._on_focus_in)
        self.connect("focus-out-event", self._on_focus_out)

    def _on_enter(self, *_):
        self.box.add_style_class("hover")

    def _on_leave(self, *_):
        self.box.remove_style_class("hover")
        self.box.remove_style_class("active")

    def _on_press(self, *_):
        self.box.add_style_class("active")

    def _on_release(self, *_):
        self.box.remove_style_class("active")

    def _on_focus_in(self, *_):
        self.box.add_style_class("focus")

    def _on_focus_out(self, *_):
        self.box.remove_style_class("focus")

    def launch(self):
        increment_usage(self._app)
        dispatch_app(self._app)
        self._launcher.toggle()


class LauncherGridItem(Button):
    def __init__(self, app: DesktopApp, launcher):
        self._app = app
        self._launcher = launcher
        self.box = Box(
            style_classes=["launcher-grid-app"],
            orientation="v",
            spacing=6,
            h_align="center",
            v_align="center",
            children=[
                Image(v_expand=True, v_align="end", icon_name=app.icon_name, icon_size=28),
                Label(
                    v_expand=True, v_align="start",
                    label=app.display_name or "",
                    h_align="center",
                    ellipsization="end",
                    max_chars_width=10,
                    style="font-size: 11px;",
                ),
            ],
        )
        super().__init__(
            on_clicked=lambda *_: self.launch(),
            child=self.box,
        )
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("focus-in-event", self._on_focus_in)
        self.connect("focus-out-event", self._on_focus_out)

    def _on_enter(self, *_):
        self.box.add_style_class("hover")

    def _on_leave(self, *_):
        self.box.remove_style_class("hover")
        self.box.remove_style_class("active")

    def _on_press(self, *_):
        self.box.add_style_class("active")

    def _on_release(self, *_):
        self.box.remove_style_class("active")

    def _on_focus_in(self, *_):
        self.box.add_style_class("focus")

    def _on_focus_out(self, *_):
        self.box.remove_style_class("focus")

    def launch(self):
        increment_usage(self._app)
        dispatch_app(self._app)
        self._launcher.toggle()


class LauncherApplet(Applet):
    def __init__(self, parent):
        self.window = parent
        self._all_apps = get_desktop_applications()
        self._grid_mode = user_options.launcher.grid

        self._list_box = Box(orientation="v", spacing=6)
        self._grid_box = Box(orientation="v", spacing=6)

        self._view_stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
        )
        self._view_stack.add_named(self._list_box, "list")
        self._view_stack.add_named(self._grid_box, "grid")
        self._view_stack.set_visible_child(self._grid_box if self._grid_mode else self._list_box)

        self._scrolled_window = AnimatedScroll(
            style_classes=["launcher-app-container"],
            v_expand=True,
            h_expand=True,
            overlay_scroll=True,
            kinetic_scroll=True,
            max_content_size=(324, 336),
        )
        self._scrolled_window.add(self._view_stack)

        self._app_count = Label(
            label=f"Apps · {len(self._all_apps)}",
            style_classes=["applet-header-label"],
        )

        self._view_toggle_icon = Icon(icon_name="list-dashes-duotone" if self._grid_mode else "squares-four-duotone", icon_size=16)
        self._view_toggle = Button(
            child=self._view_toggle_icon,
            style_classes=["applet-misc-button"],
            on_clicked=lambda *_: self._toggle_view(),
        )

        self._entry = Entry(
            h_expand=True,
            placeholder="Type to search...",
            on_changed=lambda e, *_: self._search(e.get_text()),
            on_activate=lambda *_: self._list_box.get_children()[0].launch() if not self._grid_mode and self._list_box.get_children() else None,
        )

        entry_box = Box(
            style_classes=["launcher-search"],
            spacing=8,
            children=[
                Icon(icon_name="magnifying-glass-duotone", icon_size=16),
                self._entry,
            ],
        )
        self._entry.connect("focus-in-event", lambda *_: entry_box.add_style_class("focused"))
        self._entry.connect("focus-out-event", lambda *_: entry_box.remove_style_class("focused"))


        results = Box(
            orientation="v",
            spacing=12,
            children=[entry_box, self._scrolled_window],
        )

        super().__init__(
            main_menu=AppletPage(
                first=True,
                title="Launcher",
                label=self._app_count,
                header_right_children=self._view_toggle,
                child=results,
            )
        )
        self.connect("realize", self._on_realize)
        self._entry.connect("key-press-event", self._on_entry_key_press)

    def _on_realize(self, *_):
        GLib.idle_add(lambda: self._view_stack.set_visible_child_name("grid" if self._grid_mode else "list"))
        self._render_apps(self._sorted_by_usage(self._all_apps))
        self.window.connect("notify::visible", self._on_visibility_changed)
        self.window.connect("key-press-event", self._on_key_press)

    def _toggle_view(self):
        self._grid_mode = not self._grid_mode
        user_options.launcher.grid = self._grid_mode
        user_options.save()
        icon = "list-dashes-duotone" if self._grid_mode else "squares-four-duotone"
        self._view_toggle_icon.set_icon_name(icon)
        self._view_stack.set_visible_child_name("grid" if self._grid_mode else "list")
        current_text = self._entry.get_text()
        if current_text:
            self._search(current_text)
        else:
            self._render_apps(self._sorted_by_usage(self._all_apps))

    def _on_key_press(self, _, event):
        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False
        if event.keyval in (
            Gdk.KEY_Escape, Gdk.KEY_Return, Gdk.KEY_Tab,
            Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right,
        ):
            return False
        if not self._entry.is_focus():
            self._entry.grab_focus()
            self._entry.set_position(-1)
        return False

    def _on_entry_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Down:
            if self._grid_mode:
                grid = self._grid_box.get_children()
                if grid:
                    grid[0].get_children()[-1].grab_focus()
            else:
                children = self._list_box.get_children()
                if children:
                    children[0].grab_focus()
            return True
        return False

    def _on_visibility_changed(self, *_):
        if not self.window.get_visible():
            self._grid_mode = user_options.launcher.grid
            self._view_toggle_icon.set_icon_name("list-duotone" if self._grid_mode else "squares-four-duotone")
            self._view_stack.set_visible_child_name("grid" if self._grid_mode else "list")
            self._all_apps = get_desktop_applications()
            self._entry.set_text("")
            self.window.set_focus(None)
            adj = self._scrolled_window.get_vadjustment()
            adj.set_value(adj.get_lower())
            for child in self._list_box.get_children():
                child.destroy()
            for child in self._grid_box.get_children():
                child.destroy()
            self._render_apps(self._sorted_by_usage(self._all_apps))

    def _sorted_by_usage(self, apps: list) -> list:
        usage = load_usage()
        return sorted(apps, key=lambda a: get_usage_count(a, usage), reverse=True)

    def _render_apps(self, apps: list):
        target = self._grid_box if self._grid_mode else self._list_box
        for child in target.get_children():
            child.destroy()
        self._app_count.label = f"Apps · {len(apps)}"

        if self._grid_mode:
            grid = Grid(column_homogeneous=True, column_spacing=6, row_spacing=6)
            grid.attach_flow([LauncherGridItem(a, self.window) for a in apps], columns=3)
            grid.show_all()
            target.add(grid)
        else:
            for app in apps:
                self._list_box.add(LauncherAppItem(app, self.window))
            self._list_box.show_all()

    def _search(self, query: str):
        if not query:
            self._render_apps(self._sorted_by_usage(self._all_apps))
            return

        usage = load_usage()

        raw_results = process.extract(
            query,
            self._all_apps,
            processor=lambda a: a.display_name if isinstance(a, DesktopApp) else a,
            scorer=fuzz.WRatio,
            limit=50,
        )

        filtered = [(app, score) for app, score in raw_results if score >= 60]

        boosted = sorted(
            filtered,
            key=lambda pair: (
                round(pair[1] / 5) * 10,
                get_usage_count(pair[0], usage),
            ),
            reverse=True,
        )

        adj = self._scrolled_window.get_vadjustment()
        adj.set_value(adj.get_lower())
        self._render_apps([app for app, _ in boosted])
