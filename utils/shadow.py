import cairo
import math
from snippets.blur.region_trace import trace_widget
from gi.repository import GLib

_RETRACE_DELAY_MS = 120

_BLOOM_PASSES = [
    (6.0, 0.03),
    (4.0, 0.07),
    (2.5, 0.12),
    (1.0, 0.18),
    (0.0, 0.28),
]

def _rounded_rect_path(cr, x, y, w, h, r):

    r = min(r, w / 3, h / 3)
    if r <= 0:
        cr.rectangle(x, y, w, h)
        return
    cr.new_sub_path()
    cr.arc(x + w - r, y + r,     r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r,  0,            math.pi / 2)
    cr.arc(x + r,     y + h - r, r,  math.pi / 2,  math.pi)
    cr.arc(x + r,     y + r,     r,  math.pi,      3 * math.pi / 2)
    cr.close_path()

def _render_to_surface(window, rects, radius, colour):
    alloc = window.get_allocation()
    w, h = alloc.width, alloc.height
    if w <= 0 or h <= 0 or not rects:
        return None

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surface)
    r, g, b = colour

    for expand, alpha in _BLOOM_PASSES:

        cr.push_group()
        cr.set_operator(cairo.OPERATOR_OVER)
        cr.set_source_rgba(r, g, b, alpha)
        for rect in rects:
            _rounded_rect_path(
                cr,
                rect.x - expand,
                rect.y - expand,
                rect.width  + expand * 2,
                rect.height + expand * 2,
                radius + expand,
            )
            cr.fill()
        cr.pop_group_to_source()

        cr.set_operator(cairo.OPERATOR_SCREEN)
        cr.paint_with_alpha(1.0)

    cr.set_operator(cairo.OPERATOR_CLEAR)
    for rect in rects:
        _rounded_rect_path(cr, rect.x, rect.y, rect.width, rect.height, radius)
        cr.fill()

    return surface

class _ShadowState:
    def __init__(self, window, radius, colour):
        self.window  = window
        self.radius  = radius
        self.colour  = colour
        self._surface          = None
        self._retrace_source   = None
        self._pending_retrace  = False
        self._draw_id          = 0
        self._alloc_id         = 0

    def schedule_retrace(self):
        if self._retrace_source is not None:
            GLib.source_remove(self._retrace_source)
        self._retrace_source = GLib.timeout_add(_RETRACE_DELAY_MS, self._do_retrace)

    def _do_retrace(self):
        self._retrace_source = None
        rects = trace_widget(self.window, min_alpha=10, relative_alpha=0.0, inset=4)
        new_surface = _render_to_surface(self.window, rects, self.radius, self.colour)
        self._surface = new_surface
        self.window.queue_draw()
        return False

    def _retrace_idle(self):
        rects = trace_widget(self.window, min_alpha=10, relative_alpha=0.0, inset=4)
        new_surface = _render_to_surface(self.window, rects, self.radius, self.colour)

        self._surface = new_surface
        self.window.queue_draw()
        return False

    def disconnect(self):
        if self._retrace_source is not None:
            GLib.source_remove(self._retrace_source)
            self._retrace_source = None
        for attr in ("_draw_id", "_alloc_id"):
            sig = getattr(self, attr, 0)
            if sig:
                try:
                    self.window.disconnect(sig)
                except Exception:
                    pass
            setattr(self, attr, 0)
        self._surface = None

def _on_draw(widget, cr, state):
    if state._surface is None:
        return False
    cr.save()
    cr.set_operator(cairo.OPERATOR_OVER)
    cr.set_source_surface(state._surface, 0, 0)
    cr.paint()
    cr.restore()
    return False

def add_shadow(window, radius=14.0, colour=(0.0, 0.0, 0.0)):
    state = _ShadowState(window, radius, colour)
    state._draw_id = window.connect("draw", lambda w, cr: _on_draw(w, cr, state))

    def on_alloc(w, _):
        if state._surface is None:
            state.schedule_retrace()

    state._alloc_id = window.connect("size-allocate", on_alloc)
    GLib.timeout_add(300, state._do_retrace)
    return state