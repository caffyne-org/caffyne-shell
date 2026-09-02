from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.stack import Stack
from .launcher import DashLauncherPage
from .applets import DashAppletPage, AppletDropZone
from .components import DashGroup, DashHeader
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell
from services.singletons import edit_mode
from snippets import DashReveal, enable_blur, disable_blur, free_blur
from services.desktop_applets import DesktopAppletService
import bar

display = Gdk.Display.get_default()

REVEAL_DURATION = 300

_PAGE_META = {
    "apps":    ("diamonds-four", "applets", True),
    "applets": ("stack",         "apps",    False),
}
_PAGE_LABELS = {
    "apps":    "Apps",
    "applets": "Applets",
}

_PAGES_WITH_SEARCH = {"apps", "applets"}


class DashDismissLayer(Window):
    def __init__(self, dash, on_dismiss, bar_manager, **kwargs):
        self._blur_ctx   = None
        self._dash       = dash
        self._on_dismiss = on_dismiss
        self._bar_manager = bar_manager

        self._left_zone = AppletDropZone(
            side="left",
            on_hover_commit=self._on_left_zone_commit,
        )
        self._right_zone = AppletDropZone(
            side="right",
            on_hover_commit=self._on_right_zone_commit,
        )

        self._dismiss_eb = EventBox()
        self._dismiss_eb.connect("button-release-event", self._on_button_press)

        zone_box = Box(
            orientation="h",
            h_expand=True,
            v_expand=True,
            children=[
                self._left_zone,
                self._dismiss_eb,
                self._right_zone,
            ],
        )
        self._dismiss_eb.set_hexpand(True)

        super().__init__(
            anchor="left right top bottom",
            layer="top",
            title="caffyne-shell-dash",
            keyboard_mode="none",
            style_classes=["dash"],
            visible=False,
            child=zone_box,
        )
        GtkLayerShell.set_exclusive_zone(self, -1)
        self.add_keybinding("escape", lambda: self._dash.toggle())


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
                1 for b in self._bar_manager._bars.values()
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
                    ),
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

    def _on_left_zone_commit(self):
        self._dash._switch_to_launcher_for_drop()

    def _on_right_zone_commit(self):
        self._dash._enter_canvas_mode()

    def show_drop_zones(self, key: str, show_left: bool = True, show_right: bool = True) -> None:
        if show_left:
            self._left_zone.show_zone()
        if show_right:
            self._right_zone.show_zone()

    def hide_drop_zones(self) -> None:
        self._left_zone.hide_zone()
        self._right_zone.hide_zone()


