import cairo
from urllib.parse import unquote

import gi
gi.require_version("Gtk", "3.0")
import math
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell
from fabric.core.service import Service, Signal
from fabric.widgets.wayland import WaylandWindow
from fabric.widgets.box import Box
from fabric.widgets.overlay import Overlay
from loguru import logger
from services.singletons import plugins
from user_options import user_options
from utils.helpers import popup_with_blur
from desktop_applets import DESKTOP_APPLET_SIZES, DESKTOP_APPLET_WIDGETS, DESKTOP_CANVAS_SIZES
from .themes import wp
from snippets import Animator, disable_blur, free_blur, set_blur_regions_from_widget, enable_blur, trace_widget, wl_surface_id
from snippets.blur.blur import set_blur_regions

CELL      = 81
GAP       = 12
CELL_STEP = CELL + GAP  # 93

_APPLET_TARGET = Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)


def _applet_pixel_size(key: str) -> tuple[int, int]:
    cols, rows = DESKTOP_CANVAS_SIZES.get(key, (1, 1))
    w = cols * 2 * CELL + (cols * 2 - 1) * GAP
    h = rows * 2 * CELL + (rows * 2 - 1) * GAP
    return w, h


def _applet_cell_size(key: str) -> tuple[int, int]:
    """Return the (cols, rows) cell footprint for a canvas applet key."""
    cols, rows = DESKTOP_CANVAS_SIZES.get(key, (1, 1))
    return cols * 2, rows * 2


def _grid_to_pixel(grid_x: int, grid_y: int) -> tuple[int, int]:
    return grid_x * CELL_STEP, grid_y * CELL_STEP


def _fits(grid_x: int, grid_y: int, key: str, cols: int, rows: int) -> bool:
    cc, cr = _applet_cell_size(key)
    return grid_x + cc <= cols and grid_y + cr <= rows


def _conflicts(
    grid_x: int, grid_y: int, key: str,
    placed: list[dict], cols: int, rows: int,
    ignore_key: str | None = None,
) -> bool:
    cc, cr = _applet_cell_size(key)
    new_cells = {
        (grid_x + dx, grid_y + dy)
        for dx in range(cc)
        for dy in range(cr)
    }
    for entry in placed:
        if ignore_key and entry["key"] == ignore_key:
            continue
        ec, er = _applet_cell_size(entry["key"])
        existing = {
            (entry["grid_x"] + dx, entry["grid_y"] + dy)
            for dx in range(ec)
            for dy in range(er)
        }
        if new_cells & existing:
            return True
    return False


def _render_shape(cr: cairo.Context, x: float, y: float, w: float, h: float, radius: float) -> None:
    cr.new_sub_path()
    cr.arc(x + w - radius, y + radius,         radius, -math.pi / 2, 0)
    cr.arc(x + w - radius, y + h - radius,     radius, 0,             math.pi / 2)
    cr.arc(x + radius,     y + h - radius,     radius, math.pi / 2,  math.pi)
    cr.arc(x + radius,     y + radius,         radius, math.pi,      3 * math.pi / 2)
    cr.close_path()


