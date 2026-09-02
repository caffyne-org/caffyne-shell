import logging
import cairo
import gi
import moderngl
import numpy as np

gi.require_version("Gtk", "3.0")
from gi.repository import GLib

log = logging.getLogger("GLPipeline")


def create_gl_context(gl_area=None) -> moderngl.Context:
    """Wrap the GL context GTK has already made current.

    ``moderngl.create_context()`` is not usable here. Its first call in a
    process attaches to whatever context is current through a plain symbol
    loader -- which is what we want, and works whether GDK is talking EGL or
    GLX -- but it caches that Context object process-wide, and every later
    caller is pushed down a backend "detect" path instead. That path is GLX,
    and under a Wayland session GDK's context is EGL, so it finds nothing:

        (detect) glXGetCurrentContext: cannot detect OpenGL context

    while the EGL backend cannot attach to an existing context at all. So the
    cache is cleared around the call: each GLArea gets its own Context, built
    the way the first one is, and none of them is left cached for the next.

    No version is demanded of the context. GTK hands out whatever the
    driver gives -- GLES on this setup -- and a shader written for another
    dialect reports that far more usefully than a version comparison here.
    """
    moderngl._store.default_context = None
    try:
        ctx = moderngl.get_context()
    finally:
        moderngl._store.default_context = None

    return ctx


class GLPipeline:
    """A compiled fullscreen-quad program plus the state it needs to draw.

    Two shapes of shader go through here.

    ``wrap=True`` (the default) is the Shadertoy contract: the fragment
    source only supplies ``mainImage``, and the pipeline prepends the
    ``iResolution`` / ``iTime`` / ``iChannel*`` uniform block and appends the
    ``main`` that calls it. The quad comes from a vertex buffer.

    ``wrap=False`` takes the fragment source verbatim, alongside a vertex
    shader of your own. That is the contract the reveal widgets and the
    animation packs are written against -- ``in vec2 uv``, ``out vec4
    fragColor``, and whatever uniforms the shader declares -- and their
    vertex shader builds the quad from ``gl_VertexID`` with no attributes at
    all, so no vertex buffer is created for it.
    """

    VERTEX_BUFFER = """#version 320 es
    in vec2 position;
    void main()
    {
        gl_Position = vec4(position, 0.0, 1.0);
    }
    """

    FRAGMENT_UNIFORMS = """#version 320 es
    precision highp float;
    uniform vec3 iResolution;
    uniform float iTime;
    uniform float iTimeDelta;
    uniform float iFrameRate;
    uniform int iFrame;
    uniform float iChannelTime[4];
    uniform vec3 iChannelResolution[4];
    uniform vec4 iMouse;
    uniform sampler2D iChannel0;
    uniform sampler2D iChannel1;
    uniform sampler2D iChannel2;
    uniform sampler2D iChannel3;
    uniform vec4 iDate;
    uniform float iSampleRate;
    """

    FRAGMENT_MAIN = """
    out vec4 fragColor;
    void main()
    {
        mainImage(fragColor, gl_FragCoord.xy);
    }
    """

    # Cairo hands us premultiplied ARGB32, so a texture drawn straight to the
    # framebuffer wants ONE / ONE_MINUS_SRC_ALPHA. The Shadertoy path keeps
    # the straight-alpha blend it has always used.
    BLEND_STRAIGHT = (
        moderngl.SRC_ALPHA,
        moderngl.ONE_MINUS_SRC_ALPHA,
        moderngl.ONE,
        moderngl.ONE_MINUS_SRC_ALPHA,
    )
    BLEND_PREMULTIPLIED = (
        moderngl.ONE,
        moderngl.ONE_MINUS_SRC_ALPHA,
        moderngl.ONE,
        moderngl.ONE_MINUS_SRC_ALPHA,
    )

    def __init__(
        self,
        fragment_buffer: str,
        ctx: moderngl.Context,
        width: int = 1,
        height: int = 1,
        vertex_buffer: str | None = None,
        wrap: bool = True,
        blend_func: tuple | None = None,
    ):
        self.fragment_buffer = fragment_buffer
        self.ctx = ctx
        self.width = max(1, width)
        self.height = max(1, height)
        self.wrap = wrap
        self.vertex_buffer = vertex_buffer or self.VERTEX_BUFFER
        self.blend_func = blend_func or self.BLEND_STRAIGHT

        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = self.blend_func

        # Hook directly into GTK GLArea's native framebuffer
        self.ctx.detect_framebuffer()

        self.program = None
        self.vao = None
        self._quad = None
        self._members: frozenset[str] = frozenset()
        self._build(fragment_buffer)

        self.start_time = GLib.get_monotonic_time() / 1e6
        self.frame_time = self.start_time
        self.frame_count = 0

    # ------------------------------------------------------------------
    # Program
    # ------------------------------------------------------------------

    def _source(self, fragment_buffer: str) -> str:
        if not self.wrap:
            return fragment_buffer
        return self.FRAGMENT_UNIFORMS + fragment_buffer + self.FRAGMENT_MAIN

    def _build(self, fragment_buffer: str):
        program = self.ctx.program(
            fragment_shader=self._source(fragment_buffer),
            vertex_shader=self.vertex_buffer,
        )
        members = frozenset(program)

        # A vertex shader that derives the quad from gl_VertexID declares no
        # attributes, so it gets an empty vertex array and a vertex count.
        if "position" in members:
            quad = self.ctx.buffer(
                np.array((-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0), dtype="f4")
            )
            vao = self.ctx.vertex_array(program, [(quad, "2f", "position")])
        else:
            quad = None
            vao = self.ctx.vertex_array(program, [])

        self.release_program()
        self.fragment_buffer = fragment_buffer
        self.program = program
        self.vao = vao
        self._quad = quad
        self._members = members

    def recompile(self, fragment_buffer: str) -> bool:
        """Swap in a new fragment shader, keeping the old one on failure."""
        try:
            self._build(fragment_buffer)
        except Exception as e:
            log.error("shader compile failed: %s", e)
            return False
        return True

    def has(self, name: str) -> bool:
        return name in self._members

    def set_uniform(self, name: str, value):
        if name not in self._members:
            return False
        try:
            self.program[name].value = value
        except Exception:
            return False
        return True

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def render(
        self,
        width: int,
        height: int,
        clear: bool = True,
        framebuffer: moderngl.Framebuffer | None = None,
    ):
        if not self.vao or not self.ctx or width <= 1 or height <= 1:
            return

        self.width = width
        self.height = height

        # Defaults to GTK GLArea's active framebuffer. Pass one explicitly to
        # draw the same frame somewhere else -- an offscreen probe, say --
        # without the detected binding stealing it back.
        target_fbo = framebuffer or self.ctx.detect_framebuffer()
        target_fbo.use()

        # GTK owns the context between frames, so the blend state is set per
        # frame rather than trusted to survive from realize.
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = self.blend_func

        # Clear FBO to prevent visual garbage in VRAM
        if clear:
            self.ctx.clear(0.0, 0.0, 0.0, 0.0)
        self.ctx.viewport = (0, 0, width, height)

        current_time = GLib.get_monotonic_time() / 1e6
        time_delta = current_time - self.frame_time

        self.set_uniform("iResolution", (float(width), float(height), 1.0))
        self.set_uniform("iTime", current_time - self.start_time)
        self.set_uniform("iTimeDelta", time_delta)
        self.set_uniform("iFrameRate", 1.0 / time_delta if time_delta > 0 else 60.0)
        self.set_uniform("iFrame", self.frame_count)
        self.set_uniform("u_resolution", (float(width), float(height)))

        self.vao.render(moderngl.TRIANGLE_STRIP, vertices=4)

        self.frame_time = current_time
        self.frame_count += 1

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def release_program(self):
        for obj in (self.vao, self._quad, self.program):
            if obj is not None:
                try:
                    obj.release()
                except Exception:
                    pass
        self.vao = self._quad = self.program = None
        self._members = frozenset()

    def release(self):
        """Drop every GL object. Call with the owning context current."""
        self.release_program()
        self.ctx = None


