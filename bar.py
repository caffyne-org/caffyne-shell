import cairo
import math
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.eventbox import EventBox
from snippets import HackedRevealer, enable_blur, set_blur_regions_from_widget, disable_blur, free_blur, AppletReveal
from snippets.applet_reveal import _ease_out_expo
from snippets.blur.blur import set_blur_regions
from snippets.blur.region_trace import Rect
from gi.repository import Gdk, Gtk, GLib, GtkLayerShell
from bar_widgets import (
    LauncherButton, BluetoothButton, BatteryButton, CalendarButton, ClockButton,
    CPUIndicatorButton, NetworkButton, NotificationButton, Workspaces,
    NiriClientTitle, Media, QuickSettingsButton, WeatherButton, VolumeButton,
    CalculatorButton, SessionButton, KeyboardButton, SystemTray, Dock, BrightnessButton, DashButton
)
from user_options import user_options
from services.singletons import edit_mode, wm
from windows import (
    CalculatorApplet, CalendarApplet, ClockApplet, NotificationHistoryApplet,
    WeatherApplet, MediaApplet, QuickSettings, LauncherApplet, ProcessMonitorApplet, WifiApplet, 
    LogoutApplet, NotificationWindow, Dash, OSD, AudioApplet, PowerApplet, KeyboardApplet, BluetoothApplet
)
from snippets.popupwindow import PopupWindow
from utils.helpers import popup_with_blur
from utils.monitors import get_connector_from_monitor_id
from utils.sounds import play_sound

BAR_WIDGETS: dict[str, type] = {
    "Launcher":      LauncherButton,
    "Processes":     CPUIndicatorButton,
    "Energy":        BatteryButton,
    "Bluetooth":     BluetoothButton,
    "Notifications": NotificationButton,
    "Settings":      QuickSettingsButton,
    "Clock":         ClockButton,
    "Media":         Media,
    "Workspaces":    Workspaces,
    "Weather":       WeatherButton,
    "Volume":        VolumeButton,
    "Tray":          SystemTray,
    "Calendar":      CalendarButton,
    "Focused":       NiriClientTitle,
    "Wifi":          NetworkButton,
    "Session":       SessionButton,
    "Calculator":    CalculatorButton,
    "Keyboard":      KeyboardButton,
    "Dock":          Dock,
    "Brightness":    BrightnessButton,
    "Dash":          DashButton,
}

APPLET_WIDGETS: dict[str, type] = {
    "Settings":      QuickSettings,
    "Notifications": NotificationHistoryApplet,
    "Clock":         ClockApplet,
    "Media":         MediaApplet,
    "Weather":       WeatherApplet,
    "Calendar":      CalendarApplet,
    "Volume":        AudioApplet,
    "Session":       LogoutApplet,
    "Wifi":          WifiApplet,
    "Bluetooth":     BluetoothApplet,
    "Energy":        PowerApplet,
    "Calculator":    CalculatorApplet,
    "Keyboard":      KeyboardApplet,
    "Launcher":      LauncherApplet,
    "Processes":     ProcessMonitorApplet,
}

INCOMPATIBLE_GROUPS: set[frozenset] = {
    frozenset({"Settings", "Wifi"}),
    frozenset({"Settings", "Bluetooth"}),
    frozenset({"Settings", "Energy"}),
    frozenset({"Settings", "Volume"}),
    frozenset({"Settings", "Keyboard"}),
    frozenset({"Settings", "Session"}),
    frozenset({"Processes", "Launcher"}),
}
from plugin_loader import load_plugins
from windows.dash.applets import ALL_BEAN_DATA

load_plugins(BAR_WIDGETS, APPLET_WIDGETS, INCOMPATIBLE_GROUPS, ALL_BEAN_DATA)

def can_group(key_a: str, key_b: str) -> bool:
    return frozenset({key_a, key_b}) not in INCOMPATIBLE_GROUPS

TARGET = Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)
open_applet: AppletWindow | None = None
_dragging_key: str | None = None
_dragging_widget: Gtk.Widget | None = None

def set_open_applet(applet: AppletWindow | None):
    global open_applet
    if open_applet is not None and open_applet is not applet and open_applet.is_visible():
        open_applet.toggle()
    open_applet = applet

def is_applet_open(*keys: str) -> bool:
    if open_applet is None or not open_applet.is_visible():
        return False
    return any(
        k in keys
        for k in getattr(open_applet, '_keys', [])
    )

def build_widget(key: str, monitor_id: int, vertical: bool, variant: str | None = None) -> Gtk.Widget | None:
    cls = BAR_WIDGETS.get(key)
    if cls is None:
        print(f"[bar] Unknown widget key: {key!r}")
        return None
    return cls(monitor_id, vertical=vertical, variant=variant)

def create_surface_from_widget(widget: Gtk.Widget) -> cairo.ImageSurface:
    alloc = widget.get_allocation()
    surface = cairo.ImageSurface(cairo.Format.ARGB32, alloc.width, alloc.height)
    cr = cairo.Context(surface)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.rectangle(0, 0, alloc.width, alloc.height)
    cr.fill()
    widget.draw(cr)
    return surface

def _make_variant_picker(
    key: str,
    current_variant: str,
    bar: "Bar",
    anchor_widget: Gtk.Widget,
    on_select: callable,
) -> AppletWindow | None:
    cls = BAR_WIDGETS.get(key)
    variants = getattr(cls, "VARIANTS", None)
    if not variants or len(variants) <= 1:
        return None

    def build_content(window):
        stack = Box(orientation="v", spacing=4, style_classes=["variant-picker"])
        for v in variants:
            instance = build_widget(key, bar.monitor_id, bar.vertical, v)
            if instance is None:
                continue
            row = EventBox(h_expand=True, h_align="center", style_classes=["variant-row"])
            if v == current_variant:
                row.get_style_context().add_class("active-variant")
            row.add(instance)
            def on_click(_w, event, chosen=v):
                if event.button != 1:
                    return False
                on_select(chosen)
                window.toggle()
                return True
            row.connect("button-release-event", on_click)
            stack.add(row)
        return stack
    offset = bar.get_allocated_height()
    margin = f"{offset}px 0px 0px 0px" if bar.alignment == "top" else f"0px 0px {offset}px 0px"
    return AppletWindow(
        applet=[lambda w: build_content(w)],
        alignment=bar.alignment,
        parent=bar,
        pointing_to=anchor_widget,
        layer="overlay",
        exclusivity="none",
        keyboard_mode="on-demand",
        style_classes=["applet-window", "variant-picker-window"],
        margin=margin,
        visible=False,
    )

class DropPlaceholder(Box):
    def __init__(self, vertical: bool = False):
        super().__init__(
            orientation="v" if vertical else "h",
            style_classes=["drop-placeholder"],
        )

class DismissLayer(Window):
    def __init__(self, on_dismiss, **kwargs):
        self.event_box = EventBox()
        super().__init__(
            anchor="left right top bottom",
            layer="top",
            keyboard_mode="none",
            child=self.event_box,
            **kwargs,
        )

        self.event_box.connect("button-release-event", lambda *_: on_dismiss())

