from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.eventbox import EventBox
from gi.repository import Gtk, Gdk, GLib
from utils.sounds import play_sound
import bar
from services.singletons import plugins
from .components import DashPage
from snippets import Icon
from user_options import user_options
from desktop_applets import DESKTOP_APPLET_SIZES
import cairo

ALL_BEAN_DATA: list[tuple[str, str]] = [
    ("caffyne",                 "Dash"),
    ("magnifying-glass",        "Launcher"),
    ("dock",                    "Dock"),
    ("cards-three",             "Workspaces"),
    ("app-window",              "Focused"),
    ("dots-three-circle",       "Tray"),
    ("cpu",                     "Processes"),
    ("clock",                   "Clock"),
    ("calendar-blank",          "Calendar"),
    ("cloud-sun",               "Weather"),
    ("music-notes",             "Media"),
    ("calculator",              "Calculator"),
    ("bell-simple",             "Notifications"),
    ("sliders-horizontal",      "Settings"),
    ("power",                   "Session"),
    ("lightning",               "Energy"),
    ("keyboard",                "Keyboard"),
    ("wifi-high",               "Wifi"),
    ("bluetooth",               "Bluetooth"),
    ("speaker-simple-high",     "Volume"),
    ("seal",                    "Brightness"),
]


def create_dash_drag_surface(icon_name: str, key: str) -> cairo.ImageSurface:
    icon = Icon(icon_name=icon_name, icon_size=24)
    label = Label(label=key, style="font-size: 11px;")
    box = Box(
        orientation="h",
        spacing=8,
        style_classes=["dash-drag-pill"],
        children=[icon, label],
    )
    window = Gtk.OffscreenWindow()
    window.add(box)
    window.show_all()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
    alloc = box.get_allocation()
    surface = cairo.ImageSurface(cairo.Format.ARGB32, alloc.width, alloc.height)
    cr = cairo.Context(surface)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.rectangle(0, 0, alloc.width, alloc.height)
    cr.fill()
    box.draw(cr)
    window.destroy()
    return surface

_TARGET = Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)


class DashAppletItem(Button):
    def __init__(self, icon_name: str, key: str, on_drag_end: callable = None):
        self.key = key
        self.key_icon = icon_name
        self._on_drag_end_cb = on_drag_end

        # Placement indicator row — icons appear/disappear via refresh_state()
        self._bar_indicator = Icon(
            icon_name="bar",
            icon_size=16,
            visible=False,
            tooltip_text="In bar",
        )
        self._launcher_indicator = Icon(
            icon_name="dash",
            icon_size=16,
            visible=False,
            tooltip_text="In launcher",
        )
        self._desktop_indicator = Icon(
            icon_name="monitor",
            icon_size=16,
            visible=False,
            tooltip_text="On desktop",
        )
        self._indicator_row = Box(
            orientation="h",
            spacing=6,
            h_align="center",
            style_classes=["applet-indicators"],
            children=[self._bar_indicator, self._launcher_indicator, self._desktop_indicator],
        )

        self.box = Box(
            orientation="v",
            spacing=10,
            children=[
                Icon(v_expand=True, v_align="end", icon_name=icon_name, icon_size=52),
                Label(
                    label=key,
                    v_expand=False,
                    v_align="center",
                    h_align="center",
                    ellipsization="end",
                    max_chars_width=10,
                    style="font-size: 14px; margin-bottom: 6px;",
                ),
                self._indicator_row,
            ],
        )
        super().__init__(
            style_classes=["dash-applet-item"],
            child=self.box,
            h_expand=False,
            h_align="center",
            v_expand=True,
            v_align="center",
        )

        self.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [_TARGET],
            Gdk.DragAction.MOVE,
        )
        self.connect("drag-begin", self._on_drag_begin)
        self.connect("drag-data-get", self._on_drag_data_get)
        self.connect("drag-end", self._on_drag_end)
        self.connect("drag-failed", self._on_drag_failed)
        # self.connect("enter-notify-event", self._on_enter)
        # self.connect("leave-notify-event", self._on_leave)
        # self.connect("button-press-event", self._on_press)
        # self.connect("button-release-event", self._on_release)
        # self.connect("focus-in-event", self._on_focus_in)
        # self.connect("focus-out-event", self._on_focus_out)


    # def _on_enter(self, *_):
    #     self.box.add_style_class("hover")

    # def _on_leave(self, *_):
    #     self.box.remove_style_class("hover")
    #     self.box.remove_style_class("active")

    # def _on_press(self, *_):
    #     self.box.add_style_class("active")

    # def _on_release(self, *_):
    #     self.box.remove_style_class("active")

    # def _on_focus_in(self, *_):
    #     self.box.add_style_class("focus")

    # def _on_focus_out(self, *_):
    #     self.box.remove_style_class("focus")


    def _on_drag_begin(self, widget, ctx):
        bar._dragging_key = self.key
        try:
            surface = create_dash_drag_surface(self.key_icon, self.key)
            Gtk.drag_set_icon_surface(ctx, surface)
        except Exception:
            pass
        if hasattr(self, '_page_drag_begin_cb') and self._page_drag_begin_cb:
            self._page_drag_begin_cb(self.key)

    def _on_drag_data_get(self, widget, ctx, data_obj, info, time):
        data_obj.set_text(f"applet:{self.key}", -1)

    def _on_drag_end(self, widget, ctx):
        bar._dragging_key = None
        if self._on_drag_end_cb:
            self._on_drag_end_cb()

    def _on_drag_failed(self, widget, ctx, result):
        bar._dragging_key = None
        if self._on_drag_end_cb:
            self._on_drag_end_cb()
        return False


    def refresh_state(self, in_bar: bool, in_launcher: bool, in_desktop: bool, has_desktop: bool) -> None:
        self._bar_indicator.set_visible(True)
        self._launcher_indicator.set_visible(has_desktop)
        self._desktop_indicator.set_visible(has_desktop)

        self._bar_indicator.set_opacity(0.35 if in_bar else 1.0)
        self._launcher_indicator.set_opacity(0.35 if in_launcher else 1.0)
        self._desktop_indicator.set_opacity(0.35 if in_desktop else 1.0)

        all_filled = in_bar and (in_launcher if has_desktop else True) and (in_desktop if has_desktop else True)
        self.box.get_style_context().add_class("in-bar") if all_filled else self.box.get_style_context().remove_class("in-bar")
        self.set_sensitive(not all_filled)



