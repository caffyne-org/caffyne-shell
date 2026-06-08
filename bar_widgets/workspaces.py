from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.overlay import Overlay
from fabric.widgets.label import Label
from snippets import Animator, ClippingBox
from gi.repository import Gtk, Gdk, GLib
from services.singletons import wm, edit_mode
from utils.helpers import get_app_icon_name
from utils.monitors import get_connector_from_monitor_id
import cairo
import math

PILL_HEIGHT = 2
PILL_RADIUS = 2
PILL_DURATION_SLIDE = 0.25
PILL_DURATION_MORPH = 0.15
PILL_BEZIER_SLIDE = (0.4, 0.0, 0.2, 1.0)
PILL_BEZIER_MORPH = (0.4, 0.0, 1.0, 1.0)

class WorkspaceButton(EventBox):
    def __init__(self, workspace, windows, variant):
        self.variant = variant
        self.workspace = workspace
        self.icon_map: dict[int, Image] = {}
        self._icon_box = Box(spacing=8)

        for w in windows:
            if w.workspace_id == workspace.id:
                icon = Image(
                    css_classes=["icon"],
                    icon_name=self._get_icon(w),
                    icon_size=20,
                )
                self.icon_map[w.id] = icon
                self._icon_box.add(icon)

        super().__init__(
            child=Box(
                style_classes=["workspace"] + (["active"] if workspace.is_active else []),
                orientation="v",
                spacing=8,
                children=[self._icon_box],
            ),
        )
        self.connect("button-release-event", self._on_click)

    def _on_click(self, _, event):
        if edit_mode.edit_mode:
            return False
        if event.button == 1:
            self.workspace.switch_to()
        return False
    def _get_icon(self, window) -> str:
        app_id = window.app_id
        return (
            get_app_icon_name(app_id)
            or get_app_icon_name(app_id.lower())
            or "application-x-executable-symbolic"
        )

    def set_active(self, active: bool):
        ctx = self.get_child().get_style_context()
        if active:
            ctx.add_class("active")
        else:
            ctx.remove_class("active")

    def add_window(self, window, all_windows: list):
        if window.id in self.icon_map:
            return
        icon = Image(
            css_classes=["icon"],
            icon_name=self._get_icon(window),
            icon_size=20,
        )
        self.icon_map[window.id] = icon

        ws_windows = sorted(
            [w for w in all_windows if w.workspace_id == self.workspace.id],
            key=lambda w: w.sort_key() or [0, 0]
        )
        idx = next(
            (i for i, w in enumerate(ws_windows) if w.id == window.id),
            len(self.icon_map),
        )
        self._icon_box.add(icon)
        self._icon_box.reorder_child(icon, idx)
        self._icon_box.show_all()

    def remove_window(self, window_id: int):
        icon = self.icon_map.pop(window_id, None)
        if icon:
            self._icon_box.remove(icon)

    def reorder_icons(self, all_windows: list):
        ws_windows = sorted(
            [w for w in all_windows if w.workspace_id == self.workspace.id],
            key=lambda w: w.sort_key(),
        )
        current_children = set(self._icon_box.get_children())
        for idx, w in enumerate(ws_windows):
            icon = self.icon_map.get(w.id)
            if icon and icon in current_children:
                self._icon_box.reorder_child(icon, idx)

class WorkspaceNumberButton(EventBox):
    def __init__(self, workspace):
        self.workspace = workspace
        super().__init__(
            child=Box(
                style_classes=["workspace"] + (["active"] if workspace.is_active else []),
                children=[
                    Label(h_expand=True, h_align="center", label=str(workspace.idx)),
                ],
            ),
        )
        self.connect("button-release-event", self._on_click)

    def _on_click(self, _, event):
        if edit_mode.edit_mode:
            return False
        if event.button == 1:
            self.workspace.switch_to()
        return False
    
    def sync_index(self, workspace):
        self.workspace = workspace
        self.get_child().get_children()[0].set_label(str(workspace.idx))

    def set_active(self, active: bool):
        ctx = self.get_child().get_style_context()
        if active:
            ctx.add_class("active")
        else:
            ctx.remove_class("active")

