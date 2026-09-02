import cairo
import moderngl
from gi.repository import Gtk, Gdk, GLib
from loguru import logger

from fabric.widgets.stack import Stack

from .gl_pipeline import GLPipeline, PipelineTextureStream, create_gl_context
from .reveal_shaders import VERT_SRC

STACK_FRAG_SRC = """#version 320 es
precision highp float;
in vec2 uv;
out vec4 fragColor;

uniform sampler2D u_tex_from;
uniform sampler2D u_tex_to;
uniform float     u_time;
uniform float     u_bx1, u_by1, u_bx2, u_by2;

float bezier_x(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0*mt*mt*t*bx1 + 3.0*mt*t*t*bx2 + t*t*t;
}
float bezier_y(float t, float by1, float by2) {
    float mt = 1.0 - t;
    return 3.0*mt*mt*t*by1 + 3.0*mt*t*t*by2 + t*t*t;
}
float bezier_dx(float t, float bx1, float bx2) {
    float mt = 1.0 - t;
    return 3.0*(mt*mt*bx1 + 2.0*mt*t*(bx2-bx1) + t*t*(1.0-bx2));
}
float cubic_bezier(float x, float bx1, float by1, float bx2, float by2) {
    if (x <= 0.0) return 0.0;
    if (x >= 1.0) return 1.0;
    float t = x;
    for (int i = 0; i < 8; i++) {
        float fx  = bezier_x(t, bx1, bx2) - x;
        float dfx = bezier_dx(t, bx1, bx2);
        if (abs(dfx) < 1e-6) break;
        t -= fx / dfx;
        t  = clamp(t, 0.0, 1.0);
    }
    return bezier_y(t, by1, by2);
}

// simple hash for per-tile randomness
float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}
void main() {
    vec2 tex_uv = vec2(uv.x, 1.0 - uv.y);
    float t = cubic_bezier(clamp(u_time, 0.0, 1.0), u_bx1, u_by1, u_bx2, u_by2);

    float tiles   = 12.0;
    vec2  tile    = floor(tex_uv * tiles);
    vec2  tile_uv = fract(tex_uv * tiles);

    float delay   = hash(tile) * 0.4;
    float local_t = clamp((t - delay) / (1.0 - delay), 0.0, 1.0);

    float angle = local_t * 3.14159 * 0.5 * (hash(tile + 0.5) > 0.5 ? 1.0 : -1.0);
    float scale = 1.0 - local_t;

    vec2 center  = vec2(0.5);
    vec2 rotated = tile_uv - center;
    float s = sin(angle), c = cos(angle);
    rotated = vec2(rotated.x * c - rotated.y * s,
                   rotated.x * s + rotated.y * c);
    rotated = rotated / max(scale, 0.001) + center;

    vec4 from_col = vec4(0.0);
    if (scale > 0.01 && rotated.x >= 0.0 && rotated.x <= 1.0 &&
                        rotated.y >= 0.0 && rotated.y <= 1.0) {
        from_col = texture(u_tex_from, (tile + rotated) / tiles) * (1.0 - local_t);
    }

    float delay_to   = (1.0 - hash(tile + 99.0)) * 0.4;
    float local_t_to = clamp((t - delay_to) / (1.0 - delay_to), 0.0, 1.0);

    float angle_to = (1.0 - local_t_to) * 3.14159 * 0.5 * (hash(tile + 7.3) > 0.5 ? 1.0 : -1.0);
    float scale_to = local_t_to;

    vec2 rotated_to = tile_uv - center;
    float s2 = sin(angle_to), c2 = cos(angle_to);
    rotated_to = vec2(rotated_to.x * c2 - rotated_to.y * s2,
                      rotated_to.x * s2 + rotated_to.y * c2);
    rotated_to = rotated_to / max(scale_to, 0.001) + center;

    vec4 to_col = vec4(0.0);
    if (scale_to > 0.01 && rotated_to.x >= 0.0 && rotated_to.x <= 1.0 &&
                           rotated_to.y >= 0.0 && rotated_to.y <= 1.0) {
        to_col = texture(u_tex_to, (tile + rotated_to) / tiles) * local_t_to;
    }

    fragColor = from_col + to_col;
}
"""