class AppletWindow(PopupWindow):
    def __init__(self, applet, alignment: str = "top", **kwargs):
        self._keys = None
        self._blur_ctx = None
        self._alignment = alignment
        applets = applet if isinstance(applet, list) else [applet]

        def build_content(window, alignment):
            children = [a(window) for a in applets]
            self._content_box = Box(
                orientation="v",
                spacing=18,
                children=children
            )
            self._content_box.add_style_class("applet")
            return self._content_box

        animation_direction = "up" if alignment == "bottom" else "down"

        self.revealer = AppletReveal(

            direction=animation_direction,
            child=Box(children=[build_content(self, alignment)])
        )

        self.main = Box(style="min-height: 1px;", children=[self.revealer])
        self.dismiss_layer = DismissLayer(on_dismiss=self.toggle)

        super().__init__(title="caffyne-shell-applet", child=self.main, **kwargs)
        self.add_keybinding("escape", lambda: self.toggle())
        GtkLayerShell.set_exclusive_zone(self, -1)

    def toggle(self):
        if self.is_visible():
            self.revealer.close(
                on_done=lambda: self._finish_close()
            )

            self.dismiss_layer.set_visible(False)
            self.revealer._progress_cb = None

        else:
            set_open_applet(self)
            self.dismiss_layer.set_visible(True)
            self.show()
            self.revealer.open()
            if user_options.theme.blur:
                self._start_animated_blur()
            self.set_focus(None)
    def _finish_close(self):
        GLib.timeout_add(50, self.hide)

        if self._blur_ctx:
            disable_blur(self._blur_ctx)
            free_blur(self._blur_ctx)
            self._blur_ctx = None
    def _trace_content_box(self, erode=10):
        alloc = self._content_box.get_allocation()
        w, h = alloc.width, alloc.height

        if w <= 0 or h <= 0:
            return [Rect(0, 0, w, h)]

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(surface)

        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        style_ctx = self._content_box.get_style_context()

        Gtk.render_background(style_ctx, cr, erode, erode, w - erode * 2, h - erode * 2)

        data    = surface.get_data()
        stride  = surface.get_stride()
        accuracy = 1
        alpha_threshold = 20

        raw: list[Rect] = []
        for y in range(0, h, accuracy):
            step_h = min(accuracy, h - y)
            x = 0
            while x < w:
                alpha = data[y * stride + x * 4 + 3]
                if alpha > alpha_threshold:
                    start_x = x
                    while x < w and data[y * stride + x * 4 + 3] > alpha_threshold:
                        x += 1
                    raw.append(Rect(start_x, y, x - start_x, step_h))
                else:
                    x += 1

        merged: list[Rect] = []
        for rect in raw:
            found = False
            for m in reversed(merged):
                if (m.x == rect.x and
                    m.width == rect.width and
                    m.y + m.height == rect.y):
                    m.height += rect.height
                    found = True
                    break
            if not found:
                merged.append(Rect(rect.x, rect.y, rect.width, rect.height))

        return merged if merged else [Rect(0, 0, w, h)]
    def _start_animated_blur(self):
        if self._blur_ctx:
            disable_blur(self._blur_ctx)
            free_blur(self._blur_ctx)
            self._blur_ctx = None

        self.revealer.progress_cb = None 

        self._blur_ctx = enable_blur(self)

        try:
            cx, cy = self._content_box.translate_coordinates(self, 0, 0)
        except Exception:
            GLib.timeout_add(32, self._start_animated_blur)
            return

        traced_rects  = self._trace_content_box()
        content_alloc = self._content_box.get_allocation()
        content_h     = content_alloc.height
        content_w     = content_alloc.width
        alignment     = self._alignment

        def on_progress(value):
            if not self._blur_ctx:
                return

            try:
                cx, cy = self._content_box.translate_coordinates(self, 0, 0)
            except Exception:
                return

            clipped = []

            scale = (
                self.revealer.SCALE_START
                + (1.0 - self.revealer.SCALE_START)
                * _ease_out_expo(value)
            )

            anchor_x = cx + (content_w / 2.0)
            anchor_y = cy if alignment != "bottom" else cy + content_h

            for r in traced_rects:
                abs_x = cx + r.x
                abs_y = cy + r.y - 2

                left   = math.floor(anchor_x + (abs_x - anchor_x) * scale)
                top    = math.floor(anchor_y + (abs_y - anchor_y) * scale)

                right  = math.ceil(
                    anchor_x + ((abs_x + r.width) - anchor_x) * scale
                )

                bottom = math.ceil(
                    anchor_y + ((abs_y + r.height) - anchor_y) * scale
                )

                clipped.append((
                    left,
                    top,
                    max(1, right - left),
                    max(1, bottom - top),
                ))
            if clipped:
                set_blur_regions(self._blur_ctx, clipped)
        self.revealer.progress_cb = on_progress

    def destroy(self):
        self.dismiss_layer.destroy()
        self.revealer.progress_cb = None
        if self._blur_ctx:
            disable_blur(self._blur_ctx)
            free_blur(self._blur_ctx)
        super().destroy()
def _make_applet_popup(
    keys: str | list[str],
    bar: "Bar",
    anchor_widget: Gtk.Widget,
) -> PopupWindow | None:
    key_list = keys if isinstance(keys, list) else [keys]
    classes = [APPLET_WIDGETS[k] for k in key_list if k in APPLET_WIDGETS]
    if not classes:
        return None
    def _on_bar_size_allocate(*_):

        offset = bar.get_allocated_height()
        margin = f"{offset}px 0px 0px 0px" if bar.alignment == "top" else f"0px 0px {offset}px 0px"
        window._base_margin = window.extract_margin(margin)

    offset = bar.get_allocated_height()
    margin = f"{offset}px 0px 0px 0px" if bar.alignment == "top" else f"0px 0px {offset}px 0px"
    window = AppletWindow(
        applet=classes,
        alignment=bar.alignment,
        parent=bar,
        pointing_to=anchor_widget,
        layer="top",
        exclusivity="none",
        keyboard_mode="on-demand",
        style_classes=["applet-window"],
        visible=False,
        margin=margin
    )
    window._bar_size_sig = bar.connect("size-allocate", _on_bar_size_allocate)
    window._keys = key_list
    return window