class WorkspacePill(Gtk.DrawingArea):
    def __init__(self, offset: int = 13, width=8, **kwargs):
        super().__init__(**kwargs)
        self.get_style_context().add_class("workspace-pill")
        self.set_has_window(False)
        self._offset = offset

        self._x = 0.0
        self._width = 0.0
        self._max_width = width
        self._anim_x_start = 0.0
        self._anim_x_end = 0.0
        self._anim_w_start = 0.0
        self._anim_w_end = 0.0

        self._slide_anim = Animator(
            bezier_curve=PILL_BEZIER_SLIDE,
            duration=PILL_DURATION_SLIDE,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self,
        )
        self._slide_anim.connect("notify::value", self._on_slide_tick)

        self._morph_anim = Animator(
            bezier_curve=PILL_BEZIER_MORPH,
            duration=PILL_DURATION_MORPH,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self,
        )
        self._morph_anim.connect("notify::value", self._on_morph_tick)

        self._state = "idle"
        self._pending_x = None
        self._pending_workspace_id = None
        self._last_workspace_id = None
        self.connect("draw", self._on_draw)

    def move_to(self, x: float, workspace_id: int | None = None):
        same_workspace = (workspace_id is None or workspace_id == self._last_workspace_id)

        if self._width < 0.5:

            if workspace_id is not None:
                self._last_workspace_id = workspace_id
            self._x = x
            self._anim_x_start = x
            self._anim_x_end = x
            self._expand()
            return

        if same_workspace:
            if workspace_id is not None:
                self._last_workspace_id = workspace_id
            self._slide_to(x)
        else:

            self._slide_anim.pause()
            self._anim_x_start = self._x

            self._pending_x = x
            self._pending_workspace_id = workspace_id
            self._shrink()

    def hide_pill(self):
        """Shrink the pill to nothing (no active window)."""
        if self._width > 0.5:
            self._pending_x = None
            self._shrink()

    def _slide_to(self, x: float):
        self._state = "sliding"
        self._anim_x_start = self._x
        self._anim_x_end = x
        self._play_anim(self._slide_anim)

    def _shrink(self):
        self._state = "shrinking"
        self._anim_w_start = self._width
        self._anim_w_end = 0.0
        self._morph_anim.bezier_curve = PILL_BEZIER_MORPH
        self._play_anim(self._morph_anim)

    def _expand(self):

        if hasattr(self, '_pending_workspace_id') and self._pending_workspace_id is not None:
            self._last_workspace_id = self._pending_workspace_id
            self._pending_workspace_id = None
        self._state = "expanding"
        self._anim_w_start = self._width
        self._anim_w_end = self._max_width
        self._morph_anim.bezier_curve = (0.0, 0.0, 0.6, 1.0)
        self._play_anim(self._morph_anim)

    def _play_anim(self, anim):
        anim.pause()
        anim.min_value = 0.0
        anim.max_value = 1.0
        anim.value = 0.0
        anim.play()

    def _on_slide_tick(self, *_):
        t = self._slide_anim.value
        self._x = self._anim_x_start + (self._anim_x_end - self._anim_x_start) * t
        self.queue_draw()

    def _on_morph_tick(self, *_):
        t = self._morph_anim.value
        self._width = self._anim_w_start + (self._anim_w_end - self._anim_w_start) * t
        self.queue_draw()

        if self._state == "shrinking" and t >= 1.0 and self._pending_x is not None:
            pending = self._pending_x
            self._pending_x = None
            self._state = "idle"
            self._x = pending
            GLib.idle_add(self._expand)

    def _on_draw(self, widget, cr: cairo.Context):
        if self._width < 0.5:
            return False

        alloc = widget.get_allocation()
        cx = self._x
        cy = (alloc.height / 2) + self._offset

        style = widget.get_style_context()
        color = style.get_color(Gtk.StateFlags.NORMAL)
        cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)

        w = self._width
        h = PILL_HEIGHT
        r = min(PILL_RADIUS, w / 2, h / 2)
        x = cx - w / 2
        y = cy - h / 2

        if w < 1.0:
            return False

        cr.new_sub_path()
        cr.arc(x + r,     y + r,     r,  math.pi,       3 * math.pi / 2)
        cr.arc(x + w - r, y + r,     r, -math.pi / 2,   0)
        cr.arc(x + w - r, y + h - r, r,  0,              math.pi / 2)
        cr.arc(x + r,     y + h - r, r,  math.pi / 2,   math.pi)
        cr.close_path()
        cr.fill()

        return False

