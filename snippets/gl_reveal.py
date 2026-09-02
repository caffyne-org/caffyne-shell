import cairo
import moderngl
from typing import Callable

from gi.repository import Gtk, GLib
from loguru import logger

from fabric.widgets.box import Box

from .gl_pipeline import GLPipeline, PipelineTextureStream, create_gl_context
from .reveal_shaders import VERT_SRC
from .blur.framebuffer_trace import FramebufferRegionTracer
from .blur.region_trace import Rect, trace_widget


class ShaderReveal(Box):
    TRANSITION: str = ""
    DEFAULT_FRAG: str = ""
    RESTORE_CHILD_ON_CLOSE: bool = True
    MAX_SNAPSHOT_RETRIES: int = 30

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

        self.open_bezier    = open_bezier
        self.close_bezier   = close_bezier
        self.open_duration  = open_duration
        self.close_duration = close_duration

        self._child: Gtk.Widget | None = child
        self._on_close_callbacks: list[Callable] = []

        self.progress_cb: Callable[[float], None] | None = None
        self.region_cb: Callable[[list[Rect]], None] | None = None
        self.region_inset: int = 0
        self.region_settle_step: int = 1

        # Animation state
        self._opening: bool = False
        self._animating: bool = False
        self._anim_start: float | None = None
        self._duration: float = open_duration
        self._tick_id: int = 0
        self._retry_id: int = 0
        self._retries: int = 0
        self._settle_id: int = 0

        self._stream = PipelineTextureStream()

        # GL state
        self._ctx: moderngl.Context | None = None
        self._pipeline: GLPipeline | None = None
        self._tracer: FramebufferRegionTracer | None = None
        self._probe_sampler: moderngl.Sampler | None = None
        self._frag_src: str = self.DEFAULT_FRAG

        self._gl_area = Gtk.GLArea()
        self._gl_area.set_has_alpha(True)
        self._gl_area.set_app_paintable(True)
        self._gl_area.set_hexpand(True)
        self._gl_area.set_vexpand(True)
        self._gl_area.connect("realize",   self._on_gl_realize)
        self._gl_area.connect("unrealize", self._on_gl_unrealize)
        self._gl_area.connect("render",    self._on_gl_render)

        self._overlay = Gtk.Overlay()
        if child:
            self._overlay.add(child)
        self._overlay.add_overlay(self._gl_area)
        self._overlay.set_hexpand(True)
        self._overlay.set_vexpand(True)

        self.add(self._overlay)
        self.set_app_paintable(True)
        self._overlay.show()
        if child:
            child.show()
        self._gl_area.hide()

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
        self.recompile(self._anim_service.get_frag_src(self.TRANSITION) or self.DEFAULT_FRAG)

    def recompile(self, frag_src: str) -> bool:
        self._frag_src = frag_src
        if self._pipeline is None:
            return False

        self._gl_area.make_current()
        if self._gl_area.get_error():
            return False
        return self._pipeline.recompile(frag_src)
    
    @property
    def animating(self) -> bool:
        return self._animating

    @property
    def child(self) -> Gtk.Widget | None:
        return self._child

    def open(self):
        if self._animating and self._opening:
            return
        self._begin(opening=True)

    def close(self, on_done: Callable | None = None):
        if on_done is not None:
            self._on_close_callbacks.append(on_done)
        if self._animating and not self._opening:
            return
        self._begin(opening=False)

    def _begin(self, opening: bool):
        self._stop_tick()
        self._cancel_retry()
        self._cancel_settle()

        self._opening    = opening
        self._duration   = self.open_duration if opening else self.close_duration
        self._animating  = True
        self._anim_start = None
        self._retries    = 0
        if self._tracer:
            self._tracer.reset()

        self._set_child_visible(False)

        if opening or not self._snapshot_and_start():
            self._retry_id = GLib.idle_add(
                self._deferred_start, priority=GLib.PRIORITY_LOW
            )

    def _deferred_start(self) -> bool:
        if not self._animating:
            self._retry_id = 0
            return GLib.SOURCE_REMOVE

        if self._snapshot_and_start():
            self._retry_id = 0
            return GLib.SOURCE_REMOVE

        self._retries += 1
        if self._retries > self.MAX_SNAPSHOT_RETRIES:
            self._retry_id = 0
            logger.warning(
                f"[{type(self).__name__}] no allocation to animate; finishing without one"
            )
            self._finish()
            return GLib.SOURCE_REMOVE

        return GLib.SOURCE_CONTINUE

    def _snapshot_and_start(self) -> bool:
        if not self._update_cache():
            return False
        self._gl_area.show()
        self._gl_area.make_current()
        if self._gl_area.get_error() or self._pipeline is None:
            self._finish()
            return True
        self._upload_texture()
        self._start_tick()
        return True

    def _start_tick(self):
        if not self._tick_id:
            self._tick_id = self._gl_area.add_tick_callback(self._on_tick)

    def _stop_tick(self):
        if self._tick_id:
            self._gl_area.remove_tick_callback(self._tick_id)
            self._tick_id = 0

    def _cancel_retry(self):
        if self._retry_id:
            GLib.source_remove(self._retry_id)
            self._retry_id = 0

    def _on_tick(self, widget, frame_clock) -> bool:
        now = frame_clock.get_frame_time() / 1_000_000

        if self._anim_start is None:
            self._anim_start = now
            self._gl_area.queue_render()
            return GLib.SOURCE_CONTINUE

        self._gl_area.queue_render()

        if (now - self._anim_start) >= self._duration:
            self._tick_id = 0
            self._finish()
            return GLib.SOURCE_REMOVE

        return GLib.SOURCE_CONTINUE

    def _finish(self):
        self._stop_tick()
        self._cancel_retry()
        self._animating = False
        self._anim_start = None
        self._gl_area.hide()
        self._stream.drop_surface()

        if self._opening:
            self._set_child_visible(True)
            if self.progress_cb:
                self.progress_cb(1.0)
            self._queue_settle()
            return

        if self.RESTORE_CHILD_ON_CLOSE:
            self._set_child_visible(True)
        if self.progress_cb:
            self.progress_cb(0.0)
        if self.region_cb:
            self.region_cb([])
        callbacks, self._on_close_callbacks = self._on_close_callbacks, []
        for cb in callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"[{type(self).__name__}] close callback failed: {e}")

    def _set_child_visible(self, visible: bool):
        if self._child is not None:
            self._child.set_opacity(1.0 if visible else 0.0)

    def _update_cache(self) -> bool:
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        if w <= 1 or h <= 1 or self._child is None:
            return False

        scale = self._gl_area.get_scale_factor()
        surface = self._stream.surface(w * scale, h * scale)
        cr = cairo.Context(surface)
        cr.set_operator(cairo.OPERATOR_OVER)
        if scale != 1:
            cr.scale(scale, scale)

        if self._child.get_allocated_width() <= 1:
            allocation = Gtk.Allocation()
            allocation.x = allocation.y = 0
            allocation.width = w
            allocation.height = h
            self._child.size_allocate(allocation)

        was_visible = self._child.get_visible()
        self._child.show()
        self._child.set_opacity(1.0)
        self._child.draw(cr)
        self._child.set_opacity(0.0)
        if not was_visible:
            self._child.hide()

        return True

    def _upload_texture(self):
        self._stream.upload(self._ctx, mipmaps=self.region_cb is not None)

    def _on_gl_realize(self, *_):
        self._gl_area.make_current()
        if self._gl_area.get_error():
            return

        try:
            self._ctx = create_gl_context(self._gl_area)
            self._pipeline = GLPipeline(
                fragment_buffer=self._frag_src,
                ctx=self._ctx,
                vertex_buffer=VERT_SRC,
                wrap=False,
                blend_func=GLPipeline.BLEND_PREMULTIPLIED,
            )
            self._probe_sampler = self._ctx.sampler(
                filter=(moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR),
                repeat_x=False,
                repeat_y=False,
            )
        except Exception as e:
            logger.error(f"[{type(self).__name__}] GL init failed: {e}")
            self._ctx = None
            self._pipeline = None

    def _on_gl_unrealize(self, *_):
        self._stop_tick()
        self._gl_area.make_current()

        for obj in (self._tracer, self._pipeline, self._probe_sampler):
            if obj is not None:
                obj.release()
        self._stream.release()

        self._tracer = None
        self._pipeline = None
        self._probe_sampler = None
        self._ctx = None

    def _on_destroy(self, *_):
        self._cancel_retry()
        self._cancel_settle()
        if self._anim_handler:
            self._anim_service.disconnect(self._anim_handler)
            self._anim_handler = 0

    def _extra_uniforms(self) -> dict:
        return {}

    def _draw_scene(
        self,
        t: float,
        width: int,
        height: int,
        framebuffer: moderngl.Framebuffer | None = None,
    ):
        bx1, by1, bx2, by2 = self.open_bezier if self._opening else self.close_bezier
        pipeline = self._pipeline

        pipeline.set_uniform("u_time", t)
        pipeline.set_uniform("u_opening", 1 if self._opening else 0)
        pipeline.set_uniform("u_bx1", bx1)
        pipeline.set_uniform("u_by1", by1)
        pipeline.set_uniform("u_bx2", bx2)
        pipeline.set_uniform("u_by2", by2)
        for name, value in self._extra_uniforms().items():
            pipeline.set_uniform(name, value)

        self._stream.use(0)
        pipeline.set_uniform("u_texture", 0)
        pipeline.render(width, height, framebuffer=framebuffer)

    def _probe_regions(
        self, t: float, width: int, height: int, screen: moderngl.Framebuffer
    ) -> list[Rect] | None:
        if self._tracer is None:
            self._tracer = FramebufferRegionTracer(self._ctx)

        def draw(framebuffer, probe_w: int, probe_h: int):
            if self._probe_sampler:
                self._probe_sampler.use(0)
            self._draw_scene(t, probe_w, probe_h, framebuffer=framebuffer)
            if self._probe_sampler:
                self._probe_sampler.clear(0)

        scale = self._gl_area.get_scale_factor()
        return self._tracer.capture(
            draw,
            screen,
            width * scale, height * scale,
            width, height,
            inset=self.region_inset,
        )

    def _on_gl_render(self, area, ctx) -> bool:
        if self._pipeline is None or self._anim_start is None:
            return False
        self._upload_texture()
        if not self._stream.has_texture:
            return False

        elapsed = (
            area.get_frame_clock().get_frame_time() / 1_000_000
        ) - self._anim_start
        t = min(elapsed / self._duration, 1.0)

        if self.progress_cb:
            self.progress_cb(t if self._opening else 1.0 - t)

        width  = area.get_allocated_width()
        height = area.get_allocated_height()
        scale  = area.get_scale_factor()
        screen = self._ctx.detect_framebuffer()

        self._draw_scene(t, width * scale, height * scale, framebuffer=screen)

        if self.region_cb:
            rects = self._probe_regions(t, width, height, screen)
            if rects is not None:
                self.region_cb(rects)
        return True


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
        if self.region_cb is not None and not self._animating:
            self.region_cb(self.settled_regions())
        return GLib.SOURCE_REMOVE

    def settled_regions(self) -> list[Rect]:
        """Regions the child covers once GTK, not the shader, is drawing it."""
        if not self._child:
            return []
        rects = trace_widget(
            self._child, inset=self.region_inset, step=self.region_settle_step
        )
        offset = self._child.translate_coordinates(self, 0, 0)
        if not offset:
            return rects
        dx, dy = offset
        for rect in rects:
            rect.x += dx
            rect.y += dy
        return rects