class AppletDropZone(EventBox):
    HOVER_DELAY = 450

    def __init__(self, side: str, on_hover_commit: callable):
        assert side in ("left", "right")
        self._side = side
        self._on_hover_commit = on_hover_commit
        self._hover_timer: int | None = None

        icon_name = "dash" if side == "left" else "monitor"
        label_text = "Dash" if side == "left" else "Desktop"

        inner = Box(
            orientation="v",
            spacing=12,
            h_align="center",
            v_align="center",
            v_expand=True,
            children=[
                Icon(icon_name=icon_name, icon_size=32),
                Label(label=label_text, style="font-size: 14px; padding: 0px 12px;"),
            ],
        )

        super().__init__(
            style_classes=["applet-drop-zone", f"applet-drop-zone-{side}"],
            visible=False,
            child=inner,
        )

        self.drag_dest_set(
            0,
            [_TARGET],
            Gdk.DragAction.MOVE,
        )
        self.connect("drag-motion", self._on_drag_motion)
        self.connect("drag-leave", self._on_drag_leave)
        self.connect("drag-data-received", self._on_drag_received)

    def _on_drag_motion(self, widget, ctx, x, y, time):
        Gdk.drag_status(ctx, Gdk.DragAction.MOVE, time)
        self.add_style_class("hovered")
        if self._hover_timer is None:
            self._hover_timer = GLib.timeout_add(self.HOVER_DELAY, self._commit_hover)
        return True

    def _on_drag_leave(self, widget, ctx, time):
        self.remove_style_class("hovered")
        self._cancel_hover_timer()

    def _commit_hover(self) -> bool:
        self._hover_timer = None
        self._on_hover_commit()
        return False  # don't repeat

    def _cancel_hover_timer(self):
        if self._hover_timer is not None:
            GLib.source_remove(self._hover_timer)
            self._hover_timer = None

    def _on_drag_received(self, widget, ctx, x, y, data_obj, info, time):
        Gtk.drag_finish(ctx, self._side == "right", False, time)

    def show_zone(self):
        self.set_visible(True)

    def hide_zone(self):
        self._cancel_hover_timer()
        self.remove_style_class("hovered")
        self.set_visible(False)