class ShaderStack(Stack):
    SHADER_PAGE = "__shader_transition__"

    def __init__(
        self,
        bezier: tuple[float, float, float, float] = (0.4, 0.0, 0.2, 1.0),
        duration: float = 0.25,
        frag_src: str | None = None,
        **kwargs,
    ):
        self._bezier = bezier
        self._duration = duration
        self._frag_src = frag_src or STACK_FRAG_SRC

        self._anim_start: float | None = None
        self._animating: bool = False
        self._tick_id: int = 0
        self._target: Gtk.Widget | None = None
        self._direction: float = 1.0
        self._hold_surface: cairo.ImageSurface | None = None
        self._switching: bool = False
        self._pending_target: Gtk.Widget | None = None

        self._from = PipelineTextureStream()
        self._to = PipelineTextureStream()

        self._ctx: moderngl.Context | None = None
        self._pipeline: GLPipeline | None = None

        self._gl_area = Gtk.GLArea()
        self._gl_area.set_has_alpha(True)
        self._gl_area.set_app_paintable(True)
        self._gl_area.set_hexpand(True)
        self._gl_area.set_vexpand(True)
        self._gl_area.connect("realize", self._on_gl_realize)
        self._gl_area.connect("unrealize", self._on_gl_unrealize)
        self._gl_area.connect("render", self._on_gl_render)
        self._gl_area.show()

        # GTK's own transitions would run underneath the shader.
        kwargs.pop("transition_type", None)
        kwargs.pop("transition_duration", None)
        super().__init__(transition_type="none", transition_duration=0, **kwargs)

        self.set_app_paintable(True)
        Gtk.Stack.add_named(self, self._gl_area, self.SHADER_PAGE)
        self._claim_visible()

        self.connect("realize", lambda *_: self._gl_area.realize())

        from services.animation import animation_service

        self._anim_service = animation_service
        animation_service.connect("transition-changed", self._on_transition_changed)
        self._on_transition_changed(None, "stack_transition")

    def _on_transition_changed(self, _, transition: str):
        if transition != "stack_transition":
            return
        s = self._anim_service.get_transition_settings("stack_transition")
        self._bezier = tuple(s["bezier"])
        self._duration = s["duration"]
        frag = self._anim_service.get_frag_src("stack_transition")
        self.recompile(frag or STACK_FRAG_SRC)

    def recompile(self, frag_src: str) -> bool:
        """Hot-swap the fragment shader. Safe to call before realize."""
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

    def add(self, widget: Gtk.Widget):
        Gtk.Stack.add(self, widget)
        self._claim_visible()

    def add_named(self, widget: Gtk.Widget, name: str):
        Gtk.Stack.add_named(self, widget, name)
        self._claim_visible()

    def add_titled(self, widget: Gtk.Widget, name: str, title: str):
        Gtk.Stack.add_titled(self, widget, name, title)
        self._claim_visible()

    def remove(self, widget: Gtk.Widget):
        if widget is self._target or widget is Gtk.Stack.get_visible_child(self):
            self._end_anim(apply_target=False)
            self._target = None
        Gtk.Stack.remove(self, widget)
        self._claim_visible()

    def get_children(self) -> list[Gtk.Widget]:
        return [c for c in Gtk.Stack.get_children(self) if c is not self._gl_area]

    def get_visible_child(self) -> Gtk.Widget | None:
        child = self._target if self._animating else Gtk.Stack.get_visible_child(self)
        return None if child is self._gl_area else child

    def get_visible_child_name(self) -> str | None:
        if not self._animating:
            name = Gtk.Stack.get_visible_child_name(self)
            return None if name == self.SHADER_PAGE else name
        if self._target is None:
            return None
        return self.child_get_property(self._target, "name")

    def set_visible_child(self, widget: Gtk.Widget):
        self._transition_to(widget)

    def set_visible_child_name(self, name: str):
        self._transition_to(self.get_child_by_name(name))

    def set_visible_child_full(self, name: str, transition=None):
        self._transition_to(self.get_child_by_name(name))

    def _claim_visible(self):
        """Keep the shader page from ever being the resting visible child."""
        if self._animating:
            return
        if Gtk.Stack.get_visible_child(self) is not self._gl_area:
            return
        for child in self.get_children():
            Gtk.Stack.set_visible_child(self, child)
            self._target = child
            return

    def do_draw(self, cr) -> bool:
        if self._hold_surface is None:
            return Gtk.Stack.do_draw(self, cr)

        scale = self.get_scale_factor()
        cr.save()
        if scale != 1:
            cr.scale(1.0 / scale, 1.0 / scale)
        cr.set_source_surface(self._hold_surface, 0, 0)
        cr.paint()
        cr.restore()
        return True

    def _transition_to(self, target: Gtk.Widget | None):
        if target is None or target is self._gl_area:
            return

        if self._switching:
            self._pending_target = target
            return

        while target is not None:
            self._switching = True
            try:
                self._switch(target)
            finally:
                self._switching = False
            target, self._pending_target = self._pending_target, None
            if target is self._target:
                break

    def _switch(self, target: Gtk.Widget):
        if target is self._target and (self._animating or not self._needs_switch(target)):
            return

        w = self.get_allocated_width()
        h = self.get_allocated_height()
        scale = self.get_scale_factor()

        if not self._can_animate(w, h):
            self._end_anim(apply_target=False)
            self._apply(target)
            return

        origin = self._target if self._animating else Gtk.Stack.get_visible_child(self)
        self._direction = self._direction_between(origin, target)

        if self._animating:
            self._end_anim(apply_target=False)
            self._from, self._to = self._to, self._from
            have_from = self._from.has_texture
        else:
            current = Gtk.Stack.get_visible_child(self)
            have_from = current is not None and self._snapshot(
                current, self._from, w, h, scale
            )
            if have_from:
                self._hold_surface = self._from.surface_ref

        have_to = have_from and self._snapshot_page(target, w, h, scale)
        if not have_to:
            self._apply(target)
            return

        self._target = target
        self._begin_anim(w, h)
        self._hold_surface = None

    def _direction_between(self, origin: Gtk.Widget | None, target: Gtk.Widget) -> float:
        children = self.get_children()
        if origin not in children or target not in children:
            return self._direction
        return 1.0 if children.index(target) > children.index(origin) else -1.0

    def _needs_switch(self, target: Gtk.Widget) -> bool:
        return Gtk.Stack.get_visible_child(self) is not target

    def _can_animate(self, w: int, h: int) -> bool:
        return (
            self.get_mapped()
            and w > 1
            and h > 1
            and Gtk.Stack.get_visible_child(self) is not None
        )

    def _apply(self, target: Gtk.Widget):
        self._hold_surface = None
        self._target = target
        Gtk.Stack.set_visible_child(self, target)

    def _snapshot_page(
        self, target: Gtk.Widget, w: int, h: int, scale: int
    ) -> bool:
        old_opacity = target.get_opacity()
        target.set_opacity(0.0)
        try:
            target.show()
            Gtk.Stack.set_visible_child(self, target)

            alloc = Gdk.Rectangle()
            alloc.x = alloc.y = 0
            alloc.width = w
            alloc.height = h

            settled = (
                target.get_allocated_width() == w
                and target.get_allocated_height() == h
            )
            target.size_allocate(alloc)
            if not settled:
                target.queue_resize()
                while Gtk.events_pending():
                    Gtk.main_iteration_do(False)
                target.size_allocate(alloc)

            return self._snapshot(target, self._to, w, h, scale)
        finally:
            target.set_opacity(old_opacity)

    def _snapshot(
        self,
        widget: Gtk.Widget,
        stream: PipelineTextureStream,
        w: int,
        h: int,
        scale: int,
    ) -> bool:
        if w <= 1 or h <= 1 or not widget.get_mapped():
            return False

        surf = stream.surface(w * scale, h * scale)
        cr = cairo.Context(surf)
        cr.set_operator(cairo.OPERATOR_OVER)
        if scale != 1:
            cr.scale(scale, scale)

        old_opacity = widget.get_opacity()
        widget.set_opacity(1.0)

        if widget.get_allocated_width() <= 1:
            alloc = Gdk.Rectangle()
            alloc.x = alloc.y = 0
            alloc.width = w
            alloc.height = h
            widget.size_allocate(alloc)

        widget.draw(cr)
        widget.set_opacity(old_opacity)
        return True

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
        except Exception as e:
            logger.error(f"[ShaderStack] GL init failed: {e}")
            self._ctx = None
            self._pipeline = None

    def _on_gl_unrealize(self, *_):
        self._stop_tick()
        self._gl_area.make_current()
        self._from.release()
        self._to.release()
        if self._pipeline is not None:
            self._pipeline.release()
            self._pipeline = None
        self._ctx = None

    def _begin_anim(self, w: int, h: int):
        self._gl_area.set_size_request(w, h)
        Gtk.Stack.set_visible_child(self, self._gl_area)

        if self._pipeline is None or self._ctx is None:
            self._end_anim()
            return

        self._gl_area.make_current()
        if self._gl_area.get_error():
            self._end_anim()
            return

        uploaded = self._from.upload(self._ctx) and self._to.upload(self._ctx)
        if not uploaded:
            self._end_anim()
            return

        self._anim_start = None
        self._animating = True
        self._start_tick()
        self._gl_area.queue_render()

    def _end_anim(self, apply_target: bool = True):
        self._stop_tick()
        self._animating = False
        self._anim_start = None
        self._from.drop_surface()
        self._to.drop_surface()
        self._gl_area.set_size_request(-1, -1)
        if apply_target and self._target is not None:
            Gtk.Stack.set_visible_child(self, self._target)

    def _start_tick(self):
        if not self._tick_id:
            self._tick_id = self._gl_area.add_tick_callback(self._on_tick)

    def _stop_tick(self):
        if self._tick_id:
            self._gl_area.remove_tick_callback(self._tick_id)
            self._tick_id = 0

    def _on_tick(self, widget, frame_clock) -> bool:
        now = frame_clock.get_frame_time() / 1_000_000

        if self._anim_start is None:
            self._anim_start = now
            self._gl_area.queue_render()
            return GLib.SOURCE_CONTINUE

        self._gl_area.queue_render()

        if (now - self._anim_start) >= self._duration:
            self._tick_id = 0
            self._end_anim()
            return GLib.SOURCE_REMOVE

        return GLib.SOURCE_CONTINUE
    
    def _on_gl_render(self, area, ctx) -> bool:
        if self._pipeline is None or not self._animating:
            return False
        if not (self._from.has_texture and self._to.has_texture):
            return False

        if self._anim_start is None:
            t = 0.0
        else:
            elapsed = (
                area.get_frame_clock().get_frame_time() / 1_000_000
            ) - self._anim_start
            t = min(elapsed / self._duration, 1.0)

        bx1, by1, bx2, by2 = self._bezier
        self._pipeline.set_uniform("u_time", t)
        self._pipeline.set_uniform("u_bx1", bx1)
        self._pipeline.set_uniform("u_by1", by1)
        self._pipeline.set_uniform("u_bx2", bx2)
        self._pipeline.set_uniform("u_by2", by2)
        self._pipeline.set_uniform("u_direction", self._direction)

        self._from.use(0)
        self._to.use(1)
        self._pipeline.set_uniform("u_tex_from", 0)
        self._pipeline.set_uniform("u_tex_to", 1)

        scale = area.get_scale_factor()
        self._pipeline.render(
            area.get_allocated_width() * scale,
            area.get_allocated_height() * scale,
        )
        return True