class _CanvasDrawingArea(Gtk.DrawingArea):
    _PREVIEW_CLASS         = "desktop-applet-preview"
    _PREVIEW_VALID_CLASS   = "valid"
    _PREVIEW_INVALID_CLASS = "invalid"

    def __init__(self, window: "DesktopAppletWindow"):
        super().__init__()
        self._win = window
        self.set_hexpand(True)
        self.set_vexpand(True)

        self.add_events(Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("draw",               self._on_draw)
        self.connect("leave-notify-event", self._on_leave)

    def _get_color(self, name: str) -> tuple[float, float, float, float]:
        ctx = self._win.get_style_context()
        found, color = ctx.lookup_color(name)
        if found:
            return color.red, color.green, color.blue, color.alpha
        return (1.0, 1.0, 1.0, 0.08)

    def _get_preview_styles(self, valid: bool) -> tuple[tuple, tuple, float]:
        ctx = self.get_style_context()
        ctx.add_class(self._PREVIEW_CLASS)
        if valid:
            ctx.add_class(self._PREVIEW_VALID_CLASS)
            ctx.remove_class(self._PREVIEW_INVALID_CLASS)
        else:
            ctx.add_class(self._PREVIEW_INVALID_CLASS)
            ctx.remove_class(self._PREVIEW_VALID_CLASS)

        bg     = ctx.get_background_color(self.get_state_flags())
        border = ctx.get_border_color(self.get_state_flags())
        radius = ctx.get_property("border-radius", self.get_state_flags())

        ctx.remove_class(self._PREVIEW_CLASS)
        ctx.remove_class(self._PREVIEW_VALID_CLASS)
        ctx.remove_class(self._PREVIEW_INVALID_CLASS)

        return (
            (bg.red,     bg.green,     bg.blue,     bg.alpha),
            (border.red, border.green, border.blue, border.alpha),
            float(radius if isinstance(radius, (int, float)) else 12.0),
        )

    def _on_leave(self, widget, event: Gdk.EventCrossing) -> bool:
        win = self._win
        if win._ph_grid_x is not None:
            win._ph_grid_x = None
            win._ph_grid_y = None
            win._ph_valid  = False
            self.queue_draw()
        return False

    def _on_draw(self, widget, cr: cairo.Context) -> bool:
        win = self._win
        if win._cols == 0 or win._rows == 0:
            return False

        empty_r,    empty_g,    empty_b,    empty_a    = self._get_color("canvas-empty")
        occupied_r, occupied_g, occupied_b, occupied_a = self._get_color("canvas-occupied")
        border_r,   border_g,   border_b,   border_a   = self._get_color("canvas-border")

        placed = user_options.desktop_canvas.get_applets(win._monitor_id)

        occupied: set[tuple[int, int]] = set()
        for entry in placed:
            if entry["key"] == win._dragging_key:
                continue
            ec, er = _applet_cell_size(entry["key"])
            for dx in range(ec):
                for dy in range(er):
                    occupied.add((entry["grid_x"] + dx, entry["grid_y"] + dy))

        cell_radius = 6.0

        for gy in range(win._rows):
            for gx in range(win._cols):
                px = win._pad_x + gx * CELL_STEP
                py = win._pad_y + gy * CELL_STEP

                if (gx, gy) in occupied:
                    cr.set_source_rgba(occupied_r, occupied_g, occupied_b, occupied_a)
                else:
                    cr.set_source_rgba(empty_r, empty_g, empty_b, empty_a)
                _render_shape(cr, px, py, CELL, CELL, cell_radius)
                cr.fill()

                cr.set_source_rgba(border_r, border_g, border_b, border_a)
                _render_shape(cr, px, py, CELL, CELL, cell_radius)
                cr.set_line_width(1.0)
                cr.stroke()

        if win._ph_grid_x is not None and win._dragging_key is not None:
            px = win._pad_x + win._ph_grid_x * CELL_STEP
            py = win._pad_y + win._ph_grid_y * CELL_STEP
            pw, ph = _applet_pixel_size(win._dragging_key)

            bg_rgba, border_rgba, preview_radius = self._get_preview_styles(win._ph_valid)

            # Fill
            cr.set_source_rgba(*bg_rgba)
            _render_shape(cr, px, py, pw, ph, preview_radius)
            cr.fill()

            # Border
            cr.set_source_rgba(*border_rgba)
            _render_shape(cr, px, py, pw, ph, preview_radius)
            cr.set_line_width(2.0)
            cr.stroke()

        return False



class DesktopAppletWindow(WaylandWindow):

    def __init__(self, monitor_id: int) -> None:
        self._monitor_id   = monitor_id
        self._fixed        = Gtk.Fixed()
        self._children: dict[str, Gtk.Widget] = {}

        self._pad_x = 0
        self._pad_y = 0
        self._cols  = 0
        self._rows  = 0
        self._old_w = 0
        self._old_h = 0

        self._recalc_in_progress = False
        self._pending_recalc     = False
        self._recalc_timer: int | None = None
        self._fade_in_timer: int | None = None
        self._ready              = False
        self._in_size_allocate   = False
        self._blur_ctx = None
        self._blur_surface = 0
        self._retrace_source: int | None = None
        self._retrace_retries = 0
        self._style_service = None
        self._style_handler: int | None = None

        self._canvas_active  = False
        self._dragging_key: str | None = None
        self._drag_origin: tuple[int, int] | None = None
        self._ph_grid_x: int | None = None
        self._ph_grid_y: int | None = None
        self._ph_valid:  bool       = False

        self._canvas_da = _CanvasDrawingArea(self)
        self._canvas_da.set_no_show_all(True)

        self._overlay = Overlay(h_expand=True, v_expand=True)
        self._overlay.add(self._canvas_da)
        self._overlay.add_overlay(self._fixed)
        # self._overlay.set_overlay_pass_through(self._fixed, True)

        self._root = Box(h_expand=True, v_expand=True)
        self._root.add(self._overlay)

        self._fade_animator = Animator(
            bezier_curve=(0.4, 0.0, 0.2, 1.0),
            duration=0.4,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self._root,
        )
        self._fade_animator.connect("notify::value", self._on_fade_value)
        self._fade_animator.connect("finished",      self._on_fade_finished)

        self._fade_out_animator = Animator(
            bezier_curve=(0.4, 0.0, 0.2, 1.0),
            duration=0.2,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self._root,
        )
        self._fade_out_animator.connect("notify::value", self._on_fade_out_value)
        self._fade_out_animator.connect("finished",      self._on_fade_out_finished)

        self._canvas_fade_in = Animator(
            bezier_curve=(0.4, 0.0, 0.2, 1.0),
            duration=0.25,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self._root,
        )
        self._canvas_fade_in.connect("notify::value",
            lambda a, _: self._canvas_da.set_opacity(a.value))
        self._canvas_fade_in.connect("finished",
            lambda _: self._canvas_da.set_opacity(1.0))

        self._canvas_fade_out = Animator(
            bezier_curve=(0.4, 0.0, 0.2, 1.0),
            duration=0.2,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self._root,
        )
        self._canvas_fade_out.connect("notify::value",
            lambda a, _: self._canvas_da.set_opacity(a.value))
        self._canvas_fade_out.connect("finished", self._on_canvas_fade_out_done)

        self._overlay.set_opacity(0.0)

        super().__init__(
            monitor=monitor_id,
            anchor="left right top bottom",
            exclusivity="ignore",
            layer="bottom",
            child=self._root,
            visible=True,
            title="caffyne-shell-desktop-applets",
        )

        self.connect("size-allocate",      self._on_size_allocate)
        self.connect("button-press-event", self._on_button_press)
        self._setup_drag_and_drop()
        self.show_all()
        
        GLib.timeout_add(1000, self._initial_build)

    def _initial_build(self) -> bool:
        self._ready = True
        self.recalculate_grid()
        return False

    def _on_fade_value(self, animator, _) -> None:
        self._overlay.set_opacity(animator.value)

    def _on_fade_finished(self, _) -> None:
        self._overlay.set_opacity(1.0)

    def _fade_in(self) -> None:
        if self._fade_animator.playing:
            return
        self._fade_out_animator.pause()
        self._fade_animator.min_value = self._overlay.get_opacity()
        self._fade_animator.value     = self._overlay.get_opacity()
        self._fade_animator.max_value = 1.0
        self._fade_animator.play()

    def _fade_out(self) -> None:
        self._fade_animator.pause()
        self._fade_out_animator.min_value = 0.0
        self._fade_out_animator.max_value = self._overlay.get_opacity()
        self._fade_out_animator.value     = self._overlay.get_opacity()
        self._fade_out_animator.play()

    def _on_fade_out_value(self, animator, _) -> None:
        self._overlay.set_opacity(animator.value)

    def _on_fade_out_finished(self, _) -> None:
        self._overlay.set_opacity(0.0)

    def _schedule_fade_in(self) -> None:
        if self._fade_in_timer is not None:
            GLib.source_remove(self._fade_in_timer)
        self._fade_in_timer = GLib.timeout_add(300, self._do_fade_in)

    def _do_fade_in(self) -> bool:
        self._fade_in_timer = None
        self._fade_in()
        return False
    
    # -- blur ---------------------------------------------------------------
    #
    # A BlurContext stores the wl_surface it was created with and commits that
    # surface on every call, and this window drops and rebuilds its surface on
    # every grid recalculation -- _do_window_resize() hides and shows it to
    # force a fresh allocation. So a context is never valid for the lifetime of
    # the window: each retrace compares the surface its context holds against
    # the one the window has now, and rebuilds when they differ. Committing the
    # stale one segfaults inside libwayland.

    RETRACE_RETRY_MS    = 150
    RETRACE_MAX_RETRIES = 20

    def _apply_blur(self) -> None:
        if not user_options.theme.blur:
            return

        if self._style_handler is None:
            from .singletons import style_service

            self._style_service = style_service
            # A "notify::" handler is invoked with (object, pspec), which
            # _retrace_blur takes neither of: connected directly it raised on
            # every style change instead of retracing.
            self._style_handler = style_service.connect(
                "notify::style-changed", lambda *_: self.schedule_retrace_blur()
            )

        self.schedule_retrace_blur()

    def schedule_retrace_blur(self) -> None:
        """Coalesce retrace requests into a single pass on the next idle.

        Repositioning, adding, removing and dropping an applet each ask for a
        retrace, and a grid recalculation does all of them in a row. Tracing
        every applet offscreen is not cheap enough to run once per request.
        """
        if self._retrace_source is not None:
            return
        self._retrace_retries = 0
        self._retrace_source  = GLib.idle_add(self._on_retrace_source)

    def _on_retrace_source(self) -> bool:
        self._retrace_source = None
        self._retrace_blur()
        return False

    def _retry_retrace_blur(self) -> None:
        """Come back once the window has been mapped again.

        A recalculation hides the window, and the retrace it schedules on the
        way out can land before GTK has finished remapping it and handing it a
        new wl_surface. Without a retry the applets would simply lose their
        blur until something else happened to ask for one.
        """
        if self._retrace_source is not None:
            return
        if self._retrace_retries >= self.RETRACE_MAX_RETRIES:
            return
        self._retrace_retries += 1
        self._retrace_source = GLib.timeout_add(
            self.RETRACE_RETRY_MS, self._on_retrace_source
        )

    def _teardown_blur_ctx(self) -> None:
        """Release the context, committing only a surface that is still live.

        blur_disable() commits the surface the context was built with, so it is
        safe only while that surface is still the window's. blur_free() touches
        nothing but its own allocation and is safe either way.
        """
        ctx, surface       = self._blur_ctx, self._blur_surface
        self._blur_ctx     = None
        self._blur_surface = 0
        if ctx is None:
            return
        if surface and surface == wl_surface_id(self):
            disable_blur(ctx)
        free_blur(ctx)

    def _retrace_blur(self) -> None:
        if not user_options.theme.blur:
            self._teardown_blur_ctx()
            return

        surface = wl_surface_id(self)
        if not surface:
            # Unmapped, or partway through the hide/show of a recalculation.
            # Every libblur entry point commits the surface, so there is
            # nothing safe to do until the window owns one again.
            self._teardown_blur_ctx()
            self._retry_retrace_blur()
            return

        if self._blur_ctx is None or surface != self._blur_surface:
            self._teardown_blur_ctx()
            self._blur_ctx = enable_blur(self)
            if not self._blur_ctx:
                return
            self._blur_surface = surface

        rects = []
        for eb in self._children.values():
            # get_mapped() rather than get_visible(): a widget hidden by its
            # parent, or by the drag that is about to move it, still reports
            # itself visible, and tracing one draws it into the scratch surface
            # at whatever stale allocation it last had.
            if not eb.get_mapped():
                continue
            alloc = eb.get_allocation()
            if alloc.width <= 0 or alloc.height <= 0:
                continue
            coords = eb.translate_coordinates(self, 0, 0)
            if not coords:
                continue
            cx, cy = coords
            for r in trace_widget(eb):
                rects.append((cx + r.x, cy + r.y, r.width, r.height))

        if not rects:
            # Clear the region but keep the context. The applets are only
            # hidden -- mid-drag, or between a rebuild and its reposition --
            # and freeing here left nothing to restore the blur when they came
            # back.
            disable_blur(self._blur_ctx)
            return

        set_blur_regions(self._blur_ctx, rects)

    def _show_canvas(self) -> None:
        self._canvas_da.set_opacity(0.0)
        self._canvas_da.show()
        self._canvas_fade_out.pause()
        self._canvas_fade_in.min_value = 0.0
        self._canvas_fade_in.value     = 0.0
        self._canvas_fade_in.max_value = 1.0
        self._canvas_fade_in.play()

    def _hide_canvas(self) -> None:
        self._canvas_fade_in.pause()
        self._canvas_fade_out.max_value = self._canvas_da.get_opacity()
        self._canvas_fade_out.value     = self._canvas_da.get_opacity()
        self._canvas_fade_out.min_value = 0.0
        self._canvas_fade_out.play()

    def _on_canvas_fade_out_done(self, _) -> None:
        self._canvas_da.set_opacity(0.0)
        self._canvas_da.hide()

    def enter_canvas_mode(self, key: str, origin: tuple[int, int] | None = None) -> None:
        self._canvas_active = True
        self._dragging_key  = key
        self._drag_origin   = origin
        self._ph_grid_x     = None
        self._ph_grid_y     = None
        self._ph_valid      = False

        self.layer = "overlay"

        self._show_canvas()
        self._canvas_da.queue_draw()

    def exit_canvas_mode(self, restore: bool = False) -> None:
        if restore and self._drag_origin is not None and self._dragging_key is not None:
            key = self._dragging_key
            gx, gy = self._drag_origin
            DesktopAppletService.get_instance().place(self._monitor_id, key, gx, gy)

        self._canvas_active = False
        self._dragging_key  = None
        self._drag_origin   = None
        self._ph_grid_x     = None
        self._ph_grid_y     = None
        self._ph_valid      = False

        self.layer = "bottom"
        self._hide_canvas()

    def _xy_to_grid(self, x: float, y: float) -> tuple[int, int]:
        gx = max(0, min(self._cols - 1, int((x - self._pad_x) / CELL_STEP)))
        gy = max(0, min(self._rows - 1, int((y - self._pad_y) / CELL_STEP)))
        return gx, gy
    
    def _on_canvas_drag_motion(self, widget, ctx, x, y, time):
        key = self._dragging_key
        if key is None:
            Gdk.drag_status(ctx, 0, time)
            return True

        gx, gy = self._xy_to_grid(x, y)
        placed  = user_options.desktop_canvas.get_applets(self._monitor_id)

        valid = (
            _fits(gx, gy, key, self._cols, self._rows)
            and not _conflicts(gx, gy, key, placed, self._cols, self._rows,
                               ignore_key=key)
        )

        if gx != self._ph_grid_x or gy != self._ph_grid_y or valid != self._ph_valid:
            self._ph_grid_x = gx
            self._ph_grid_y = gy
            self._ph_valid  = valid
            self._canvas_da.queue_draw()

        Gdk.drag_status(ctx, Gdk.DragAction.MOVE if valid else 0, time)
        return True

    def _on_canvas_drag_leave(self, widget, ctx, time):
        self._ph_grid_x = None
        self._ph_grid_y = None
        self._ph_valid  = False
        self._canvas_da.queue_draw()

    def _on_canvas_drag_received(self, widget, ctx, x, y, data_obj, info, time):
        payload = data_obj.get_text() or ""
        parts   = payload.split(":")
        if len(parts) != 2 or parts[0] != "applet":
            Gtk.drag_finish(ctx, False, False, time)
            return

        key = parts[1]
        if key not in DESKTOP_APPLET_SIZES:
            Gtk.drag_finish(ctx, False, False, time)
            return

        gx, gy = self._xy_to_grid(x, y)
        placed  = user_options.desktop_canvas.get_applets(self._monitor_id)

        if not _fits(gx, gy, key, self._cols, self._rows):
            Gtk.drag_finish(ctx, False, False, time)
            self.exit_canvas_mode(restore=False)
            return

        if _conflicts(gx, gy, key, placed, self._cols, self._rows, ignore_key=key):
            Gtk.drag_finish(ctx, False, False, time)
            self.exit_canvas_mode(restore=False)
            return

        DesktopAppletService.get_instance().remove(self._monitor_id, key)
        DesktopAppletService.get_instance().place(self._monitor_id, key, gx, gy)

        from utils.sounds import play_sound
        play_sound("widget-placed")

        self._drop_success = True
        Gtk.drag_finish(ctx, True, False, time)
        self.exit_canvas_mode()

        DesktopAppletService.get_instance().canvas_drop_complete(self._monitor_id)


    def _on_size_allocate(self, widget, alloc: Gdk.Rectangle) -> None:
        if not self._ready or self._in_size_allocate:
            return
        w, h = alloc.width, alloc.height
        if w < 1 or h < 1:
            return
        if w != self._old_w or h != self._old_h:
            self._old_w = w
            self._old_h = h
            if self._recalc_in_progress:
                self._pending_recalc = True
                return
            if self._fade_in_timer is not None:
                GLib.source_remove(self._fade_in_timer)
                self._fade_in_timer = None
            if self._recalc_timer is not None:
                GLib.source_remove(self._recalc_timer)
                self._recalc_timer = None
            if self._fade_out_animator.value != 0:
                self._fade_out()
            self._recalc_timer = GLib.timeout_add(300, self._deferred_recalc)

    def _deferred_recalc(self) -> bool:
        self._recalc_timer = None
        self._recalc_in_progress = True
        self._overlay.hide()
        GLib.timeout_add(50, self._do_window_resize)
        return False

    def _do_window_resize(self) -> bool:
        self._in_size_allocate = True
        self.hide()
        self.show()
        GLib.timeout_add(50, self._do_recalc)
        return False

    def _do_recalc(self) -> bool:
        self._in_size_allocate = False
        self.recalculate_grid()
        self._overlay.set_opacity(0.0)
        self._overlay.show()
        self._recalc_in_progress = False

        if self._pending_recalc:
            self._pending_recalc = False
            self._old_w = 0
            self._old_h = 0
            self._fade_out()
            self._recalc_timer = GLib.timeout_add(300, self._deferred_recalc)
        else:
            self._schedule_fade_in()

        return False

    def recalculate_grid(self) -> None:
        alloc = self.get_allocation()
        w, h = alloc.width, alloc.height
        if w < 1 or h < 1:
            return
        new_cols  = max(2, (w // CELL_STEP) & ~1)
        new_pad_x = (w - (new_cols * CELL_STEP - GAP)) // 2
        new_rows  = max(1, (h - new_pad_x - GAP) // CELL_STEP)
        new_pad_y = new_pad_x
        if new_cols != self._cols or new_rows != self._rows:
            self._cols  = new_cols
            self._rows  = new_rows
            self._pad_x = new_pad_x
            self._pad_y = new_pad_y
            user_options.desktop_canvas.resolve(self._monitor_id, self._cols, self._rows)
            user_options.save()
            self._reposition_all()
        else:
            self._pad_x = new_pad_x
            self._pad_y = new_pad_y
            self._reposition_all()

    def _reposition_all(self) -> None:
        entries = user_options.desktop_canvas.get_applets(self._monitor_id)
        for entry in entries:
            key    = entry["key"]
            grid_x = entry["grid_x"]
            grid_y = entry["grid_y"]
            widget = self._children.get(key)
            if widget is None:
                continue
            px, py = _grid_to_pixel(grid_x, grid_y)
            self._fixed.move(widget, self._pad_x + px, self._pad_y + py)
        self.schedule_retrace_blur()

    @property
    def cols(self) -> int:
        return self._cols

    @property
    def rows(self) -> int:
        return self._rows


    def rebuild(self) -> None:
        for widget in self._children.values():
            self._fixed.remove(widget)
            widget.destroy()
        self._children.clear()

        entries = user_options.desktop_canvas.get_applets(self._monitor_id)
        for entry in entries:
            key = entry["key"]
            cls = DESKTOP_APPLET_WIDGETS.get(key)
            if cls is None:
                logger.warning(f"[DesktopAppletService] unknown applet key {key!r}")
                continue
            try:
                widget = cls()
                w_px, h_px = _applet_pixel_size(key)
                widget.set_size_request(w_px, h_px)

                eb = Gtk.EventBox()
                eb.set_size_request(w_px, h_px)
                eb.add(widget)
                eb.connect("button-press-event", self._on_applet_right_click, key)
                eb.show_all()

                self._setup_applet_drag(eb, key)

                self._fixed.put(eb, 0, 0)
                self._children[key] = eb
            except Exception as e:
                logger.error(f"[DesktopAppletService] failed to build {key!r}: {e}")

        self._reposition_all()

    def add_applet(self, key: str, grid_x: int, grid_y: int) -> None:
        if key in self._children:
            return
        cls = DESKTOP_APPLET_WIDGETS.get(key)
        if cls is None:
            return
        try:
            widget = cls()
            w_px, h_px = _applet_pixel_size(key)
            widget.set_size_request(w_px, h_px)

            eb = Gtk.EventBox()
            eb.set_size_request(w_px, h_px)
            eb.add(widget)
            eb.connect("button-press-event", self._on_applet_right_click, key)
            eb.show_all()

            self._setup_applet_drag(eb, key)

            self._fixed.put(eb, 0, 0)
            self._children[key] = eb
            self._reposition_all()

            self.schedule_retrace_blur()

        except Exception as e:
            logger.error(f"[DesktopAppletService] failed to build {key!r}: {e}")

    def remove_applet(self, key: str) -> None:
        widget = self._children.pop(key, None)
        if widget:
            self._fixed.remove(widget)
            widget.destroy()
            self.schedule_retrace_blur()

    def _setup_applet_drag(self, eb: Gtk.EventBox, key: str) -> None:
        eb.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [_APPLET_TARGET],
            Gdk.DragAction.MOVE,
        )
        eb.connect("drag-begin",    self._on_applet_drag_begin,    key)
        eb.connect("drag-data-get", self._on_applet_drag_data_get, key)
        eb.connect("drag-end",      self._on_applet_drag_end,      key)
        eb.connect("drag-failed",   self._on_applet_drag_failed,   key)

    def _on_applet_drag_begin(self, eb, ctx, key: str) -> None:
        placed = user_options.desktop_canvas.get_applets(self._monitor_id)
        origin = next(
            ((e["grid_x"], e["grid_y"]) for e in placed if e["key"] == key),
            None,
        )
        eb.hide()
        self._drop_success = False
        # GLib.timeout_add(1000, self._retrace_blur)
        self.enter_canvas_mode(key, origin=origin)

    def _on_applet_drag_data_get(self, eb, ctx, data_obj, info, time, key: str) -> None:
        data_obj.set_text(f"applet:{key}", -1)

    def _on_applet_drag_end(self, eb, ctx, key: str) -> None:
        if self._drop_success:
            eb.hide()
        else:
            eb.show()
            if self._canvas_active and self._dragging_key == key:
                self.exit_canvas_mode(restore=False)
        self.schedule_retrace_blur()


    def _on_applet_drag_failed(self, eb, ctx, result, key: str) -> bool:
        eb.show()
        if self._canvas_active and self._dragging_key == key:
            self.exit_canvas_mode(restore=False)
            self.schedule_retrace_blur()
        return True

    def _on_applet_right_click(self, eb, event: Gdk.EventButton, key: str) -> bool:
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        remove_item = Gtk.MenuItem(label=f"Remove {key}")
        remove_item.connect(
            "activate",
            lambda _: DesktopAppletService.get_instance().remove(self._monitor_id, key),
        )
        menu.append(remove_item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True


    def _on_button_press(self, widget, event: Gdk.EventButton) -> bool:
        if event.button != 3:
            return False

        from services.singletons import bar_manager

        menu = Gtk.Menu()
        bar_count = sum(
            1 for bar in bar_manager._bars.values()
            if bar.monitor_id == self._monitor_id
        )

        if bar_count < 2:
            add_item = Gtk.MenuItem(label="Add Bar")
            add_item.connect(
                "activate",
                lambda _: bar_manager.add_bar_for_monitor(
                    Gdk.Display.get_default().get_monitor(self._monitor_id)
                ),
            )
            menu.append(add_item)
        else:
            item = Gtk.MenuItem(label="Maximum bars (2) reached on this monitor")
            item.set_sensitive(False)
            menu.append(item)

        if user_options.theme.blur:
            popup_with_blur(menu, event)
        else:
            menu.show_all()
            menu.popup_at_pointer(event)

        return True


    def _setup_drag_and_drop(self) -> None:
        self.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [_APPLET_TARGET],
            Gdk.DragAction.MOVE | Gdk.DragAction.COPY,
        )
        target_list = self.drag_dest_get_target_list()
        if target_list:
            target_list.add_text_targets(0)
            target_list.add_uri_targets(0)
        self.connect("drag-motion",        self._on_drag_motion)
        self.connect("drag-leave",         self._on_drag_leave)
        self.connect("drag-data-received", self._on_drag_data_received)

    def _on_drag_motion(self, widget, ctx, x, y, time) -> bool:
        targets = [t.name() for t in ctx.list_targets()]
        if "text/plain" in targets and self._canvas_active:
            return self._on_canvas_drag_motion(widget, ctx, x, y, time)
        Gdk.drag_status(ctx, Gdk.DragAction.COPY, time)
        return True

    def _on_drag_leave(self, widget, ctx, time) -> None:
        if self._canvas_active:
            self._on_canvas_drag_leave(widget, ctx, time)

    def _on_drag_data_received(self, widget, ctx, x, y, data, info, time) -> None:
        payload = (data.get_text() or "") if data else ""
        if payload.startswith("applet:"):
            parts = payload.split(":")
            if len(parts) == 2:
                self._on_canvas_drag_received(widget, ctx, x, y, data, info, time)
            else:
                Gtk.drag_finish(ctx, False, False, time)
            return

        if data and data.get_data():
            text = data.get_data().decode("utf-8", errors="ignore")
            for line in text.strip().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    text = line
                    break
            path = unquote(text.replace("file://", "").strip())
            if path.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")):
                alloc = self.get_allocation()
                nx = x / alloc.width  if alloc.width  > 0 else 0.5
                ny = 1.0 - (y / alloc.height if alloc.height > 0 else 0.5)
                nx = max(0.0, min(1.0, nx))
                ny = max(0.0, min(1.0, ny))
                logger.info(f"Drop on monitor {self._monitor_id}: {path!r} at ({nx:.3f}, {ny:.3f})")
                wp.set_wallpaper(path, pos=(nx, ny))
        ctx.finish(True, False, time)
        
    def destroy(self) -> None:
        # A pending retrace outlives the window otherwise, and traces children
        # that super().destroy() has already torn down.
        if self._retrace_source is not None:
            GLib.source_remove(self._retrace_source)
            self._retrace_source = None
        if self._style_handler is not None:
            self._style_service.disconnect(self._style_handler)
            self._style_handler = None
            self._style_service = None
        self._teardown_blur_ctx()
        super().destroy()

class DesktopAppletService(Service):
    _instance: "DesktopAppletService | None" = None

    @staticmethod
    def get_instance() -> "DesktopAppletService":
        if DesktopAppletService._instance is None:
            DesktopAppletService._instance = DesktopAppletService()
        return DesktopAppletService._instance

    @Signal
    def applets_changed(self, monitor_id: int) -> None: ...

    @Signal
    def canvas_drop_complete(self, monitor_id: int) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._windows: dict[int, DesktopAppletWindow] = {}

        display = Gdk.Display.get_default()
        if display:
            display.connect("monitor-added",   self._on_monitor_added)
            display.connect("monitor-removed", self._on_monitor_removed)

        self._sync_monitors()
        for win in self._windows.values():
            win.rebuild()
        plugins.connect("plugin-disabled", self._on_plugin_disabled)

        if user_options.theme.blur:
            GLib.timeout_add(2000, self._initial_blur)

    def _initial_blur(self) -> bool:
        self.apply_blur(True)
        return False

    def _sync_monitors(self) -> None:
        display  = Gdk.Display.get_default()
        current  = set(range(display.get_n_monitors()))
        existing = set(self._windows.keys())
        for mid in existing - current:
            self._remove_window(mid)
        for mid in current - existing:
            self._add_window(mid)

    def _add_window(self, monitor_id: int) -> None:
        if monitor_id in self._windows:
            return
        win = DesktopAppletWindow(monitor_id)
        self._windows[monitor_id] = win
        logger.info(f"[DesktopAppletService] window created for monitor {monitor_id}")

    def _remove_window(self, monitor_id: int) -> None:
        win = self._windows.pop(monitor_id, None)
        if win:
            win.destroy()
            logger.info(f"[DesktopAppletService] window removed for monitor {monitor_id}")

    def _on_monitor_added(self, _display, _monitor) -> None:
        logger.info("[DesktopAppletService] monitor added, resyncing...")
        self._sync_monitors()

    def _on_monitor_removed(self, _display, _monitor) -> None:
        logger.info("[DesktopAppletService] monitor removed, resyncing...")
        self._sync_monitors()

    def _on_plugin_disabled(self, _, name: str) -> None:
        display = Gdk.Display.get_default()
        for monitor_id in range(display.get_n_monitors()):
            if user_options.desktop_canvas.is_placed(monitor_id, name):
                self.remove(monitor_id, name)
            # Also clean up legacy desktop_applets
            if user_options.desktop_applets.is_placed(name):
                user_options.desktop_applets.remove(name)
        user_options.save()
        
    def apply_blur(self, enabled: bool) -> None:
        for win in self._windows.values():
            if enabled:
                win._apply_blur()
            else:
                win._teardown_blur_ctx()

    def place(self, monitor_id: int, key: str, grid_x: int, grid_y: int) -> bool:
        win  = self._windows.get(monitor_id)
        cols = win.cols if win and win.cols > 0 else 1
        rows = win.rows if win and win.rows > 0 else 1
        ry   = grid_y / rows

        placed = user_options.desktop_canvas.place(monitor_id, key, grid_x, grid_y, cols, ry)
        if not placed:
            return False
        user_options.save()
        if win:
            win.add_applet(key, grid_x, grid_y)
        self.applets_changed(monitor_id)
        return True

    def remove(self, monitor_id: int, key: str) -> bool:
        removed = user_options.desktop_canvas.remove(monitor_id, key)
        if not removed:
            return False
        user_options.save()
        win = self._windows.get(monitor_id)
        if win:
            win.remove_applet(key)
        self.applets_changed(monitor_id)
        return True

    def move(self, monitor_id: int, key: str, grid_x: int, grid_y: int) -> None:
        user_options.desktop_canvas.move(monitor_id, key, grid_x, grid_y)
        user_options.save()
        win = self._windows.get(monitor_id)
        if win:
            win.remove_applet(key)
            win.add_applet(key, grid_x, grid_y)
        self.applets_changed(monitor_id)

    def enter_canvas_mode(self, monitor_id: int, key: str) -> None:
        """Called from the dash to begin a new placement drag."""
        win = self._windows.get(monitor_id)
        if win:
            win.enter_canvas_mode(key, origin=None)

    def exit_canvas_mode(self, monitor_id: int, restore: bool = False) -> None:
        """Called from the dash to cancel canvas mode."""
        win = self._windows.get(monitor_id)
        if win:
            win.exit_canvas_mode(restore=restore)

    def get_window(self, monitor_id: int) -> "DesktopAppletWindow | None":
        return self._windows.get(monitor_id)