class PipelineTextureStream:
    """Streams a widget's cairo rendering into one long-lived moderngl texture.

    The moderngl counterpart of ``TextureStream``, and it keeps the same
    lifetimes for the same reasons: the texture survives between animations
    because reallocating texture storage costs a driver round trip that lands
    on the first frame, where a stutter is visible; the cairo surface is
    dropped the moment it has been uploaded because it is several megabytes
    of system RAM that nothing reads again.
    """

    def __init__(self):
        self._surface: cairo.ImageSurface | None = None
        self._texture: moderngl.Texture | None = None
        self._dirty = False

    @property
    def texture(self) -> moderngl.Texture | None:
        return self._texture

    @property
    def has_texture(self) -> bool:
        return self._texture is not None

    def surface(self, width: int, height: int) -> cairo.ImageSurface:
        """A cleared ARGB32 surface, reusing the previous one when it fits."""
        if (
            self._surface is not None
            and self._surface.get_width() == width
            and self._surface.get_height() == height
        ):
            cr = cairo.Context(self._surface)
            cr.set_operator(cairo.OPERATOR_CLEAR)
            cr.paint()
        else:
            self._surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
        self._dirty = True
        return self._surface

    @property
    def surface_ref(self) -> cairo.ImageSurface | None:
        """The surface as last drawn, until it is uploaded and let go of."""
        return self._surface

    def drop_surface(self):
        self._surface = None

    def upload(
        self,
        ctx: moderngl.Context,
        mipmaps: bool = False,
        keep_surface: bool = False,
    ) -> bool:
        """Push the surface to the GPU, then let go of it."""
        if not self._dirty or self._surface is None:
            return self._texture is not None

        self._surface.flush()
        width = self._surface.get_width()
        height = self._surface.get_height()
        stride = self._surface.get_stride()
        data = self._surface.get_data()

        # Cairo pads rows to its own alignment. For ARGB32 that is already
        # width * 4, but a padded stride would upload skewed, so repack.
        if stride != width * 4:
            data = b"".join(
                bytes(data[row * stride : row * stride + width * 4])
                for row in range(height)
            )

        if self._texture is None or self._texture.size != (width, height):
            if self._texture is not None:
                self._texture.release()
            self._texture = ctx.texture((width, height), 4)
            # Cairo's ARGB32 is BGRA in memory on little-endian machines.
            self._texture.swizzle = "BGRA"
            self._texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            self._texture.repeat_x = False
            self._texture.repeat_y = False

        self._texture.write(data)

        # Only a region probe samples the lower levels; building the chain for
        # a widget nobody is tracing is a third of the texture wasted.
        if mipmaps:
            self._texture.build_mipmaps()

        self._dirty = False

        if not keep_surface:
            self._surface = None
        return True

    def use(self, location: int = 0):
        if self._texture is not None:
            self._texture.use(location=location)

    def release(self):
        """Drop every GL object. Call with the owning context current."""
        if self._texture is not None:
            try:
                self._texture.release()
            except Exception:
                pass
            self._texture = None
        self._surface = None
        self._dirty = False