class WidgetWrapper(Box):
    def __init__(self, key: str, child: Gtk.Widget, variant: str = None):
        super().__init__()
        self.widget_key = key
        self.variant = variant
        self._variant_picker: AppletWindow | None = None 
        self._drag_signals: list[int] = []
        self._popup: PopupWindow | None = None

        self.event_box = EventBox()
        self.event_box.add(child)
        self.add(self.event_box)

        self.event_box.connect("button-release-event", self._on_click)
        if key not in ["Workspaces", "Dock"]:
            self.event_box.add_style_class("bar-widget")
            
        if self.widget_key in APPLET_WIDGETS:
            self.event_box.connect("enter-notify-event", lambda w, _: w.add_style_class("hovered"))
            self.event_box.connect("leave-notify-event", self.on_leave)
            self.event_box.connect("button-press-event", lambda w, e: w.add_style_class("active") if e.button == 1 and not edit_mode.edit_mode else None)
        if self.widget_key == "Dash":
            self.event_box.connect("enter-notify-event", lambda w, _: w.add_style_class("hovered"))
            self.event_box.connect("leave-notify-event", self.on_leave)
        edit_mode.connect("notify::edit-mode", self._on_edit_mode_changed)
        self._apply_drag_state()

    def _on_drag_end(self, widget, ctx):
        global _dragging_key, _dragging_widget
        _dragging_key = None
        _dragging_widget = None
        GLib.idle_add(lambda: self.set_visible(True))
                
    def on_leave(self, w, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            w.remove_style_class("hovered")

    def _ensure_popup(self) -> PopupWindow | None:
        if self._popup is not None:
            return self._popup
        bar = self._get_bar()
        if bar is None:
            return None
        if self.widget_key not in APPLET_WIDGETS:
            return None
        self._popup = _make_applet_popup(self.widget_key, bar, self.event_box)
        self._popup.connect("notify::visible", self._on_popup_visibility_changed)
        return self._popup

    def _on_popup_visibility_changed(self, popup, _):
        if popup.is_visible():
            self.event_box.add_style_class("applet-open")
        else:
            self.event_box.remove_style_class("applet-open")

            bar = self._get_bar()
            if bar is not None:
                bar._on_applet_closed()

    def destroy_popup(self) -> None:
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
        if self._variant_picker is not None:
            self._variant_picker.destroy()
            self._variant_picker = None
        if hasattr(self._popup, "_bar_size_sig"):
            bar = self._get_bar()
            if bar is not None:
                bar.disconnect(self._popup._bar_size_sig)

    def _on_click(self, _widget, event: Gdk.EventButton):
        _widget.remove_style_class("active")
        if event.button == 3:
            self._show_variant_menu(event)
            return True
        if edit_mode.edit_mode:
            return False
        if event.button != 1:
            return False
        popup = self._ensure_popup()
        if popup is None:
            return False
        popup.toggle()

        return True

    def _on_edit_mode_changed(self, *_):
        self._apply_drag_state()

    def _apply_drag_state(self):
        if edit_mode.edit_mode:

            self.drag_source_set(
                Gdk.ModifierType.BUTTON1_MASK,
                [TARGET],
                Gdk.DragAction.MOVE,
            )
            if not self._drag_signals:
                self._drag_signals = [
                    self.connect("drag-begin", self._on_drag_begin),
                    self.connect("drag-data-get", self._on_drag_data_get),
                    self.connect("drag-failed", self._on_drag_failed),
                    self.connect("drag-end", self._on_drag_end),
                ]
            self.add_style_class("edit-mode")
        else:
            self.drag_source_unset()
            for sig in self._drag_signals:
                self.disconnect(sig)
            self._drag_signals = []
            self.remove_style_class("edit-mode")

    def _on_drag_begin(self, widget, ctx):
        global _dragging_key, _dragging_widget
        _dragging_key = self.widget_key
        _dragging_widget = self
        if self._popup is not None:
            GLib.idle_add(lambda: self._popup.set_visible(False))
        try:
            Gtk.drag_set_icon_surface(ctx, create_surface_from_widget(self))
        except Exception:
            pass

        def _maybe_hide():
            if _dragging_widget is self and ctx.get_dest_window() is not None:
                self.set_visible(False)
            return False

        GLib.idle_add(_maybe_hide)

    def _on_drag_data_get(self, widget, ctx, data_obj, info, time):
        section = self._get_section()
        if section is None:
            return
        try:
            index = section.get_children().index(self)
        except ValueError:
            return
        data_obj.set_text(f"{self._get_bar().monitor_id}:{self._get_bar().bar_index}:{section.section_name}:{index}", -1)

    def _on_drag_failed(self, widget, ctx, result):
        global _dragging_key, _dragging_widget
        _dragging_key = None
        _dragging_widget = None
        self.set_visible(True)
        return False
        
    def _is_group_zone(self, x: int) -> bool:
        alloc = self.get_allocation()
        center = alloc.width / 2
        zone = alloc.width * 0.40
        return center - zone <= x <= center + zone
    
    def _can_be_grouped(self) -> bool:
        return self.widget_key in APPLET_WIDGETS

    def _on_drag_data_received(self, widget, ctx, x, y, data_obj, info, time):
        self.event_box.remove_style_class("group-drop-target")
        self.event_box.remove_style_class("group-drop-invalid")
        if not edit_mode.edit_mode:
            Gtk.drag_finish(ctx, False, False, time)
            return
        if not self._is_group_zone(x):
            Gtk.drag_finish(ctx, False, False, time)
            return

        payload = data_obj.get_text()
        if not payload:
            Gtk.drag_finish(ctx, False, False, time)
            return
        
        parts = payload.split(":")

        if parts[0] == "applet":
            dragged_key = parts[1]
            if not self._is_group_zone(x) or not self._can_be_grouped():
                Gtk.drag_finish(ctx, False, False, time)
                return
            if dragged_key not in APPLET_WIDGETS or not can_group(self.widget_key, dragged_key):
                Gtk.drag_finish(ctx, False, False, time)
                return
            bar = self._get_bar()
            if bar is None:
                Gtk.drag_finish(ctx, False, False, time)
                return

            self_child = self.event_box.get_child()
            self.event_box.remove(self_child)
            new_widget = build_widget(dragged_key, bar.monitor_id, bar.vertical)
            section = self._get_section()
            try:
                self_index = section.get_children().index(self)
            except ValueError:
                Gtk.drag_finish(ctx, False, False, time)
                return
            self.destroy_popup()
            section.remove(self)
            group = GroupWrapper(
                keys=[self.widget_key, dragged_key],
                variants=[self.variant, None],
                children=[self_child, new_widget],
            )
            section.add(group)
            section.reorder_child(group, self_index)
            Gtk.drag_finish(ctx, True, False, time)
            bar.sync_config()
            return

        if len(parts) != 4:
            Gtk.drag_finish(ctx, False, False, time)
            return

        _, _bar_index_str, src_section_name, src_index_str = parts
        try:
            src_index = int(src_index_str)
        except ValueError:
            Gtk.drag_finish(ctx, False, False, time)
            return

        bar = self._get_bar()
        if bar is None:
            Gtk.drag_finish(ctx, False, False, time)
            return

        src_section: DraggableSection = bar.sections.get(src_section_name)
        if src_section is None:
            Gtk.drag_finish(ctx, False, False, time)
            return

        src_children = src_section.get_children()
        if src_index >= len(src_children):
            Gtk.drag_finish(ctx, False, False, time)
            return

        dragged = src_children[src_index]

        if dragged is self:
            Gtk.drag_finish(ctx, False, False, time)
            return
        if not isinstance(dragged, WidgetWrapper):
            Gtk.drag_finish(ctx, False, False, time)
            return

        if not self._can_be_grouped() or not dragged._can_be_grouped():
            Gtk.drag_finish(ctx, False, False, time)
            return
        if not can_group(self.widget_key, dragged.widget_key):
            Gtk.drag_finish(ctx, False, False, time)
            return
        dst_section = self._get_section()
        if dst_section is None:
            Gtk.drag_finish(ctx, False, False, time)
            return

        try:
            self_index = dst_section.get_children().index(self)
        except ValueError:
            Gtk.drag_finish(ctx, False, False, time)
            return

        if src_section is dst_section:
            try:
                dragged_index = src_section.get_children().index(dragged)
                if dragged_index < self_index:
                    self_index -= 1
            except ValueError:
                pass

        self.destroy_popup()
        dragged.destroy_popup()

        self_child = self.event_box.get_child()
        dragged_child = dragged.event_box.get_child()
        self.event_box.remove(self_child)
        dragged.event_box.remove(dragged_child)

        src_section.remove(dragged)
        dst_section.remove(self)

        group = GroupWrapper(
            keys=[self.widget_key, dragged.widget_key],
            variants=[self.variant, dragged.variant],
            children=[self_child, dragged_child],
        )
        dst_section.add(group)
        dst_section.reorder_child(group, self_index)

        Gtk.drag_finish(ctx, True, False, time)
        bar.sync_config()
    
    def _show_variant_menu(self, event: Gdk.EventButton):
        if not edit_mode.edit_mode:
            return
        if self._variant_picker is not None:
            self._variant_picker.toggle()
            return
        bar = self._get_bar()
        if bar is None:
            return
        self._variant_picker = _make_variant_picker(
            key=self.widget_key,
            current_variant=self.variant,
            bar=bar,
            anchor_widget=self.event_box,
            on_select=self._set_variant,
        )
        if self._variant_picker is not None:
            self._variant_picker.connect("hide", lambda w: self._clear_picker())
            self._variant_picker.toggle()

    def _clear_picker(self):
        if self._variant_picker is not None:
            picker = self._variant_picker
            self._variant_picker = None
            GLib.timeout_add(10, picker.destroy)
            
    def _set_variant(self, variant: str):
        if variant == self.variant:
            return
        self.variant = variant

        if self._variant_picker is not None:
            self._variant_picker.toggle()
        GLib.idle_add(self._apply_variant, variant)

    def _apply_variant(self, variant: str):
        bar = self._get_bar()
        if bar is None:
            return False
        old = self.event_box.get_child()
        self.event_box.remove(old)
        old.destroy()
        new = build_widget(self.widget_key, bar.monitor_id, bar.vertical, variant)
        if new:
            self.event_box.add(new)

        bar.sync_config()
        return False

    def _get_section(self) -> "DraggableSection | None":
        parent = self.get_parent()
        return parent if isinstance(parent, DraggableSection) else None

    def _get_bar(self) -> "Bar | None":
        section = self._get_section()
        return section.bar if section is not None else None

class GroupWrapper(Box):
    def __init__(self, keys: list[str], variants: list[str], children: list[Gtk.Widget]):
        assert len(keys) == 2 and len(children) == 2, "GroupWrapper requires exactly 2 widgets"
        super().__init__(orientation="h")
        self.get_style_context().add_class("widget-group")

        self.widget_keys = list(keys)

        self.widget_variants = list(variants)
        self._variant_pickers: list[AppletWindow | None] = [None, None]

        self._drag_signals: list[int] = []
        self._popup: PopupWindow | None = None
        self._inner = Box(orientation="h", spacing=10)
        self._inner.get_style_context().add_class("widget-group-inner")

        self._event_boxes: list[EventBox] = []
        for i, child in enumerate(children):
            eb = EventBox()
            eb.add(child)
            eb.connect("button-release-event", self._on_child_click)
            eb.connect("button-release-event", self._make_child_right_click(i))
            child.add_style_class("left" if i == 0 else "right")
            self._inner.pack_start(eb, False, False, 0)
            self._event_boxes.append(eb)

        outer_eb = EventBox()
        outer_eb.add(self._inner)
        self.add(outer_eb)
        self._outer_eb = outer_eb
        self._outer_eb.add_style_class("bar-widget")
        self._outer_eb.connect("enter-notify-event", lambda w, _: w.add_style_class("hovered"))
        self._outer_eb.connect("leave-notify-event", self.on_leave)
        self._outer_eb.connect("button-press-event", lambda w, e: w.add_style_class("active") if e.button == 1 and not edit_mode.edit_mode else None)
        self._outer_eb.connect("button-release-event", self._on_outer_click)

        self.drag_dest_set(
            Gtk.DestDefaults.HIGHLIGHT,
            [TARGET],
            Gdk.DragAction.MOVE,
        )

        edit_mode.connect("notify::edit-mode", self._on_edit_mode_changed)
        self._apply_drag_state()

    def on_leave(self, w, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            w.remove_style_class("hovered")

    def _ensure_popup(self) -> PopupWindow | None:
        if self._popup is not None:
            return self._popup
        bar = self._get_bar()
        if bar is None:
            return None
        self._popup = _make_applet_popup(self.widget_keys, bar, self._outer_eb)
        self._popup.connect("notify::visible", self._on_popup_visibility_changed)
        return self._popup

    def _on_popup_visibility_changed(self, popup, _):
        if popup.is_visible():
            self._outer_eb.add_style_class("applet-open")
        else:
            self._outer_eb.remove_style_class("applet-open")

            bar = self._get_bar()
            if bar is not None:
                bar._on_applet_closed()

    def destroy_popups(self) -> None:
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
        for i, picker in enumerate(self._variant_pickers):
            if picker is not None:
                picker.destroy()
                self._variant_pickers[i] = None

    def _on_child_click(self, _widget, event: Gdk.EventButton):
        self._outer_eb.remove_style_class("active")
        if edit_mode.edit_mode:
            return False
        if event.button != 1:
            return False
        popup = self._ensure_popup()
        if popup is None:
            return False
        popup.toggle()
        return True
    
    def _on_outer_click(self, widget, event: Gdk.EventButton):
        self._outer_eb.remove_style_class("active")

        if edit_mode.edit_mode:
            return False

        if event.button != 1:
            return False

        popup = self._ensure_popup()
        if popup is None:
            return False

        popup.toggle()
        return True
    
    def _on_edit_mode_changed(self, *_):
        self._apply_drag_state()

    def _apply_drag_state(self):
        if edit_mode.edit_mode:
            for i, eb in enumerate(self._event_boxes):
                eb.drag_source_set(
                    Gdk.ModifierType.BUTTON1_MASK,
                    [TARGET],
                    Gdk.DragAction.MOVE,
                )
                eb.connect("drag-begin", self._on_child_drag_begin)
                eb.connect("drag-data-get", self._make_child_drag_data_get(i))
                eb.connect("drag-end", self._on_child_drag_end)
                eb.connect("drag-failed", self._on_child_drag_failed)
            self.add_style_class("edit-mode")
        else:
            self.drag_source_unset()
            for sig in self._drag_signals:
                self.disconnect(sig)
            self._drag_signals = []
            for eb in self._event_boxes:
                eb.drag_source_unset()
            self.remove_style_class("edit-mode")

    def _on_child_drag_begin(self, widget, ctx):
        global _dragging_key, _dragging_widget
        _dragging_widget = widget
        if self._popup is not None:
            self._popup.set_visible(False)
        try:
            surface = create_surface_from_widget(widget)
            Gtk.drag_set_icon_surface(ctx, surface)
        except Exception as e:
            print(f"[GroupWrapper] drag icon failed: {e}")

        def _maybe_hide():
            if _dragging_widget is widget and ctx.get_dest_window() is not None:
                widget.set_visible(False)
            return False

        GLib.idle_add(_maybe_hide)

    def _on_child_drag_failed(self, widget, ctx, result):
        global _dragging_key, _dragging_widget
        widget.set_visible(True)
        _dragging_key = None
        _dragging_widget = None
        return False

    def _on_child_drag_end(self, widget, ctx):
        global _dragging_key, _dragging_widget
        _dragging_key = None
        _dragging_widget = None
        GLib.idle_add(lambda: widget.set_visible(True) or False)

    def _make_child_drag_data_get(self, child_index: int):
        def handler(widget, ctx, data_obj, info, time):
            section = self._get_section()
            if section is None:
                return
            try:
                group_index = section.get_children().index(self)
            except ValueError:
                return
            data_obj.set_text(
                f"{self._get_bar().monitor_id}:{self._get_bar().bar_index}:{section.section_name}:{group_index}:child:{child_index}", -1
            )
        return handler

    def _make_child_right_click(self, i: int):
        def handler(_widget, event: Gdk.EventButton):
            if event.button != 3:
                return False
            if not edit_mode.edit_mode:
                return False
            if self._variant_pickers[i] is not None:
                self._variant_pickers[i].toggle()
                return True
            bar = self._get_bar()
            if bar is None:
                return True
            self._variant_pickers[i] = _make_variant_picker(
                key=self.widget_keys[i],
                current_variant=self.widget_variants[i],
                bar=bar,
                anchor_widget=self,
                on_select=lambda chosen, idx=i: self._set_child_variant(idx, chosen),
            )
            if self._variant_pickers[i] is not None:
                self._variant_pickers[i].connect("hide", lambda w, idx=i: self._clear_picker(idx))
                self._variant_pickers[i].toggle()
            return True
        return handler

    def _clear_picker(self, i: int):
        if self._variant_pickers[i] is not None:
            GLib.timeout_add(10, self._variant_pickers[i].destroy)
            self._variant_pickers[i] = None
            
    def _set_child_variant(self, i: int, variant: str):
        if variant == self.widget_variants[i]:
            return
        self.widget_variants[i] = variant
        if self._variant_pickers[i] is not None:
            self._variant_pickers[i].toggle()
        GLib.idle_add(self._apply_child_variant, i, variant)

    def _apply_child_variant(self, i: int, variant: str):
        bar = self._get_bar()
        if bar is None:
            return False
        eb = self._event_boxes[i]
        old = eb.get_child()
        eb.remove(old)
        old.destroy()
        new = build_widget(self.widget_keys[i], bar.monitor_id, bar.vertical, variant)
        if new:
            eb.add(new)

        bar.sync_config()
        return False

    def _get_section(self) -> "DraggableSection | None":
        parent = self.get_parent()
        return parent if isinstance(parent, DraggableSection) else None

    def _get_bar(self) -> "Bar | None":
        section = self._get_section()
        return section.bar if section is not None else None

class DraggableSection(Box):
    def __init__(self, section_name: str, bar: "Bar", **kwargs):
        super().__init__(style_classes=["draggable-section"] + [section_name], **kwargs)
        self.section_name = section_name
        self.bar = bar
        self._placeholder: DropPlaceholder | None = None

        self.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [TARGET],
            Gdk.DragAction.MOVE,
        )
        self.connect("drag-motion", self._on_drag_motion)
        self.connect("drag-data-received", self._on_drag_data_received)
        self.connect("drag-leave", self._on_drag_leave)
        edit_mode.connect("notify::edit-mode", self._apply_drag_state)

    def _apply_drag_state(self, *_):
        if edit_mode.edit_mode:
            self.add_style_class("edit-mode")
        else:
            self.remove_style_class("edit-mode")
        self.remove_style_class("drop-target-active")

    def _on_drag_motion(self, widget, ctx, x, y, time):
        if not edit_mode.edit_mode:
            Gdk.drag_status(ctx, 0, time)
            return True
        self.add_style_class("drop-target-active")

        for child in self.get_children():
            if not isinstance(child, WidgetWrapper):
                continue
            cx, cy = self.translate_coordinates(child, x, y)
            alloc = child.get_allocation()
            if 0 <= cx <= alloc.width and 0 <= cy <= alloc.height:
                if child._is_group_zone(cx) and child._can_be_grouped():
                    dragged_groupable = _dragging_key and _dragging_key in APPLET_WIDGETS
                    if dragged_groupable:
                        if can_group(child.widget_key, _dragging_key):
                            child.event_box.add_style_class("group-drop-target")
                            child.event_box.remove_style_class("group-drop-invalid")
                        else:
                            child.event_box.add_style_class("group-drop-invalid")
                            child.event_box.remove_style_class("group-drop-target")
                    else:
                        child.event_box.remove_style_class("group-drop-target")
                        child.event_box.remove_style_class("group-drop-invalid")
                else:
                    child.event_box.remove_style_class("group-drop-target")
                    child.event_box.remove_style_class("group-drop-invalid")
            else:
                child.event_box.remove_style_class("group-drop-target")
                child.event_box.remove_style_class("group-drop-invalid")

        drop_idx = self._drop_index_excluding_placeholder(x, y)
        if drop_idx is not None:
            self._show_placeholder(drop_idx)
        else:
            self._remove_placeholder()

        Gdk.drag_status(ctx, Gdk.DragAction.MOVE, time)
        return True

    def _drop_index(self, x: int, y: int) -> int:
        children = self.get_children()
        toplevel = self.get_toplevel()
        win = toplevel.get_window()
        if win is None:
            return len(children)

        sx, sy = self.translate_coordinates(toplevel, 0, 0)
        ox, oy = win.get_position()
        root_x = ox + sx + x

        for i, child in enumerate(children):
            cx, cy = child.translate_coordinates(toplevel, 0, 0)
            child_root_x = ox + cx
            alloc = child.get_allocation()
            if root_x < child_root_x + alloc.width / 2:
                return i

        return len(children)

    def _on_drag_data_received(self, widget, ctx, x, y, data_obj, info, time):
        self._remove_placeholder()
        if not edit_mode.edit_mode:
            Gtk.drag_finish(ctx, False, False, time)
            return
        self.remove_style_class("drop-target-active") 

        payload = data_obj.get_text()
        if not payload:
            Gtk.drag_finish(ctx, False, False, time)
            return

        parts = payload.split(":")

        if len(parts) == 6 and parts[4] == "child":
            self._handle_ungroup_drop(parts, x, y, ctx, time)
            return
        if len(parts) == 2 and parts[0] == "applet":

            for child in self.get_children():
                if not isinstance(child, WidgetWrapper):
                    continue
                cx, cy = self.translate_coordinates(child, x, y)
                alloc = child.get_allocation()
                if 0 <= cx <= alloc.width and 0 <= cy <= alloc.height:
                    if child._is_group_zone(cx):
                        child._on_drag_data_received(widget, ctx, cx, cy, data_obj, info, time)
                        return

            self._handle_applet_drop(parts[1], x, y, ctx, time)
            return
        if len(parts) == 4:
            for child in self.get_children():
                if not isinstance(child, WidgetWrapper):
                    continue
                cx, cy = self.translate_coordinates(child, x, y)
                alloc = child.get_allocation()
                if 0 <= cx <= alloc.width and 0 <= cy <= alloc.height:
                    if child._is_group_zone(cx):
                        child._on_drag_data_received(widget, ctx, cx, cy, data_obj, info, time)
                        return
                    else:
                        self._handle_reorder_drop(parts, x, y, ctx, time)
                        return
            self._handle_reorder_drop(parts, x, y, ctx, time)
            return

        Gtk.drag_finish(ctx, False, False, time)

    def _show_placeholder(self, index: int):
        if self._placeholder is None:
            self._placeholder = DropPlaceholder()
            self._placeholder.show()
            self.add(self._placeholder)
        self.reorder_child(self._placeholder, index)

    def _remove_placeholder(self):
        if self._placeholder is not None:
            self.remove(self._placeholder)
            self._placeholder.destroy()
            self._placeholder = None

    def _on_drag_leave(self, widget, ctx, time):
        self._remove_placeholder()
        self.remove_style_class("drop-target-active")

        for child in self.get_children():
            if isinstance(child, WidgetWrapper):
                child.event_box.remove_style_class("group-drop-target")
                child.event_box.remove_style_class("group-drop-invalid")

    def _handle_reorder_drop(self, parts, x, y, ctx, time):
        print("reorder")
        src_monitor_id, src_bar_index_str, src_section_name, src_index_str = parts
        try:
            src_index = int(src_index_str)
            src_bar_index = int(src_bar_index_str)
            src_monitor_id = int(src_monitor_id)
        except ValueError:
            Gtk.drag_finish(ctx, False, False, time)
            return

        if src_monitor_id != self.bar.monitor_id:
            Gtk.drag_finish(ctx, False, False, time)
            return

        src_bar = next(
            (b for (_, bi), b in self.bar._bar_manager._bars.items()
            if b.monitor_id == src_monitor_id and bi == src_bar_index),
            None
        )
        if src_bar is None:
            Gtk.drag_finish(ctx, False, False, time)
            return

        src_section = src_bar.sections.get(src_section_name)
        if src_section is None:
            Gtk.drag_finish(ctx, False, False, time)
            return

        src_children = src_section.get_children()
        if src_index >= len(src_children):
            Gtk.drag_finish(ctx, False, False, time)
            return

        wrapper = src_children[src_index]
        drop_index = self._drop_index_excluding_placeholder(x, y)

        src_section.remove(wrapper)
        self.add(wrapper)
        self.reorder_child(wrapper, drop_index)
        play_sound("widget-placed")
        Gtk.drag_finish(ctx, True, False, time)
        self.bar.sync_config()
        if src_bar is not self.bar:
            src_bar.sync_config()

    def _handle_ungroup_drop(self, parts, x, y, ctx, time):
        try:
            src_monitor_id = int(parts[0])
            src_bar_index = int(parts[1])
            src_section_name = parts[2]
            group_index = int(parts[3])
            child_index = int(parts[5])
        except ValueError:
            Gtk.drag_finish(ctx, False, False, time)
            return

        if src_monitor_id != self.bar.monitor_id:
            Gtk.drag_finish(ctx, False, False, time)
            return

        src_bar = next(
            (b for (_, bi), b in self.bar._bar_manager._bars.items()
            if b.monitor_id == src_monitor_id and bi == src_bar_index),
            None
        )
        if src_bar is None:
            Gtk.drag_finish(ctx, False, False, time)
            return

        src_section = src_bar.sections.get(src_section_name)
        src_children = src_section.get_children()
        if group_index >= len(src_children):
            Gtk.drag_finish(ctx, False, False, time)
            return

        group = src_children[group_index]
        if not isinstance(group, GroupWrapper):
            Gtk.drag_finish(ctx, False, False, time)
            return

        if child_index >= len(group.widget_keys):
            Gtk.drag_finish(ctx, False, False, time)
            return

        extracted_key     = group.widget_keys[child_index]
        extracted_variant = group.widget_variants[child_index]
        remaining_key     = group.widget_keys[1 - child_index]
        remaining_variant = group.widget_variants[1 - child_index]

        group_section_index = src_section.get_children().index(group)

        group.destroy_popups()
        src_section.remove(group)

        remaining_widget = build_widget(remaining_key, self.bar.monitor_id, self.bar.vertical, remaining_variant)
        if remaining_widget is None:
            remaining_widget = build_widget(remaining_key, self.bar.monitor_id, self.bar.vertical)
        remaining_wrapper = WidgetWrapper(remaining_key, remaining_widget, variant=remaining_variant)
        src_section.add(remaining_wrapper)
        src_section.reorder_child(remaining_wrapper, group_section_index)

        new_widget = build_widget(extracted_key, self.bar.monitor_id, self.bar.vertical, extracted_variant)
        if new_widget is None:
            new_widget = build_widget(extracted_key, self.bar.monitor_id, self.bar.vertical)
        new_wrapper = WidgetWrapper(extracted_key, new_widget, variant=extracted_variant)
        drop_index = self._drop_index_excluding_placeholder(x, y)
        self.add(new_wrapper)
        self.reorder_child(new_wrapper, drop_index)
        Gtk.drag_finish(ctx, True, False, time)
        self.bar.sync_config()
    def _handle_applet_drop(self, key: str, x: int, y: int, ctx, time):
        if key not in BAR_WIDGETS:
            Gtk.drag_finish(ctx, False, False, time)
            return
        if key in self.bar.get_monitor_active_keys():
            Gtk.drag_finish(ctx, False, False, time)
            return
        widget = build_widget(key, self.bar.monitor_id, self.bar.vertical)
        if widget is None:
            Gtk.drag_finish(ctx, False, False, time)
            return
        wrapper = WidgetWrapper(key, widget)
        drop_index = self._drop_index_excluding_placeholder(x, y)
        self.add(wrapper)
        self.reorder_child(wrapper, drop_index)
        play_sound("widget-placed")
        Gtk.drag_finish(ctx, True, False, time)
        self.bar.sync_config()
        self.bar.notify_dash_changed()

    def _drop_index_excluding_placeholder(self, x: int, y: int) -> int | None:
        children = [c for c in self.get_children() if not isinstance(c, DropPlaceholder)]
        toplevel = self.get_toplevel()
        win = toplevel.get_window()
        if win is None:
            return len(children)

        sx, sy = self.translate_coordinates(toplevel, 0, 0)
        ox, oy = win.get_position()
        root_x = ox + sx + x

        drop_index = len(children)
        for i, child in enumerate(children):
            cx, cy = child.translate_coordinates(toplevel, 0, 0)
            child_root_x = ox + cx
            alloc = child.get_allocation()
            if root_x < child_root_x + alloc.width / 2:
                drop_index = i
                break

        return drop_index
class Bar(Window):
    def __init__(self, monitor_id: int = 0, bar_index: int = 0, bar_cfg: dict = None, monitor: Gdk.Monitor = None, bar_manager=None, on_remove: callable = None):
        self._on_remove_cb = on_remove
        self._blur_ctx = None
        self.monitor_id = monitor_id
        self.bar_index = bar_index
        self.vertical = False
        self._bar_manager = bar_manager
        self._dash_changed_callbacks: list[callable] = []
        self._hide_timeout = None
        
        if bar_cfg is not None:
            self.bar_config = bar_cfg

        self.sections: dict[str, DraggableSection] = {
            "left":   self._build_section("left"),
            "center": self._build_section("center"),
            "right":  self._build_section("right"),
        }
        
        self.alignment = self.bar_config.get("alignment", "top")
        self.min_width = self.bar_config.get("min_width", False)
        self.auto_hide = self.bar_config.get("auto_hide", False)

        self._centerbox = CenterBox(
            style_classes=["bar", "top"] if self.alignment == "top" else ["bar", "bottom"],
            start_children=self.sections["left"],
            center_children=self.sections["center"],
            end_children=self.sections["right"],
        )

        transition = "slide-up" if self.alignment == "bottom" else "slide-down"
        self._revealer = HackedRevealer(
            bezier_curve=(0.17, 0.67, 0, 1),
            transition_type=transition,
            child=self._centerbox,
            child_revealed=not self.auto_hide,
            h_expand=True,
            duration=0.3,

        )

        super().__init__(
            title=f"caffyne-shell-bar",
            layer="top",
            anchor=f"{self.alignment}" if self.min_width else f"{self.alignment} left right",
            exclusivity="none" if self.auto_hide else "auto",
            monitor=monitor_id,
            child=Box(
                h_expand=True,
                style="min-height: 4px;",
                children=self._revealer,
            )
        )

        if self.bar_config.get("floating_bar", False):
            self._centerbox.add_style_class("floating")
        if self.min_width:
            self._centerbox.add_style_class("min-width")
        if self.auto_hide:
            self._centerbox.add_style_class("auto-hide")
 
        self.connect("button-release-event", self._on_button_release)
        self.connect("enter-notify-event", self._on_bar_enter)
        self.connect("leave-notify-event", self._on_bar_leave)
        edit_mode.connect("notify::edit-mode", self._on_edit_mode_changed)
        self.gdk_monitor = monitor
        if user_options.theme.blur:
            self._blur_ctx = enable_blur(self)
            GLib.timeout_add(1500, self._update_blur_region)

    def _build_section(self, section_name: str) -> DraggableSection:
        entries: list = self.bar_config.get(section_name, [])
        section = DraggableSection(
            section_name=section_name,
            bar=self,
            orientation="h",
            spacing=6,
        )
        for entry in entries:
            if isinstance(entry, str):
                widget = build_widget(entry, self.monitor_id, self.vertical)
                if widget is not None:
                    section.add(WidgetWrapper(entry, widget))
            elif isinstance(entry, dict) and entry.get("type") == "group":
                keys, variants, children = [], [], []
                valid = True
                for item in entry.get("widgets", []):
                    if isinstance(item, str):
                        k, v = item, None
                    else:
                        k, v = item.get("widget", ""), item.get("variant", None)
                    w = build_widget(k, self.monitor_id, self.vertical, v)
                    if w is None:
                        valid = False
                        break
                    keys.append(k)
                    variants.append(v)
                    children.append(w)
                if valid and len(keys) == 2:
                    section.add(GroupWrapper(keys=keys, variants=variants, children=children))
            elif isinstance(entry, dict) and "widget" in entry:
                k = entry["widget"]
                v = entry.get("variant", None)
                widget = build_widget(k, self.monitor_id, self.vertical, v)
                if widget is not None:
                    section.add(WidgetWrapper(k, widget, variant=v))
        return section

    def _update_blur_region(self) -> bool:
        set_blur_regions_from_widget(self._blur_ctx, self, accuracy=1, erode=0)
        return False

    def apply_blur(self, enabled: bool) -> None:
        if enabled:
            if self._blur_ctx is None:
                self._blur_ctx = enable_blur(self)
                self._update_blur_region()
        else:
            if self._blur_ctx is not None:
                disable_blur(self._blur_ctx)
                free_blur(self._blur_ctx)
                self._blur_ctx = None

    def _on_button_release(self, widget, event: Gdk.EventButton):
        if event.button == 2:
            edit_mode.toggle()
            return True
        if event.button == 3:
            self._show_context_menu(event)
            return True
        return False

    def _toggle_floating(self):
        floating = self.bar_config.get("floating_bar", False)
        floating = not floating
        self.bar_config["floating_bar"] = floating
        user_options.save()
        if floating:
            self._centerbox.add_style_class("floating")
        else:
            self._centerbox.remove_style_class("floating")
        GLib.timeout_add(320, self._update_blur_region)
        for i, cfg in enumerate(user_options.bars.configs):
            if cfg.get("monitor") == self.monitor_id:
                user_options.bars.configs[i]["floating_bar"] = floating
                break

    def _show_context_menu(self, event: Gdk.EventButton):
        menu = Gtk.Menu()

        label = "Lock" if edit_mode.edit_mode else "Unlock"
        toggle_item = Gtk.MenuItem(label=label)
        toggle_item.connect("activate", lambda _: edit_mode.toggle())
        menu.append(toggle_item)

        edit_applets_item = Gtk.MenuItem(label="Edit Applets")
        edit_applets_item.connect("activate", lambda _: self._open_edit_applets())
        menu.append(edit_applets_item)
        floating_label = "Attach Bar" if self.bar_config.get("floating_bar", False) else "Floating (Beta)"
        floating_item = Gtk.MenuItem(label=floating_label)
        floating_item.connect("activate", lambda _: self._toggle_floating())
        menu.append(floating_item)
    
        min_width_label = "Full Width" if self.min_width else "Min Width (Beta)"
        min_width_item = Gtk.MenuItem(label=min_width_label)
        min_width_item.connect("activate", lambda _: self._toggle_min_width())
        menu.append(min_width_item)

        monitor_bars = [
            bar for (m, _), bar in self._bar_manager._bars.items()
            if bar.monitor_id == self.monitor_id
        ] if self._bar_manager else []

        if len(monitor_bars) == 2:
            swap_item = Gtk.MenuItem(label="Swap Bars")
            swap_item.connect("activate", lambda _: self._swap_bars())
            menu.append(swap_item)
        else:
            other = "bottom" if self.alignment == "top" else "top"
            move_item = Gtk.MenuItem(label=f"Move to {other.capitalize()}")
            move_item.connect("activate", lambda _: self._set_alignment(other))
            menu.append(move_item)

        auto_hide_label = "Always Show" if self.auto_hide else "Auto Hide (Beta)"
        auto_hide_item = Gtk.MenuItem(label=auto_hide_label)
        auto_hide_item.connect("activate", lambda _: self._toggle_auto_hide())
        menu.append(auto_hide_item)

        remove_item = Gtk.MenuItem(label="Remove Bar")
        remove_item.connect("activate", lambda _: self._request_remove())
        menu.connect("deactivate", self._on_menu_deactivate)
        menu.append(remove_item)
        if user_options.theme.blur:
            popup_with_blur(menu, event)
        else:
            menu.show_all()
            menu.popup_at_pointer(event)

    def _set_alignment(self, alignment: str):
        self.alignment = alignment
        self.bar_config["alignment"] = alignment
        transition = "slide-up" if alignment == "bottom" else "slide-down"
        self._revealer.transition_type = transition
        user_options.save()
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.TOP, alignment == "top")
        GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, alignment == "bottom")
        if alignment == "bottom":
            self._centerbox.remove_style_class("top")
            self._centerbox.add_style_class("bottom")
        else:
            self._centerbox.remove_style_class("bottom")
            self._centerbox.add_style_class("top")
        GLib.timeout_add(320, self._update_blur_region)
        for section in self.sections.values():
            for child in section.get_children():
                if isinstance(child, WidgetWrapper):
                    child.destroy_popup()
                elif isinstance(child, GroupWrapper):
                    child.destroy_popups()

        for i, cfg in enumerate(user_options.bars.configs):
            if cfg.get("monitor") == self.monitor_id:
                user_options.bars.configs[i]["alignment"] = alignment
                break
    def _toggle_min_width(self):
        self.min_width = not self.min_width
        self.bar_config["min_width"] = self.min_width
        self.anchor = self.alignment if self.min_width else f"{self.alignment} left right"
        if self.min_width:
            self._centerbox.add_style_class("min-width")
        else:
            self._centerbox.remove_style_class("min-width")
        GLib.timeout_add(320, self._update_blur_region)
        user_options.save()

    def _toggle_auto_hide(self):
        self.auto_hide = not self.auto_hide
        self.bar_config["auto_hide"] = self.auto_hide
        if self.auto_hide:
            self._centerbox.add_style_class("auto-hide")
            self.exclusivity = "none"
            self._revealer.set_reveal_child(False)
            self._centerbox.remove_style_class("revealed")
        else:
            self._centerbox.remove_style_class("auto-hide")
            self.exclusivity = "auto"
            self._revealer.set_reveal_child(True)
        GLib.timeout_add(320, self._update_blur_region)
        user_options.save()

    def _swap_bars(self):
        if self._bar_manager is None:
            return
        monitor_bars = [
            bar for (m, _), bar in self._bar_manager._bars.items()
            if bar.monitor_id == self.monitor_id
        ]
        if len(monitor_bars) != 2:
            return
        a, b = monitor_bars[0], monitor_bars[1]
        a_align, b_align = a.alignment, b.alignment
        a._set_alignment(b_align)
        b._set_alignment(a_align)
        
    def _on_bar_enter(self, _, event: Gdk.EventCrossing):
        if not self.auto_hide:
            return
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        if self._hide_timeout is not None:
            GLib.source_remove(self._hide_timeout)
            self._hide_timeout = None
        if self._revealer.get_reveal_child():
            return
        self._revealer.set_reveal_child(True)
        self._centerbox.add_style_class("revealed")

    def _on_bar_leave(self, _, event: Gdk.EventCrossing):
        if not self.auto_hide:
            return
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        if self._hide_timeout is not None:
            GLib.source_remove(self._hide_timeout)
        self._hide_timeout = GLib.timeout_add(600, self._try_hide)

    def _try_hide(self):
        self._hide_timeout = None
        if open_applet is not None and open_applet.is_visible():
            return False
        if edit_mode.edit_mode:
            return False
        self._do_hide()
        return False

    def _do_hide(self):
        self.exclusivity = "none"
        self._revealer.set_reveal_child(False)
        self._centerbox.remove_style_class("revealed")

    def _on_edit_mode_changed(self, *_):
        if open_applet:
            set_open_applet(None)
        if edit_mode.edit_mode:
            self._centerbox.add_style_class("edit-mode")
            if self.auto_hide:
                if self._hide_timeout is not None:
                    GLib.source_remove(self._hide_timeout)
                    self._hide_timeout = None
                self._revealer.set_reveal_child(True)
                self.exclusivity = "auto"
                self._centerbox.add_style_class("revealed")
        else:
            if self.auto_hide:
                self.exclusivity = "none"

            self._centerbox.remove_style_class("edit-mode")
            user_options.save()
            if self.auto_hide:
                self._hide_timeout = GLib.timeout_add(600, self._try_hide)

    def _open_edit_applets(self):
        if self._bar_manager is None:
            return
        dash = self._bar_manager._dashes.get(self.gdk_monitor)
        if dash:
            dash.toggle_applets()
    def _on_menu_deactivate(self, _):
        if not self.auto_hide:
            return
        if is_applet_open():
            return

        ptr = self.get_display().get_default_seat().get_pointer()
        _, px, py, _ = self.get_window().get_device_position(ptr)
        alloc = self.get_allocation()
        if not (0 <= px <= alloc.width and 0 <= py <= alloc.height):
            self._do_hide()
    def _on_applet_closed(self):
        if not self.auto_hide:
            return
        if self._hide_timeout is not None:
            GLib.source_remove(self._hide_timeout)
        self._hide_timeout = GLib.timeout_add(600, self._try_hide)
    def sync_config(self):
        for section_name, section in self.sections.items():
            entries = []
            for child in section.get_children():
                if isinstance(child, WidgetWrapper):
                    if not child.variant:
                        entries.append(child.widget_key)
                    else:
                        entries.append({"widget": child.widget_key, "variant": child.variant})
                elif isinstance(child, GroupWrapper):
                    widgets = []
                    for k, v in zip(child.widget_keys, child.widget_variants):
                        if not v:
                            widgets.append(k)
                        else:
                            widgets.append({"widget": k, "variant": v})
                    entries.append({"type": "group", "widgets": widgets})
            self.bar_config[section_name] = entries

        for monitor_cfg in user_options.bars.configs:
            if monitor_cfg.get("monitor") != self.monitor_id:
                continue
            bars_list = monitor_cfg.get("bars")
            if bars_list is not None:
                if self.bar_index < len(bars_list):
                    bars_list[self.bar_index] = self.bar_config
            else:

                monitor_cfg.update(self.bar_config)
            break

        self.notify_dash_changed()
    def get_active_keys(self) -> set[str]:
        """Return all widget keys currently present in any section."""
        keys = set()
        for section in self.sections.values():
            for child in section.get_children():
                if isinstance(child, WidgetWrapper):
                    keys.add(child.widget_key)
                elif isinstance(child, GroupWrapper):
                    keys.update(child.widget_keys)
        return keys
    def register_dash_callback(self, cb: callable) -> None:
        self._dash_changed_callbacks.append(cb)

    def notify_dash_changed(self) -> None:
        for cb in self._dash_changed_callbacks:
            cb()
    def get_monitor_active_keys(self) -> set[str]:
        """Return all widget keys active across ALL bars on this monitor."""
        if self._bar_manager is None:
            return self.get_active_keys()
        keys = set()
        for (monitor, _), bar in self._bar_manager._bars.items():
            if bar.monitor_id == self.monitor_id:
                keys.update(bar.get_active_keys())
        return keys
    def _request_remove(self):
        for monitor_cfg in user_options.bars.configs:
            if monitor_cfg.get("monitor") != self.monitor_id:
                continue
            bars_list = monitor_cfg.get("bars")
            if bars_list is not None:
                if self.bar_index < len(bars_list):
                    bars_list.pop(self.bar_index)
                if not bars_list:
                    user_options.bars.configs.remove(monitor_cfg)
            else:
                user_options.bars.configs.remove(monitor_cfg)
            break
        user_options.save()
        if self._on_remove_cb:
            self._on_remove_cb()
