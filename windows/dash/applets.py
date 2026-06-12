from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from gi.repository import Gtk, Gdk
from utils.sounds import play_sound
import bar
from .components import DashPage
from snippets import Icon
import cairo

ALL_BEAN_DATA: list[tuple[str, str]] = [
    ("caffyne-duotone",                 "Dash"),
    ("magnifying-glass-duotone",        "Launcher"),
    ("dock-duotone",                    "Dock"),
    ("cards-three-duotone",             "Workspaces"),
    ("app-window-duotone",              "Focused"),
    ("dots-three-circle-duotone",       "Tray"),
    ("cpu-duotone",                     "Processes"),
    ("clock-duotone",                   "Clock"),
    ("calendar-blank-duotone",          "Calendar"),
    ("cloud-sun-duotone",               "Weather"),
    ("music-notes-duotone",             "Media"),
    ("calculator-duotone",              "Calculator"),
    ("bell-simple-duotone",             "Notifications"),
    ("sliders-horizontal-duotone",      "Settings"),
    ("power-duotone",                   "Session"),
    ("lightning-duotone",               "Energy"),
    ("keyboard-duotone",                "Keyboard"),
    ("wifi-high-duotone",               "Wifi"),
    ("bluetooth-duotone",               "Bluetooth"),
    ("speaker-simple-high-duotone",     "Volume"),
    ("seal-duotone",                    "Brightness"),
]

def create_dash_drag_surface(icon_name: str, key: str) -> cairo.ImageSurface:
    icon = Icon(icon_name=icon_name, icon_size=24)
    label = Label(label=key, style="font-size: 12px;")
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
    def __init__(self, icon_name: str, key: str, in_bar: bool = False):
        self.key = key
        self.key_icon = icon_name
        self.box = Box(
                style_classes=["dash-applet-item"],
                orientation="v",
                spacing=18,
                h_expand=False,
                h_align="center",
                v_expand=True,
                v_align="center",
                children=[
                    Icon(v_expand=True, v_align="end", icon_name=icon_name, icon_size=52),
                    Label(
                        label=key,
                        v_expand=True,
                        v_align="start",
                        h_align="center",
                        ellipsization="end",
                        max_chars_width=10,
                        style="font-size: 14px;",
                    ),
                ],
            )
        super().__init__(
            child=self.box
        )
        self.connect("drag-begin", self._on_drag_begin)
        self.connect("drag-data-get", self._on_drag_data_get)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("button-press-event", self._on_press)
        self.connect("button-release-event", self._on_release)
        self.connect("focus-in-event", self._on_focus_in)
        self.connect("focus-out-event", self._on_focus_out)
        self.set_in_bar(in_bar)
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
    def _on_drag_begin(self, widget, ctx):
        bar._dragging_key = self.key
        try:
            surface = create_dash_drag_surface(self.key_icon, self.key)
            Gtk.drag_set_icon_surface(ctx, surface)
        except Exception:
            pass
    def _on_drag_data_get(self, widget, ctx, data_obj, info, time):
        data_obj.set_text(f"applet:{self.key}", -1)

    def set_in_bar(self, in_bar: bool) -> None:
        ctx = self.get_child().get_style_context()
        if in_bar:
            ctx.add_class("in-bar")
            self.drag_source_unset()
        else:
            ctx.remove_class("in-bar")
            self.drag_source_set(
                Gdk.ModifierType.BUTTON1_MASK,
                [_TARGET],
                Gdk.DragAction.MOVE,
            )

class DashAppletPage(DashPage):
    def __init__(self, window, bar_manager):
        self.window = window
        self._bar_manager = bar_manager
        self._monitor_obj = None

        self._all_items = ALL_BEAN_DATA
        self._search_entry: Entry | None = None

        self._item_map: dict[str, DashAppletItem] = {
            key: DashAppletItem(icon, key, in_bar=False)
            for icon, key in self._all_items
        }

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

    def _get_all_active_keys(self) -> set[str]:
        bars = self._get_monitor_bars()
        if not bars:
            return set()
        return set().union(*(b.get_active_keys() for b in bars))

    def _get_monitor_bars(self):
        if self._monitor_obj is None:
            return []
        return [
            b for (mon, _), b in self._bar_manager._bars.items()
            if mon == self._monitor_obj
        ]
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

    def set_monitor(self, monitor_obj):
            if monitor_obj is None or monitor_obj is self._monitor_obj:
                return
            self._monitor_obj = monitor_obj
            self.refresh_bar_state()

    def refresh_bar_state(self) -> None:
        active = self._get_all_active_keys()
        for key, item in self._item_map.items():
            item.set_in_bar(key in active)

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
    def _get_monitor_bars(self):
        return [
            b for (mon, _), b in self._bar_manager._bars.items()
            if mon == self._monitor_obj
        ]
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