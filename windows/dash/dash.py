from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from .launcher import DashLauncherPage
from .applets import DashAppletPage
from .components import DashGroup, DashHeader
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell
from services.singletons import edit_mode
from .wallpapers import DashWallpaperPage
from .themes import DashThemePage
from snippets import DashReveal, enable_blur, disable_blur, free_blur
import bar
display = Gdk.Display.get_default()

REVEAL_DURATION = 300

_PAGE_META = {
    "apps":   ("diamonds-four-duotone",           "applets",    "themes-wallpapers", "paint-brush-broad-duotone",       True),
    "applets":    ("stack-duotone",       "apps",   "themes-wallpapers", "paint-brush-broad-duotone",       False),
    "wallpapers": ("images-duotone", "themes",     "apps-applets",      "dash-duotone",   True),
    "themes":     ("swatches-duotone",             "wallpapers", "apps-applets",      "dash-duotone",   False),
}
_PAGE_LABELS = {
    "apps":   "Apps",
    "applets":    "Applets",
    "wallpapers": "Wallpapers",
    "themes":     "Themes",
}

_PAGES_WITH_SEARCH = {"apps", "applets"}

class DashDismissLayer(Window):
    def __init__(self, dash, on_dismiss, bar_manager, **kwargs):
        self.event_box = EventBox()
        self._blur_ctx = None
        self._dash = dash
        self._on_dismiss = on_dismiss
        self._bar_manager = bar_manager
        super().__init__(
            anchor="left right top bottom",
            layer="top",
            title="caffyne-shell-dash",
            keyboard_mode="none",
            style_classes=["dash"],
            visible=False,
            child=self.event_box,
        )

        self.event_box.connect("button-release-event", self._on_button_press)

    def _on_button_press(self, widget, event: Gdk.EventButton):
        if event.button == 1:
            self._on_dismiss()
            return True

        if event.button == 3:
            active_monitor = self._dash._active_monitor
            if active_monitor is None:
                return True

            monitor_id = next(
                (i for i in range(display.get_n_monitors())
                if display.get_monitor(i) == active_monitor),
                None,
            )

            bar_count = sum(
                1
                for b in self._bar_manager._bars.values()
                if b.monitor_id == monitor_id
            )

            menu = Gtk.Menu()

            if bar_count < 2:
                add_item = Gtk.MenuItem(label="Add Bar")
                add_item.connect(
                    "activate",
                    lambda _: (
                        self._bar_manager.add_bar_for_monitor(active_monitor),
                        self._bar_manager.set_bars_overlay(active_monitor),
                    )
                )
                menu.append(add_item)
            else:
                item = Gtk.MenuItem(label="Maximum bars (2) reached on this monitor")
                item.set_sensitive(False)
                menu.append(item)

            menu.show_all()
            menu.popup_at_pointer(event)
            return True

        return False
