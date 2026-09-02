from gi.repository import Gtk

from .cairo_reveal import CairoReveal
from .gl_reveal import ShaderReveal
from .reveal_shaders import DASH_FRAG_SRC


class ShaderDashReveal(ShaderReveal):
    TRANSITION = "dash_reveal"
    DEFAULT_FRAG = DASH_FRAG_SRC

    def __init__(
        self,
        child: Gtk.Widget | None = None,
        open_bezier: tuple[float, float, float, float] = (0.16, 1.0, 0.3, 1.0),
        close_bezier: tuple[float, float, float, float] = (0.16, 1.0, 0.3, 1.0),
        open_duration: float = 0.3,
        close_duration: float = 0.3,
        **kwargs,
    ):
        super().__init__(
            child=child,
            open_bezier=open_bezier,
            close_bezier=close_bezier,
            open_duration=open_duration,
            close_duration=close_duration,
            **kwargs,
        )
        self.show_all()
        self._gl_area.hide()


class CairoDashReveal(CairoReveal):
    TRANSITION = "dash_reveal"
    SCALE_START = 0.8

    def __init__(
        self,
        child: Gtk.Widget | None = None,
        open_bezier: tuple[float, float, float, float] = (0.05, 0.9, 0.1, 1.0),
        close_bezier: tuple[float, float, float, float] = (0.16, 1.0, 0.3, 1.0),
        open_duration: float = 0.25,
        close_duration: float = 0.22,
        **kwargs,
    ):
        super().__init__(
            child=child,
            open_bezier=open_bezier,
            close_bezier=close_bezier,
            open_duration=open_duration,
            close_duration=close_duration,
            **kwargs,
        )


def DashReveal(*args, **kwargs) -> ShaderDashReveal | CairoDashReveal:
    from services.animation import shaders_enabled

    variant = ShaderDashReveal if shaders_enabled() else CairoDashReveal
    return variant(*args, **kwargs)
