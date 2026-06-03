from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from .launcher import DashLauncherPage
from .applets import DashAppletPage
from .components import DashGroup, DashHeader
from gi.repository import Gdk, GLib, GtkLayerShell
from services.singletons import edit_mode, wm
from .wallpapers import DashWallpaperPage
from .themes import DashThemePage
from snippets import DashReveal, enable_blur, disable_blur, free_blur
import bar
display = Gdk.Display.get_default()

REVEAL_DURATION = 300

_PAGE_META = {
    "apps":   ("stack-duotone",           "applets",    "themes-wallpapers", "paint-brush-broad-duotone",       True),
    "applets":    ("diamonds-four-duotone",       "apps",   "themes-wallpapers", "paint-brush-broad-duotone",       False),
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

class Dash(Window):
    def __init__(self, monitor, bar_manager):
        self._opening = False
        self.monitor_obj = display.get_monitor(monitor)
        self._bar_manager = bar_manager
        self.header = DashHeader()

        self.h_group_1 = DashGroup(transition_type="slide-left-right")
        self.h_group_2 = DashGroup(transition_type="slide-left-right")
        self.v_stack   = DashGroup(transition_type="slide-up-down")

        self.launcher   = DashLauncherPage(self)
        self.applets = DashAppletPage(self, bar_manager=bar_manager, monitor_obj=self.monitor_obj)
        self.themes     = DashThemePage(bar_manager=bar_manager)
        self.wallpapers = DashWallpaperPage()

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
        self._blur_ctx = None

        super().__init__(
            monitor=monitor,
            style_classes=["dash"],
            layer="top",
            title="caffyne-shell-dash",
            keyboard_mode="on-demand",
            anchor="top right bottom left",
            child=self.revealer,
            visible=False,
        )
        self.connect("button-press-event", self._on_bg_click)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
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

    def _apply_blur(self):
        if not self._blur_ctx:
            self._blur_ctx = enable_blur(self)
        
    def toggle(self):
        if self.is_visible():
            self.remove_style_class("dash")
            self.revealer.close(on_done=self._hide)
            if self._blur_ctx:
                disable_blur(self._blur_ctx)
                free_blur(self._blur_ctx)
                self._blur_ctx = None
            self._bar_manager.set_bars_top(self.monitor_obj)
        else:
            self._opening = True
            if bar.is_applet_open:
                bar.set_open_applet(None)
            self.show()
            self.add_style_class("dash")
            self._apply_blur()
            self.revealer.open()

            self._bar_manager.set_bars_overlay(self.monitor_obj)

            GLib.timeout_add(300, self._clear_opening)

    def _clear_opening(self):
        self._opening = False
        return False

    def toggle_applets(self):
        """Open dash straight to the applets page and enable edit mode."""
        self.h_group_1.set_visible_child(self.applets)
        self.v_stack.set_visible_child(self.h_group_1)
        if not self.is_visible():
            self.toggle()
        edit_mode.enable()

    def _hide(self):
        self.hide()
        self.v_stack.set_visible_child(self.h_group_1)
        self.h_group_1.set_visible_child(self.launcher)
        edit_mode.disable()
    def _on_workspace_changed(self, *_):
        if self.is_visible():
            self.toggle()
    def _on_window_changed(self, *_):
        if self._opening:
            return
        if self.is_visible():
            self.toggle()

    def _on_bg_click(self, widget, event):
        if event.button != 1:
            return False
        if self.revealer.progress < 1.0:
            return False
        
        alloc = self._main_box.get_allocation()
        if (alloc.x <= event.x <= alloc.x + alloc.width and
            alloc.y <= event.y <= alloc.y + alloc.height):
            return False
        self.toggle()
        return False
