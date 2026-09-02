from cffi import FFI
from .region_trace import trace_widget
from fabric.utils import get_relative_path
ffi = FFI()

ffi.cdef("""
    typedef struct BlurContext BlurContext;

    int          blur_supported(void *wl_display);
    BlurContext* blur_enable(void *wl_display, void *wl_surface);
    void         blur_set_region(BlurContext *ctx,
                                 int32_t x, int32_t y,
                                 int32_t width, int32_t height);
    void         blur_set_regions(BlurContext *ctx,
                                  const int32_t *xs, const int32_t *ys,
                                  const int32_t *widths, const int32_t *heights,
                                  int count);
    void         blur_disable(BlurContext *ctx);
    void         blur_free(BlurContext *ctx);
""")

ffi.cdef("""
    typedef struct _GtkWidget  GtkWidget;
    typedef struct _GdkWindow  GdkWindow;
    typedef struct _GdkDisplay GdkDisplay;

    GdkWindow*  gtk_widget_get_window(GtkWidget *widget);
    GdkDisplay* gtk_widget_get_display(GtkWidget *widget);

    void* gdk_wayland_display_get_wl_display(GdkDisplay *display);
    void* gdk_wayland_window_get_wl_surface(GdkWindow *window);
""")

libblur = ffi.dlopen(get_relative_path("./lib/libblur.so"))
libgtk  = ffi.dlopen("libgtk-3.so.0")
libgdk  = ffi.dlopen("libgdk-3.so.0")

def _get_wl_pointers(widget):
    ptr     = ffi.cast("GtkWidget*", hash(widget))
    gdk_win = libgtk.gtk_widget_get_window(ptr)
    gdk_dpy = libgtk.gtk_widget_get_display(ptr)

    if not gdk_win:
        raise RuntimeError(
            "Widget has no GDK window — is it realized? "
            "Connect to the 'realize' signal before calling blur functions."
        )

    wl_display = libgdk.gdk_wayland_display_get_wl_display(gdk_dpy)
    wl_surface = libgdk.gdk_wayland_window_get_wl_surface(gdk_win)

    return wl_display, wl_surface

def wl_surface_id(widget) -> int:
    """Address of ``widget``'s current wl_surface, or 0 if it has none.

    GTK destroys the wl_surface on hide and builds a fresh one on the next
    show, so the identity matters and not just the presence: a BlurContext
    stores the surface it was created against and commits it on every call,
    which means a context outliving a hide/show cycle commits a pointer the
    compositor has already freed. Callers that survive across maps compare
    this against the value they enabled with and rebuild when it changes.
    """
    try:
        ptr = ffi.cast("GtkWidget*", hash(widget))
        gdk_win = libgtk.gtk_widget_get_window(ptr)
        if not gdk_win:
            return 0
        surface = libgdk.gdk_wayland_window_get_wl_surface(gdk_win)
        if not surface:
            return 0
        return int(ffi.cast("uintptr_t", surface))
    except Exception:
        return 0

def has_wl_surface(widget) -> bool:
    """Whether ``widget`` still owns a live wl_surface.

    A toplevel withdraws its GdkWindow before it unmaps its children, so a
    child that waits for its own ::unmap is already too late: the surface is
    gone, and committing it crashes inside libwayland. Anything that touches
    the surface during teardown has to ask first.
    """
    return wl_surface_id(widget) != 0

def is_blur_supported(widget) -> bool:
    wl_display, _ = _get_wl_pointers(widget)
    return bool(libblur.blur_supported(wl_display))

def enable_blur(widget) -> "BlurContext | None":
    try:
        wl_display, wl_surface = _get_wl_pointers(widget)

        if not wl_surface:
            # Realized but not on screen. GTK drops the wl_surface on hide and
            # only builds a new one while showing, so a caller inside the map
            # cycle can arrive before it exists -- and blur_enable() commits
            # the surface without checking, which segfaults in libwayland.
            print("enable_blur: widget has no wl_surface yet")
            return None

        ctx = libblur.blur_enable(wl_display, wl_surface)

        if not ctx:
            print("enable_blur: compositor does not support ext_background_effect_manager_v1")
            return None

        return ctx
    except Exception as e:
        print(f"enable_blur failed: {e}")
        return None

def set_blur_region(ctx, x: int, y: int, width: int, height: int):
    libblur.blur_set_region(ctx, x, y, width, height)

def set_blur_regions(ctx, rects: list[tuple[int, int, int, int]]):
    count = len(rects)
    if count == 0:
        return

    xs      = ffi.new("int32_t[]", [r[0] for r in rects])
    ys      = ffi.new("int32_t[]", [r[1] for r in rects])
    widths  = ffi.new("int32_t[]", [r[2] for r in rects])
    heights = ffi.new("int32_t[]", [r[3] for r in rects])

    libblur.blur_set_regions(ctx, xs, ys, widths, heights, count)

def set_blur_regions_from_widget(ctx, widget, step: int = 1,
                                 min_alpha: int = 8, relative_alpha: float = 0.5,
                                 inset: int = 0):
    """Blur exactly where ``widget`` paints.

    ``relative_alpha`` thresholds against the widget's own most opaque pixel,
    which keeps a drop shadow out of the region without the caller having to
    guess at an erode margin to compensate.
    """
    rects = trace_widget(widget, min_alpha=min_alpha,
                         relative_alpha=relative_alpha, inset=inset, step=step)
    set_blur_regions(ctx, [(r.x, r.y, r.width, r.height) for r in rects])

def disable_blur(ctx):
    libblur.blur_disable(ctx)

def free_blur(ctx):
    libblur.blur_free(ctx)