class Dash(Window):
    def __init__(self, bar_manager):
        self._opening = False
        self._bar_manager = bar_manager
        self._active_monitor = None
        self.header = DashHeader()
        self.h_group_1 = DashGroup(transition_type="slide-left-right")
        self.h_group_2 = DashGroup(transition_type="slide-left-right")
        self.v_stack   = DashGroup(transition_type="slide-up-down")

        self.launcher   = DashLauncherPage(self)
        self.applets = DashAppletPage(self, bar_manager=bar_manager)
        self.themes     = DashThemePage(bar_manager=bar_manager)
        self.wallpapers = DashWallpaperPage()
        self.dismiss_layer = DashDismissLayer(dash=self, on_dismiss=lambda: self.toggle(self._active_monitor), bar_manager=bar_manager)

        self.h_group_1.add_named(self.launcher,   "apps")
        self.h_group_1.add_named(self.applets,    "applets")
        self.h_group_2.add_named(self.wallpapers, "wallpapers")
        self.h_group_2.add_named(self.themes,     "themes")
        self.v_stack.add_named(self.h_group_2,    "themes-wallpapers")
        self.v_stack.add_named(self.h_group_1,    "apps-applets")
        self.v_stack.set_visible_child(self.h_group_1)
        self._name_to_page = {
            "apps":   self.launcher,
            "applets":    self.applets,
            "wallpapers": self.wallpapers,
            "themes":     self.themes,
        }

        self._main_box = Box(
            orientation="v",
            h_expand=True,
            v_expand=True,
            v_align="center",
            h_align="center",
            spacing=52,
            children=[self.header, self.v_stack],
        )

        self.revealer = DashReveal(
            child=self._main_box,
            h_expand=True,
            v_expand=True,
        )

        super().__init__(
            # monitor=monitor,
            # style_classes=["dash"],
            layer="top",
            keyboard_mode="on-demand",
            # anchor="top right bottom left",
            child=self.revealer,
            visible=False,
        )
        self.add_keybinding("escape", lambda: self.toggle())
        self.connect("key-press-event", self._on_key_press)
        self.h_group_1.connect("notify::visible-child", self._on_stack_changed)
        self.h_group_2.connect("notify::visible-child", self._on_stack_changed)
        self.v_stack.connect("notify::visible-child",   self._on_v_stack_changed)
        # niri.connect("notify::active-window", self._on_window_changed)
        # niri.connect("notify::workspaces", self._on_workspace_changed)
        self._sync_header()
        GtkLayerShell.set_exclusive_zone(self, -1)

    def _on_key_press(self, _, event):
        if self._current_page_name() not in _PAGES_WITH_SEARCH:
            return False
        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False
        if event.keyval in (
            Gdk.KEY_Escape, Gdk.KEY_Return, Gdk.KEY_Tab,
            Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right,
        ):
            return False

        entry = self.header._entry
        if not entry or not entry.get_visible():
            return False

        if not entry.is_focus():
            entry.grab_focus()
            entry.set_position(-1)

        return False
    
    def _current_page_name(self) -> str:
        v_child = self.v_stack.get_visible_child()
        if v_child is self.h_group_1:
            return "apps" if self.h_group_1.get_visible_child() is self.launcher else "applets"
        else:
            return "wallpapers" if self.h_group_2.get_visible_child() is self.wallpapers else "themes"

    def _sync_header(self):
        name = self._current_page_name()
        icon, peer_name, v_target, v_icon, current_on_left = _PAGE_META[name]
        peer_icon  = _PAGE_META[peer_name][0]
        peer_label = _PAGE_LABELS[peer_name]
        h_group    = self.h_group_1 if name in ("apps", "applets") else self.h_group_2

        self.header.update(
            current_icon=icon,
            peer_icon=peer_icon,
            peer_label=peer_label,
            peer_h_callback=lambda: h_group.set_visible_child_name(peer_name),
            v_icon=v_icon,
            v_callback=lambda: self.v_stack.set_visible_child_name(v_target),
            show_search=(name in _PAGES_WITH_SEARCH),
            current_on_left=current_on_left,
            h_switcher_on_right=(name in ("wallpapers", "themes")),
        )
        if name in _PAGES_WITH_SEARCH:
            self._name_to_page[name]._attach_search_entry(self.header._entry)

    def _on_stack_changed(self, *_):
        self._sync_header()
        on_applets = self.h_group_1.get_visible_child() is self.applets and self.v_stack.get_visible_child() is not self.h_group_2
        edit_mode.enable() if on_applets else edit_mode.disable()

    def _on_v_stack_changed(self, *_):
        self._on_stack_changed()
        self.h_group_1.set_visible_child(self.launcher)
        self.h_group_2.set_visible_child(self.wallpapers)
        
    def toggle(self, active_monitor=None):
        if self.is_visible():
            self.revealer.close(on_done=self._hide)
            if self.dismiss_layer._blur_ctx:
                disable_blur(self.dismiss_layer._blur_ctx)
                free_blur(self.dismiss_layer._blur_ctx)
                self.dismiss_layer._blur_ctx = None
            if self._active_monitor is not None:
                self._bar_manager.set_bars_top(self._active_monitor)
            self.dismiss_layer.hide()
        else:
            self._opening = True
            if bar.is_applet_open:
                bar.set_open_applet(None)
            self._active_monitor = active_monitor
            self.applets.set_monitor(active_monitor)
            self.dismiss_layer.show()
            if not self.dismiss_layer._blur_ctx:
                self.dismiss_layer._blur_ctx = enable_blur(self.dismiss_layer)
            self.show()
            self.revealer.open()

            if active_monitor is not None:
                self._bar_manager.set_bars_overlay(active_monitor)

            GLib.timeout_add(300, self._clear_opening)

    def _clear_opening(self):
        self._opening = False
        return False

    def toggle_applets(self, active_monitor=None):
        self.h_group_1.set_visible_child(self.applets)
        self.v_stack.set_visible_child(self.h_group_1)
        if not self.is_visible():
            self.toggle(active_monitor)
        edit_mode.enable()

    def toggle_wallpapers(self, active_monitor=None):
        self.h_group_2.set_visible_child(self.wallpapers)
        self.v_stack.set_visible_child(self.h_group_2)
        if not self.is_visible():
            self.toggle(active_monitor)

    def toggle_themes(self, active_monitor=None):
        self.v_stack.set_visible_child(self.h_group_2)
        self.h_group_2.set_visible_child(self.themes)
        if not self.is_visible():
            self.toggle(active_monitor)

    def _hide(self):
        self.hide()
        self.v_stack.set_visible_child(self.h_group_1)
        self.h_group_1.set_visible_child(self.launcher)
        edit_mode.disable()