class Workspaces(EventBox):
    VARIANTS = ["dots", "numbers", "icons+pill"]
    def __init__(self, monitor_id: int, vertical: bool, variant: str = None, **kwargs):
        self.monitor_name = get_connector_from_monitor_id(monitor_id)
        self._variant = variant or "icons+pill"
        self._ws_buttons: dict[int, WorkspaceButton] = {}
        self._dot_buttons: dict[int, Button] = {}

        self._buttons_box = ClippingBox(
            style_classes=(
                ["workspace-dots-container"] if self._variant == "dots"
                else ["workspace-numbers-container"] if self._variant == "numbers"
                else ["workspace-button-container"]
            ),
            v_expand=False, v_align="center", spacing=1 if self._variant == "numbers" else 4 if self._variant == "dots" else 6
        )

        if self._variant == "icons+pill":
            self._pill = WorkspacePill()
            self._overlay = Overlay(
                child=self._buttons_box,
                overlays=[self._pill],
            )
            self._pill.set_halign(Gtk.Align.FILL)
            self._pill.set_valign(Gtk.Align.FILL)
            child = self._overlay
            self._overlay.set_overlay_pass_through(self._pill, True)
            self._pill.show_all()

        else:
            self._pill = None
            child = self._buttons_box

        super().__init__(
            events=["scroll", "smooth-scroll"],
            style_classes=["workspaces"],
            child=child,
            **kwargs,
        )

        self._signal_ids = []
        self._signal_ids.append(wm.connect("notify::windows", self._on_windows_changed))
        self._signal_ids.append(wm.connect("notify::workspaces", self._on_workspaces_changed))
        if self._pill:
            self._signal_ids.append(wm.connect("notify::active-window", self._on_active_window_changed))

        self.connect("destroy", self._on_destroy)
        self.connect("scroll-event", self._on_scroll)
        self.connect("button-release-event", self._on_click)
        self._rebuild() 

    def _on_destroy(self, *_):
        for sig_id in self._signal_ids:
            wm.disconnect(sig_id)
        self._signal_ids.clear()

    def _on_scroll(self, widget, event):
        if event.direction == Gdk.ScrollDirection.UP:
            self._scroll("up")
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self._scroll("down")
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            _, dx, dy = event.get_scroll_deltas()
            if dy < -0.5:
                self._scroll("up")
            elif dy > 0.5:
                self._scroll("down")
        return True
    
    def _on_click(self, _, event):
        if self._variant != "dots":
            return False
        if event.button == 1:
            self._scroll("down")
        return False
    
    def _sync_dots(self):
        current_ids = set(self._dot_buttons.keys())
        new_ids = {ws.id for ws in wm.workspaces if ws.output == self.monitor_name}

        for ws_id in current_ids - new_ids:
            btn = self._dot_buttons.pop(ws_id)
            self._buttons_box.remove(btn)
            btn.destroy()

        for ws in wm.workspaces:
            if ws.output != self.monitor_name:
                continue
            if ws.id not in self._dot_buttons:
                btn = Button(style_classes=["workspace-dot"])
                # btn.connect("clicked", lambda *_, w=ws: w.switch_to())
                self._dot_buttons[ws.id] = btn
                self._buttons_box.add(btn)

        for ws in wm.workspaces:
            if ws.id in self._dot_buttons:
                ctx = self._dot_buttons[ws.id].get_style_context()
                if ws.is_active:
                    ctx.add_class("active")
                else:
                    ctx.remove_class("active")

        self._buttons_box.show_all()
    def _sync_numbers(self):
        current_ids = set(self._ws_buttons.keys())
        new_ids = {ws.id for ws in wm.workspaces if ws.output == self.monitor_name}

        for ws_id in current_ids - new_ids:
            btn = self._ws_buttons.pop(ws_id)
            self._buttons_box.remove(btn)
            btn.destroy()

        for ws in wm.workspaces:
            if ws.output != self.monitor_name:
                continue
            if ws.id not in self._ws_buttons:
                btn = WorkspaceNumberButton(ws)
                self._ws_buttons[ws.id] = btn
                self._buttons_box.add(btn)
            else:
                self._ws_buttons[ws.id].set_active(ws.is_active)

        sorted_workspaces = sorted(
            [ws for ws in wm.workspaces if ws.id in self._ws_buttons],
            key=lambda ws: ws.idx,
        )
        for idx, ws in enumerate(sorted_workspaces):
            self._buttons_box.reorder_child(self._ws_buttons[ws.id], idx)
            self._ws_buttons[ws.id].sync_index(ws)

        self._buttons_box.show_all()
    def _sync_workspaces(self):
        windows = wm.windows
        current_ids = set(self._ws_buttons.keys())
        new_ids = {
            ws.id for ws in wm.workspaces
            if ws.output == self.monitor_name
            and any(w.workspace_id == ws.id for w in windows)
        }

        for ws_id in current_ids - new_ids:
            btn = self._ws_buttons.pop(ws_id)
            self._buttons_box.remove(btn)
            btn.destroy()

        for ws in wm.workspaces:
            if ws.output != self.monitor_name:
                continue
            if not any(w.workspace_id == ws.id for w in windows):
                continue
            if ws.id not in self._ws_buttons:
                btn = WorkspaceButton(ws, windows, self._variant)
                self._ws_buttons[ws.id] = btn
                self._buttons_box.add(btn)
            else:
                self._ws_buttons[ws.id].set_active(ws.is_active)

        sorted_workspaces = sorted(
            [ws for ws in wm.workspaces if ws.id in self._ws_buttons],
            key=lambda ws: ws.idx,
        )
        for idx, ws in enumerate(sorted_workspaces):
            self._buttons_box.reorder_child(self._ws_buttons[ws.id], idx)

        self._buttons_box.show_all()

    def _on_windows_changed(self, *_):
        if self._variant == "icons+pill":
            windows = wm.windows
            window_ids = {w.id for w in windows}

            for ws_id, btn in list(self._ws_buttons.items()):
                for w_id in list(btn.icon_map.keys()):
                    if w_id not in window_ids:
                        btn.remove_window(w_id)

            for w in windows:
                for ws_id, btn in list(self._ws_buttons.items()):
                    if ws_id != w.workspace_id and w.id in btn.icon_map:
                        btn.remove_window(w.id)

            for w in windows:
                if w.workspace_id in self._ws_buttons:
                    self._ws_buttons[w.workspace_id].add_window(w, windows)

            for btn in self._ws_buttons.values():
                btn.reorder_icons(windows)

            self._sync_workspaces()

        if self._pill:
            GLib.idle_add(self._on_active_window_changed)
    
    def _on_workspaces_changed(self, *_):
        if self._variant == "dots":
            self._sync_dots()
        elif self._variant == "icons+pill":
            self._sync_workspaces()
        else:
            self._sync_numbers()
            
    def _rebuild(self):
        for child in self._buttons_box.get_children():
            self._buttons_box.remove(child)
        self._ws_buttons.clear()
        self._dot_buttons.clear()

        if self._variant == "dots":
            self._sync_dots()
        elif self._variant == "numbers":
            self._sync_numbers()
        else:
            self._sync_workspaces()

    def _on_active_window_changed(self, *_):
        if not self._pill:
            return

        active = wm.active_window
        if not active:
            self._pill.hide_pill()
            return

        ws_btn = self._ws_buttons.get(active.workspace_id)
        if not ws_btn:
            self._pill.hide_pill()
            return

        icon = ws_btn.icon_map.get(active.id)
        if not icon:
            self._pill.hide_pill()
            return

        GLib.idle_add(self._move_pill_to_icon, icon, active.workspace_id)

    def _move_pill_to_icon(self, icon: Image, workspace_id: int):
        try:
            x, y = icon.translate_coordinates(self._overlay, 0, 0)
        except Exception:
            return False
        alloc = icon.get_allocation()
        self._pill.move_to(x + alloc.width / 2, workspace_id=workspace_id)
        return False

    def _scroll(self, direction: str):
        if edit_mode.edit_mode:
            return False
        monitor_workspaces = [
            ws for ws in wm.workspaces
            if ws.output == self.monitor_name
        ]
        if not monitor_workspaces:
            return
        current_idx = next(
            (i for i, ws in enumerate(monitor_workspaces) if ws.is_active), None
        )
        if current_idx is None:
            return
        if direction == "up":
            next_idx = (current_idx - 1) % len(monitor_workspaces)
        else:
            next_idx = (current_idx + 1) % len(monitor_workspaces)
        monitor_workspaces[next_idx].switch_to()