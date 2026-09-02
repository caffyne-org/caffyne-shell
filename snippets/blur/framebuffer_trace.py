import moderngl

from .region_trace import Rect, regions_from_alpha


class FramebufferRegionTracer:
    def __init__(
        self,
        ctx: moderngl.Context,
        divisor: int = 2,
        max_grid: int = 192,
        min_alpha: int = 8,
        relative_alpha: float = 0.5,
    ):
        self.ctx            = ctx
        self.divisor        = max(1, divisor)
        self.max_grid       = max(8, max_grid)
        self.min_alpha      = min_alpha
        self.relative_alpha = relative_alpha

        self._fbo: moderngl.Framebuffer | None = None
        self._texture: moderngl.Texture | None = None
        self._pbos: list[moderngl.Buffer] = []
        self._grid        = (0, 0)
        self._size        = 0
        self._slot        = 0
        self._filled: set[int] = set()
        self._synchronous = False


    def _grid_for(self, dev_width: int, dev_height: int) -> tuple[int, int]:
        gw = max(1, min(self.max_grid, -(-dev_width  // self.divisor)))
        gh = max(1, min(self.max_grid, -(-dev_height // self.divisor)))
        return gw, gh

    def _ensure_target(self, gw: int, gh: int) -> bool:
        if self._grid == (gw, gh) and self._fbo is not None:
            return True

        self.release()
        try:
            self._texture = self.ctx.texture((gw, gh), 4)
            self._texture.filter = (moderngl.NEAREST, moderngl.NEAREST)
            self._fbo = self.ctx.framebuffer(color_attachments=[self._texture])
            self._size = gw * gh * 4
            self._pbos = [self.ctx.buffer(reserve=self._size) for _ in range(2)]
        except Exception:
            self.release()
            return False

        self._grid   = (gw, gh)
        self._slot   = 0
        self._filled = set()
        return True

    def release(self):
        for obj in (*self._pbos, self._fbo, self._texture):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass

        self._pbos    = []
        self._fbo     = None
        self._texture = None
        self._grid    = (0, 0)
        self._size    = 0
        self._filled  = set()

    def reset(self):
        self._filled = set()

    def capture(
        self,
        draw,
        screen: moderngl.Framebuffer,
        dev_width: int,
        dev_height: int,
        out_width: int,
        out_height: int,
        inset: int = 0,
    ) -> list[Rect] | None:
        if dev_width <= 0 or dev_height <= 0 or out_width <= 0 or out_height <= 0:
            return None

        gw, gh = self._grid_for(dev_width, dev_height)
        if not self._ensure_target(gw, gh):
            return None

        pending = 1 - self._slot
        data = (
            bytes(self._pbos[pending].read())
            if not self._synchronous and pending in self._filled
            else None
        )

        try:
            draw(self._fbo, gw, gh)

            if self._synchronous:
                data = self._fbo.read(components=4)
            else:
                try:
                    self._fbo.read_into(self._pbos[self._slot], components=4)
                    self._filled.add(self._slot)
                    self._slot = pending
                except Exception:
                    self._synchronous = True
                    data = self._fbo.read(components=4)
        finally:
            screen.use()

        if data is None or len(data) < self._size:
            return None

        return regions_from_alpha(
            data[3::4], gw, gh,
            min_alpha=self.min_alpha,
            relative_alpha=self.relative_alpha,
            flip_y=True,
            out_width=out_width,
            out_height=out_height,
            inset=inset,
        )