class DashAppletPage(DashPage):
    def __init__(self, window, bar_manager, on_applet_drag_begin: callable = None, on_applet_drag_end: callable = None):
        self.window = window
        self._bar_manager = bar_manager
        self._monitor_obj = None
        self._monitor_id: int | None = None
        self._on_applet_drag_begin = on_applet_drag_begin
        self._on_applet_drag_end = on_applet_drag_end

        self._all_items = ALL_BEAN_DATA
        self._search_entry: Entry | None = None

        self._item_map: dict[str, DashAppletItem] = {}
        for icon, key in self._all_items:
            item = DashAppletItem(icon, key, on_drag_end=self._handle_drag_end)
            item._page_drag_begin_cb = self._handle_drag_begin
            self._item_map[key] = item

        super().__init__(grid_children=[list(self._item_map.values())])

        self.connect(
            "realize",
            lambda *_: self.window.connect("notify::visible", self._on_visibility_changed)
        )

        self.grid.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [_TARGET],
            Gdk.DragAction.MOVE,
        )
        self.grid.connect("drag-data-received", self._on_grid_drag_received)
        self.grid.connect("drag-motion", self._on_grid_drag_motion)
        plugins.connect("plugin-enabled", self._on_plugin_enabled)
        plugins.connect("plugin-disabled", self._on_plugin_disabled)

    def _on_plugin_enabled(self, _, name: str) -> None:
        # Add to item list and map if not already there
        mod = plugins._loaded.get(name)
        if mod is None:
            return
        icon = getattr(mod, "ICON", "placeholder")
        if name not in self._item_map:
            item = DashAppletItem(icon, name, on_drag_end=self._handle_drag_end)
            item._page_drag_begin_cb = self._handle_drag_begin
            self._item_map[name] = item
        if not any(k == name for _, k in self._all_items):
            self._all_items.append((icon, name))
        self._render_items(self._all_items)
        self.refresh_bar_state()

    def _on_plugin_disabled(self, _, name: str) -> None:
        # Remove from item map and list
        item = self._item_map.pop(name, None)
        if item:
            item.destroy()
        self._all_items = [(icon, k) for icon, k in self._all_items if k != name]
        self._render_items(self._all_items)
        self.refresh_bar_state()

    def _handle_drag_begin(self, key: str) -> None:
        in_launcher  = key in self._get_launcher_keys()
        has_desktop  = key in DESKTOP_APPLET_SIZES
        in_desktop   = key in self._get_desktop_keys()

        show_left  = has_desktop and not in_launcher
        show_right = has_desktop and not in_desktop

        if self._on_applet_drag_begin:
            self._on_applet_drag_begin(key, show_left=show_left, show_right=show_right)

    def _handle_drag_end(self) -> None:
        if self._on_applet_drag_end:
            self._on_applet_drag_end()

    # ── monitor ────────────────────────────────────────────────────────────

    def set_monitor(self, monitor_obj) -> None:
        if monitor_obj is None or monitor_obj is self._monitor_obj:
            return
        self._monitor_obj = monitor_obj
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            if display.get_monitor(i) == monitor_obj:
                self._monitor_id = i
                break
        self.refresh_bar_state()

    def _get_monitor_bars(self):
        if self._monitor_obj is None:
            return []
        return [
            b for (mon, _), b in self._bar_manager._bars.items()
            if mon == self._monitor_obj
        ]

    def _get_all_active_keys(self) -> set[str]:
        bars = self._get_monitor_bars()
        if not bars:
            return set()
        return set().union(*(b.get_active_keys() for b in bars))

    def _get_launcher_keys(self) -> set[str]:
        return {
            e["key"]
            for e in user_options.desktop_applets.get_applets()
            if e.get("type", "applet") == "applet" and "key" in e
        }


    def refresh_bar_state(self) -> None:
        bar_keys      = self._get_all_active_keys()
        launcher_keys = self._get_launcher_keys()
        desktop_keys  = self._get_desktop_keys()

        for key, item in self._item_map.items():
            has_desktop = key in DESKTOP_APPLET_SIZES
            item.refresh_state(
                in_bar=key in bar_keys,
                in_launcher=key in launcher_keys,
                in_desktop=key in desktop_keys,
                has_desktop=has_desktop,
            )
    def _get_desktop_keys(self) -> set[str]:
        mid = self._monitor_id
        if mid is None:
            return set()
        return {e["key"] for e in user_options.desktop_canvas.get_applets(mid)}

    def _attach_search_entry(self, entry: Entry):
        if self._search_entry is entry:
            return
        if self._search_entry is not None:
            try:
                self._search_entry.disconnect_by_func(self._search)
                self._search_entry.disconnect_by_func(self._on_entry_key_press)
            except Exception as e:
                print(f"[applets] disconnect failed: {e}")
        self._search_entry = entry
        entry.connect("changed", self._search)
        entry.connect("key-press-event", self._on_entry_key_press)

    def _on_entry_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Down:
            children = self.grid.get_children()
            if children:
                children[-1].grab_focus()
            return True
        return False


    def _on_grid_drag_motion(self, widget, ctx, x, y, time):
        Gdk.drag_status(ctx, Gdk.DragAction.MOVE, time)
        return True

    def _on_grid_drag_received(self, widget, ctx, x, y, data_obj, info, time):
        payload = data_obj.get_text() or ""
        parts = payload.split(":")
        monitor_bars = self._get_monitor_bars()

        if parts[0] == "applet":
            Gtk.drag_finish(ctx, False, False, time)
            return

        if not monitor_bars:
            Gtk.drag_finish(ctx, False, False, time)
            return

        from bar import WidgetWrapper, GroupWrapper

        if len(parts) == 4:
            src_monitor_id_str, bar_index_str, src_section_name, src_index_str = parts
            try:
                src_index = int(src_index_str)
                bar_index = int(bar_index_str)
                src_monitor_id = int(src_monitor_id_str)
            except ValueError:
                Gtk.drag_finish(ctx, False, False, time)
                return

            monitor_id = self._get_monitor_bars()[0].monitor_id
            if src_monitor_id != monitor_id:
                Gtk.drag_finish(ctx, False, False, time)
                return

            owning_bar = next(
                (b for b in monitor_bars if b.bar_index == bar_index),
                None
            )
            if owning_bar is None:
                Gtk.drag_finish(ctx, False, False, time)
                return

            section = owning_bar.sections.get(src_section_name)
            if section is None:
                Gtk.drag_finish(ctx, False, False, time)
                return
            children = section.get_children()
            if src_index >= len(children):
                Gtk.drag_finish(ctx, False, False, time)
                return
            wrapper = children[src_index]
            if isinstance(wrapper, (WidgetWrapper, GroupWrapper)):
                if isinstance(wrapper, WidgetWrapper):
                    wrapper.destroy_popup()
                else:
                    wrapper.destroy_popups()
                section.remove(wrapper)
                wrapper.destroy()
                play_sound("widget-removed")
                Gtk.drag_finish(ctx, True, False, time)
                owning_bar.sync_config()
                return

        elif len(parts) == 6 and parts[4] == "child":
            src_monitor_id_str, src_section_name = parts[0], parts[1]
            try:
                src_monitor_id = int(src_monitor_id_str)
                bar_index = int(parts[2])
                group_index = int(parts[3])
                child_index = int(parts[5])
            except ValueError:
                Gtk.drag_finish(ctx, False, False, time)
                return

            monitor_id = self._get_monitor_bars()[0].monitor_id
            if src_monitor_id != monitor_id:
                Gtk.drag_finish(ctx, False, False, time)
                return

            owning_bar = next(
                (b for b in monitor_bars if b.bar_index == bar_index),
                None
            )
            if owning_bar is None:
                Gtk.drag_finish(ctx, False, False, time)
                return

            section = owning_bar.sections.get(src_section_name)
            if section is None:
                Gtk.drag_finish(ctx, False, False, time)
                return
            children = section.get_children()
            if group_index >= len(children):
                Gtk.drag_finish(ctx, False, False, time)
                return
            group = children[group_index]
            if not isinstance(group, GroupWrapper):
                Gtk.drag_finish(ctx, False, False, time)
                return

            from bar import build_widget
            remaining_key = group.widget_keys[1 - child_index]
            remaining_var = group.widget_variants[1 - child_index]
            group_pos = section.get_children().index(group)

            group.destroy_popups()
            section.remove(group)

            remaining_widget = build_widget(remaining_key, owning_bar.monitor_id, owning_bar.vertical, remaining_var)
            if remaining_widget:
                remaining_wrapper = WidgetWrapper(remaining_key, remaining_widget, variant=remaining_var)
                section.add(remaining_wrapper)
                section.reorder_child(remaining_wrapper, group_pos)
            play_sound("widget-removed")
            Gtk.drag_finish(ctx, True, False, time)
            owning_bar.sync_config()
            return

        Gtk.drag_finish(ctx, False, False, time)


    def _on_visibility_changed(self, *_):
        if not self.window.get_visible():
            if self._search_entry:
                self._search_entry.set_text("")


    def _render_items(self, items: list[tuple[str, str]]):
        for child in self.grid.get_children():
            self.grid.remove(child)
        visible_items = [self._item_map[key] for _, key in items if key in self._item_map]
        self.grid.attach_flow(visible_items, columns=6)
        self.grid.show_all()

    def _search(self, entry):
        query = entry.get_text().strip().lower()
        if not query:
            self._render_items(self._all_items)
            return
        self._render_items([
            (icon, key) for icon, key in self._all_items
            if query in key.lower()
        ])
        adj = self.scroll.get_vadjustment()
        adj.set_value(adj.get_lower())


    def on_launcher_applet_changed(self) -> None:
        self.refresh_bar_state()
