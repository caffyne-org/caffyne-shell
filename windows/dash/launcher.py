from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from ..launcher import get_usage_count, load_usage, increment_usage
from thefuzz import process, fuzz
from utils.dispatch import dispatch_app
from fabric.utils import get_desktop_applications, DesktopApp
from .components import DashPage
from gi.repository import Gdk

class DashLauncherAppItem(Button):
    def __init__(self, app: DesktopApp, launcher):
        self._app = app
        self._launcher = launcher
        self.box = Box(
                style_classes=["dash-launcher-app"],
                orientation="v",
                spacing=18,
                h_expand=False,
                h_align="center",
                v_expand=True,
                v_align="center",
                children=[
                    Image(v_expand=True, v_align="end", icon_name=app.icon_name, icon_size=52),
                    Label(
                        v_expand=True, v_align="start",
                        label=app.display_name or "",
                        h_align="center",
                        ellipsization="end",
                        max_chars_width=10,
                        style="font-size: 14px;",
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

class DashLauncherPage(DashPage):
    def __init__(self, window):
        self.window = window
        self._all_apps = get_desktop_applications()
        self._search_entry: Entry | None = None

        super().__init__(grid_children=[])

        self.connect("realize", self._on_realise)
        self._render_apps(self._sorted_by_usage(self._all_apps))

    def _attach_search_entry(self, entry: Entry):
        if self._search_entry is entry:
            return
        if self._search_entry is not None:
            try:
                self._search_entry.disconnect_by_func(self._search)
                self._search_entry.disconnect_by_func(self._on_entry_key_press)
            except Exception as e:
                print(f"[launcher] disconnect failed: {e}")
        self._search_entry = entry
        entry.connect("changed", self._search)
        entry.connect("activate", lambda *_: self.grid.get_children()[-1].launch())
        entry.connect("key-press-event", self._on_entry_key_press)

    def _on_entry_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Down:
            children = self.grid.get_children()
            if children:
                children[-1].grab_focus()
            return True
        return False

    def _on_realise(self, *_):
        self.window.connect("notify::visible", self._on_visibility_changed)

    def _on_visibility_changed(self, *_):
        if not self.window.get_visible():
            self._all_apps = get_desktop_applications()
            if self._search_entry:
                self._search_entry.set_text("")
            self._render_apps(self._sorted_by_usage(self._all_apps))
            adj = self.scroll.get_vadjustment()
            adj.set_value(adj.get_lower())
            
    def _sorted_by_usage(self, apps: list) -> list:
        usage = load_usage()
        return sorted(apps, key=lambda a: get_usage_count(a, usage), reverse=True)

    def _render_apps(self, apps: list):
        for child in self.grid.get_children():
            child.destroy()
        self.grid.attach_flow([DashLauncherAppItem(a, self.window) for a in apps], columns=6)

    def _search(self, entry):
        query = entry.get_text()
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
                round(pair[1] / 10) * 10,
                get_usage_count(pair[0], usage),
            ),
            reverse=True,
        )

        adj = self.scroll.get_vadjustment()
        adj.set_value(adj.get_lower())
        self._render_apps([app for app, _ in boosted])