class BarManager:
    def __init__(self):
        self._bars: dict[tuple[Gdk.Monitor, int], Bar] = {}
        self._notifications: dict[Gdk.Monitor, NotificationWindow] = {}
        self._dashes: dict[Gdk.Monitor, Dash] = {}
        self._osds: dict[Gdk.Monitor, OSD] = {}
        self._display = Gdk.Display.get_default()

        for i in range(self._display.get_n_monitors()):
            monitor = self._display.get_monitor(i)
            self._add_bar(monitor, i)

        self._display.connect(
            "monitor-added",
            lambda display, monitor: GLib.timeout_add(1000, self._on_monitor_added, display, monitor),
        )
        self._display.connect("monitor-removed", self._on_monitor_removed)

    def _add_bar(self, monitor: Gdk.Monitor, monitor_id: int) -> None:
        if monitor not in self._notifications:
            self._notifications[monitor] = NotificationWindow(monitor_id)

        monitor_cfg = next(
            (c for c in user_options.bars.configs if c.get("monitor") == monitor_id),
            None,
        )
        if monitor_cfg is None:
            print(f"[BarManager] no config for monitor_id={monitor_id}, skipping")
            return

        for bar_index, bar_cfg in enumerate(monitor_cfg["bars"]):
            key = (monitor, bar_index)
            if key in self._bars:
                continue
            new_bar = Bar(
                monitor_id,
                bar_index=bar_index,
                bar_cfg=bar_cfg,
                monitor=monitor,
                bar_manager=self,
                on_remove=lambda m=monitor, bi=bar_index: self._remove_bar(m, bi),
            )
            self._bars[key] = new_bar

            dash = self._dashes.get(monitor)
            if dash is not None:
                new_bar.register_dash_callback(dash.applets.refresh_bar_state)

        if monitor not in self._dashes:
            monitor_bars = [bar for (m, _), bar in self._bars.items() if m == monitor]
            self._dashes[monitor] = Dash(monitor_id, self)

        if monitor not in self._osds:
            self._osds[monitor] = OSD(monitor_id)

    def _remove_bar(self, monitor: Gdk.Monitor, bar_index: int = None) -> None:
        if bar_index is not None:
            bar = self._bars.pop((monitor, bar_index), None)
            if bar:
                bar.destroy()

            dash = self._dashes.get(monitor)
            if dash:
                dash.applets.refresh_bar_state()
            if not any(m == monitor for m, _ in self._bars):
                self._cleanup_monitor(monitor)
        else:
            for key in [k for k in self._bars if k[0] == monitor]:
                self._bars.pop(key).destroy()
            self._cleanup_monitor(monitor)

    def _cleanup_monitor(self, monitor: Gdk.Monitor) -> None:
        for collection in (self._notifications, self._dashes, self._osds):
            widget = collection.pop(monitor, None)
            if widget:
                widget.destroy()

    def _on_monitor_added(self, display: Gdk.Display, monitor: Gdk.Monitor) -> None:
        for i in range(display.get_n_monitors()):
            if display.get_monitor(i) == monitor:
                self._add_bar(monitor, i)
                break
        return False

    def _on_monitor_removed(self, display: Gdk.Display, monitor: Gdk.Monitor) -> None:
        self._remove_bar(monitor)

    def toggle(self, key: str):
        active_output = wm.active_output
        for (monitor, bar_index), bar in self._bars.items():
            if get_connector_from_monitor_id(bar.monitor_id) != active_output:
                continue
            if key == "Dash":
                dash = self._dashes.get(monitor)
                if dash:
                    dash.toggle()
                return
            if key == "EditApplets":
                dash = self._dashes.get(monitor)
                if dash:
                    dash.toggle_applets()
                return
            for section in bar.sections.values():
                for child in section.get_children():
                    if isinstance(child, WidgetWrapper) and child.widget_key == key:
                        popup = child._ensure_popup()
                        if popup:
                            popup.toggle()
                        return
                    elif isinstance(child, GroupWrapper) and key in child.widget_keys:
                        popup = child._ensure_popup()
                        if popup:
                            popup.toggle()
                        return
            return

    def apply_blur(self, enabled: bool) -> None:
        for bar in self._bars.values():
            bar.apply_blur(enabled)

    def add_bar_for_monitor(self, monitor_id: int) -> None:
        monitor_cfg = next(
            (c for c in user_options.bars.configs if c.get("monitor") == monitor_id),
            None,
        )
        
        existing_alignment = "top"
        if monitor_cfg and monitor_cfg.get("bars"):
            existing_alignment = monitor_cfg["bars"][0].get("alignment", "top")
        new_alignment = "bottom" if existing_alignment == "top" else "top"

        new_bar_cfg = {
            "alignment": new_alignment,
            "floating_bar": False,
            "floating_applets": True,
            "rounded_edges": True,
            "min_width": False,
            "auto_hide": False,
            "left": [],
            "center": [],
            "right": [],
        }
        monitor_cfg = next(
            (c for c in user_options.bars.configs if c.get("monitor") == monitor_id),
            None,
        )
        if monitor_cfg is not None:
            monitor_cfg["bars"].append(new_bar_cfg)
        else:
            user_options.bars.configs.append({"monitor": monitor_id, "bars": [new_bar_cfg]})
        user_options.save()

        monitor = Gdk.Display.get_default().get_monitor(monitor_id)
        if monitor:
            self._add_bar(monitor, monitor_id)
    def set_bars_overlay(self, monitor):
        for (m, _), bar in self._bars.items():
            if m != monitor:
                continue

            GtkLayerShell.set_layer(bar, GtkLayerShell.Layer.OVERLAY)
    def set_bars_top(self, monitor):
        for (m, _), bar in self._bars.items():
            if m != monitor:
                continue
            GtkLayerShell.set_layer(bar, GtkLayerShell.Layer.TOP)
def initialise_bars():
    return BarManager()