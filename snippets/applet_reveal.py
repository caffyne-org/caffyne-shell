from typing import Literal

from gi.repository import Gtk

from .cairo_reveal import CairoReveal
from .gl_reveal import ShaderReveal
from .reveal_shaders import APPLET_FRAG_SRC


class ShaderAppletReveal(ShaderReveal):
    TRANSITION = "applet_reveal"
    DEFAULT_FRAG = APPLET_FRAG_SRC
    RESTORE_CHILD_ON_CLOSE = False

    def __init__(
        self,
        direction: Literal["down", "up"] = "down",
        child: Gtk.Widget | None = None,
        open_bezier: tuple[float, float, float, float] = (0.17, 0.67, 0.0, 1.0),
        close_bezier: tuple[float, float, float, float] = (0.16, 1.0, 0.3, 1.0),
        open_duration: float = 0.3,
        close_duration: float = 0.2,
        **kwargs,
    ):
        self._direction = direction
        super().__init__(
            child=child,
            open_bezier=open_bezier,
            close_bezier=close_bezier,
            open_duration=open_duration,
            close_duration=close_duration,
            **kwargs,
        )

    @property
    def direction(self) -> str:
        return self._direction

    @direction.setter
    def direction(self, value: Literal["down", "up"]):
        self._direction = value

    def _extra_uniforms(self) -> dict:
        return {"u_direction": 0 if self._direction == "down" else 1}


class CairoAppletReveal(CairoReveal):
    TRANSITION = "applet_reveal"
    SCALE_START = 0.6

    def __init__(
        self,
        direction: Literal["down", "up"] = "down",
        child: Gtk.Widget | None = None,
        open_bezier: tuple[float, float, float, float] = (0.16, 1.0, 0.3, 1.0),
        close_bezier: tuple[float, float, float, float] = (0.16, 1.0, 0.3, 1.0),
        open_duration: float = 0.22,
        close_duration: float = 0.16,
        **kwargs,
    ):
        self._direction = direction
        super().__init__(
            child=child,
            open_bezier=open_bezier,
            close_bezier=close_bezier,
            open_duration=open_duration,
            close_duration=close_duration,
            **kwargs,
        )

    @property
    def direction(self) -> str:
        return self._direction

    @direction.setter
    def direction(self, value: Literal["down", "up"]):
        self._direction = value
        self.queue_draw()

    def _anchor(self, width: int, height: int) -> tuple[float, float]:
        return width / 2.0, 0.0 if self._direction == "down" else float(height)


def AppletReveal(*args, **kwargs) -> ShaderAppletReveal | CairoAppletReveal:
    from services.animation import shaders_enabled

    variant = ShaderAppletReveal if shaders_enabled() else CairoAppletReveal
    return variant(*args, **kwargs)
