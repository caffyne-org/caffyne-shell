import cairo
from typing import Callable

from gi.repository import Gtk, GLib
from loguru import logger

from fabric.widgets.box import Box

from .animator import Animator
from .blur.region_trace import Rect, regions_from_alpha, trace_widget


def _surface_alpha(surface: cairo.ImageSurface, step: int = 1) -> tuple[bytes, int, int]:
    surface.flush()
    width  = surface.get_width()
    height = surface.get_height()
    if width <= 0 or height <= 0:
        return b"", 0, 0

    step   = max(1, step)
    stride = surface.get_stride()
    raw    = bytes(surface.get_data())

    out_width  = -(-width // step)
    out_height = -(-height // step)
    row = step * stride
    plane = b"".join(
        raw[y * row + 3 : y * row + 3 + width * 4 : 4 * step]
        for y in range(out_height)
    )
    return plane, out_width, out_height


class CairoReveal(Box):
    TRANSITION: str = ""
    SCALE_START: float = 0.6

    def __init__(
        self,
        child: Gtk.Widget | None = None,
        open_bezier: tuple[float, float, float, float] = (0.16, 1.0, 0.3, 1.0),
        close_bezier: tuple[float, float, float, float] = (0.16, 1.0, 0.3, 1.0),
        open_duration: float = 0.3,
        close_duration: float = 0.3,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.show_all()

        self.open_bezier    = open_bezier
        self.close_bezier   = close_bezier
        self.open_duration  = open_duration
        self.close_duration = close_duration

        self._child: Gtk.Widget | None = child
        self._progress = 0.0
        self._target   = 0.0
        self._on_close_callbacks: list[Callable] = []

        self._cached_surface: cairo.ImageSurface | None = None
        self._base_regions: list[Rect] | None = None
        self._settle_id: int = 0
        self.active_animator: Animator | None = None

        self.progress_cb: Callable[[float], None] | None = None
        self.region_cb: Callable[[list[Rect]], None] | None = None
        self.region_inset: int = 0
        self.region_settle_step: int = 1

        if child:
            self.add(child)

        self.set_app_paintable(True)

        from services.animation import animation_service

        self._anim_service = animation_service
        self._anim_handler = animation_service.connect(
            "transition-changed", self._on_transition_changed
        )
        self._on_transition_changed(None, self.TRANSITION)
        self.connect("destroy", self._on_destroy)

    def _on_transition_changed(self, _, transition: str):
        if transition != self.TRANSITION:
            return
        s = self._anim_service.get_transition_settings(self.TRANSITION)
        self.open_bezier    = tuple(s.get("open_bezier", self.open_bezier))
        self.close_bezier   = tuple(s.get("close_bezier", self.close_bezier))
        self.open_duration  = s.get("open_duration", self.open_duration)
        self.close_duration = s.get("close_duration", self.close_duration)

    def _on_destroy(self, *_):
        self._cancel_settle()
        if self._anim_handler:
            self._anim_service.disconnect(self._anim_handler)
            self._anim_handler = 0

    @property
    def child(self) -> Gtk.Widget | None:
        return self._child

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def animating(self) -> bool:
        return self.active_animator is not None

    def _anchor(self, width: int, height: int) -> tuple[float, float]:
        return width / 2.0, height / 2.0

    def _update_cache(self):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        if w <= 1 or h <= 1:
            return

        self._cached_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        cr = cairo.Context(self._cached_surface)
        Gtk.Box.do_draw(self, cr)
        self._base_regions = None

    def _clear_cache(self):
        self._cached_surface = None
        self._base_regions = None

    def open(self):
        self._start(opening=True)

    def close(self, on_done: Callable | None = None):
        if on_done:
            def _once(*_):
                on_done()
                try:
                    self._on_close_callbacks.remove(_once)
                except ValueError:
                    pass
            self._on_close_callbacks.append(_once)

        self._start(opening=False)

    def _start(self, opening: bool):
        self._target = 1.0 if opening else 0.0
        self._cancel_settle()

        if self.active_animator:
            self.active_animator.pause()
            self.active_animator = None

        self._update_cache()

        start_value = self._progress
        end_value   = self._target
        distance    = abs(end_value - start_value)

        if distance < 0.001:
            self._set_progress(end_value)
            self._clear_cache()
            if opening:
                self._on_open_finished()
            else:
                self._on_close_finished()
            return

        bezier   = self.open_bezier if opening else self.close_bezier
        duration = self.open_duration if opening else self.close_duration

        self.active_animator = (
            Animator(
                bezier_curve=bezier,
                duration=max(0.01, duration * distance),
                min_value=start_value,
                max_value=end_value,
                tick_widget=self,
            )
            .build()
            .unwrap()
        )

        self.active_animator.connect(
            "notify::value", lambda a, _: self._set_progress(a.value)
        )
        self.active_animator.connect(
            "finished",
            self._on_open_finished if opening else self._on_close_finished,
        )
        self.active_animator.play()

    def _set_progress(self, value: float):
        self._progress = max(0.0, min(value, 1.0))
        if self.progress_cb:
            self.progress_cb(self._progress)
        if self.region_cb:
            self.region_cb(self._regions(self._progress))
        self.queue_draw()

    def _on_open_finished(self, *_):
        self.active_animator = None
        self._set_progress(1.0)
        self._clear_cache()
        self._queue_settle()

    def _on_close_finished(self, *_):
        self.active_animator = None
        self._set_progress(0.0)
        self._clear_cache()
        if self.region_cb:
            self.region_cb([])
        if self._target != 0.0:
            return
        callbacks, self._on_close_callbacks = self._on_close_callbacks, []
        for cb in callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"[{type(self).__name__}] close callback failed: {e}")

    def _regions(self, progress: float) -> list[Rect]:
        if progress <= 0.0:
            return []

        base = self._base_regions
        if base is None:
            base = self._base_regions = self._trace_cache()
        if not base:
            return []

        w = self.get_allocated_width()
        h = self.get_allocated_height()
        scale = self.SCALE_START + (1.0 - self.SCALE_START) * progress
        anchor_x, anchor_y = self._anchor(w, h)

        return [
            Rect(
                round(anchor_x + (rect.x - anchor_x) * scale),
                round(anchor_y + (rect.y - anchor_y) * scale),
                round(rect.width * scale),
                round(rect.height * scale),
            )
            for rect in base
        ]

    def _trace_cache(self) -> list[Rect]:
        if self._cached_surface is None:
            return []
        alpha, w, h = _surface_alpha(
            self._cached_surface, step=self.region_settle_step
        )
        return regions_from_alpha(
            alpha, w, h,
            min_alpha=8,
            relative_alpha=0.5,
            out_width=self._cached_surface.get_width(),
            out_height=self._cached_surface.get_height(),
            inset=self.region_inset,
        )

    def _queue_settle(self):
        self._cancel_settle()
        if self.region_cb is None:
            return
        self._settle_id = GLib.idle_add(
            self._emit_settled, priority=GLib.PRIORITY_LOW
        )

    def _cancel_settle(self):
        if self._settle_id:
            GLib.source_remove(self._settle_id)
            self._settle_id = 0

    def _emit_settled(self) -> bool:
        self._settle_id = 0
        if self.region_cb is not None and not self.animating:
            self.region_cb(self.settled_regions())
        return GLib.SOURCE_REMOVE

    def settled_regions(self) -> list[Rect]:
        """Regions this reveal covers once it draws its child untransformed."""
        if self._progress < 1.0:
            return []
        return trace_widget(
            self, inset=self.region_inset, step=self.region_settle_step
        )

    def do_draw(self, cr: cairo.Context) -> bool:
        p = self._progress
        if p <= 0.0:
            return True

        if p >= 1.0 and self._cached_surface is None:
            return Gtk.Box.do_draw(self, cr)

        w = self.get_allocated_width()
        h = self.get_allocated_height()

        scale = self.SCALE_START + (1.0 - self.SCALE_START) * p
        anchor_x, anchor_y = self._anchor(w, h)

        cr.save()
        cr.translate(anchor_x, anchor_y)
        cr.scale(scale, scale)
        cr.translate(-anchor_x, -anchor_y)

        if self._cached_surface:
            cr.set_source_surface(self._cached_surface, 0, 0)
            cr.paint_with_alpha(p)
        else:
            Gtk.Box.do_draw(self, cr)

        cr.restore()
        return True