class Dash(Window):
    def __init__(self, bar_manager):
        self._opening              = False
        self._bar_manager          = bar_manager
        self._active_monitor       = None
        self._active_monitor_id: int | None = None
        self._in_canvas_mode: bool = False
        self._applet_drag_key: str | None = None

        self.header    = DashHeader(dash=self)
        self.h_group_1 = DashGroup(transition_type="slide-left-right")

        self.launcher   = DashLauncherPage(self)
        self.applets    = DashAppletPage(
            self,
            bar_manager=bar_manager,
            on_applet_drag_begin=self._on_applet_drag_begin,
            on_applet_drag_end=self._on_applet_drag_end,
        )
        self.dismiss_layer = DashDismissLayer(
            dash=self,
            on_dismiss=lambda: self.toggle(self._active_monitor),
            bar_manager=bar_manager,
        )

        self.launcher._applet_page_ref = self.applets

        self.h_group_1.add_named(self.launcher, "apps")
        self.h_group_1.add_named(self.applets,  "applets")

        self._name_to_page = {
            "apps":    self.launcher,
            "applets": self.applets,
        }

        self._main_box = Box(
            orientation="v",
            h_expand=True,
            v_expand=True,
            spacing=24,
            children=[self.header, self.h_group_1],
        )

        self.revealer = DashReveal(
            # open_duration=0.15,
            # close_duration=0.2,
            child=self._main_box,
            h_expand=True,
            v_expand=True,
        
        )

        super().__init__(
            layer="top",
            keyboard_mode="on-demand",
            child=self.revealer,
            visible=False,
        )

        self.add_keybinding("escape", lambda: self.toggle())
        self.connect("key-press-event", self._on_key_press)
        self.h_group_1.connect("notify::visible-child", self._on_stack_changed)

        DesktopAppletService.get_instance().connect(
            "applets-changed",
            lambda _, mid: self.applets.refresh_bar_state(),
        )
        DesktopAppletService.get_instance().connect(
            "canvas-drop-complete",
            self._on_service_canvas_drop_complete,
        )
        self._sync_header()


    def _on_applet_drag_begin(self, key: str, show_left: bool = True, show_right: bool = True) -> None:
        if not self.is_visible():
            return
        self._applet_drag_key = key
        self.dismiss_layer.show_drop_zones(key, show_left=show_left, show_right=show_right)

    def _on_applet_drag_end(self) -> None:
        self._applet_drag_key = None
        self.dismiss_layer.hide_drop_zones()
        self.launcher.exit_drag_receive_mode()
        if self._in_canvas_mode:
            self._exit_canvas_mode()


    def _enter_canvas_mode(self) -> None:
        key = self._applet_drag_key
        if key is None:
            return

        mid = self._active_monitor_id
        if mid is None:
            return

        self.dismiss_layer.hide_drop_zones()

        self.revealer.close()

        DesktopAppletService.get_instance().enter_canvas_mode(mid, key)
        self._in_canvas_mode = True

    def _exit_canvas_mode(self) -> None:
        mid = self._active_monitor_id
        if mid is not None:
            DesktopAppletService.get_instance().exit_canvas_mode(mid, restore=False)
        self._in_canvas_mode = False
        self.revealer.open()
        # self.dismiss_layer.switch()

    def _on_service_canvas_drop_complete(self, service, monitor_id: int) -> None:
        if monitor_id != self._active_monitor_id:
            return
        self._in_canvas_mode = False
        self.revealer.open()
        # self.dismiss_layer.switch()


    def _switch_to_launcher_for_drop(self):
        key = self._applet_drag_key
        if key is None:
            return
        self.dismiss_layer.hide_drop_zones()
        self.h_group_1.set_visible_child(self.launcher)
        self._sync_header()
        self.launcher.enter_drag_receive_mode(key)

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
        return "apps" if self.h_group_1.get_visible_child() is self.launcher else "applets"

    def _sync_header(self):
        name = self._current_page_name()
        icon, peer_name, current_on_left = _PAGE_META[name]
        peer_icon  = _PAGE_META[peer_name][0]
        peer_label = _PAGE_LABELS[peer_name]

        self.header.update(
            current_icon=icon,
            peer_icon=peer_icon,
            peer_label=peer_label,
            peer_h_callback=lambda: self.h_group_1.set_visible_child_name(peer_name),
            show_search=(name in _PAGES_WITH_SEARCH),
            current_on_left=current_on_left,
        )
        if name in _PAGES_WITH_SEARCH:
            self._name_to_page[name]._attach_search_entry(self.header._entry)

    def _on_stack_changed(self, *_):
        self._sync_header()
        on_applets = self.h_group_1.get_visible_child() is self.applets
        edit_mode.enable() if on_applets else edit_mode.disable()
        if self.h_group_1.get_visible_child() is not self.launcher:
            self.launcher.exit_drag_receive_mode()


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
            self.dismiss_layer.hide_drop_zones()
        else:
            self._opening = True
            if bar.is_applet_open:
                bar.set_open_applet(None)
            self._active_monitor = active_monitor

            self._active_monitor_id = None
            if active_monitor is not None:
                for i in range(display.get_n_monitors()):
                    if display.get_monitor(i) == active_monitor:
                        self._active_monitor_id = i
                        break

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
        if not self.is_visible():
            self.toggle(active_monitor)
        edit_mode.enable()

    def _hide(self):
        self.hide()
        self.launcher.exit_drag_receive_mode()
        if self._in_canvas_mode:
            self._exit_canvas_mode()
        self.h_group_1.set_visible_child(self.launcher)
        edit_mode.disable()
