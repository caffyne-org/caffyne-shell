import shutil
from gi.repository import GioUnix, Gtk, GdkPixbuf, GLib, Gio
from PIL import Image as PILImage, ImageEnhance, ImageFilter
import io
from snippets import enable_blur, set_blur_regions_from_widget
from .icon_resolver import IconResolver
_resolver = IconResolver()

def get_app_icon_name(app_id: str) -> str | None:
    return _resolver.get_icon(app_id)

def popup_with_blur(menu: Gtk.Menu, event, step: int = 1):
    blur_ctx = None

    def do_blur():
        nonlocal blur_ctx
        blur_ctx = enable_blur(menu)
        def do_set_regions():
            if blur_ctx:
                set_blur_regions_from_widget(blur_ctx, menu, step=step)
            return False
        GLib.timeout_add(50, do_set_regions)

    menu.show_all()
    menu.popup_at_pointer(event)
    GLib.idle_add(do_blur)

def executable_exists(executable_name):
    executable_path = shutil.which(executable_name)
    return bool(executable_path)


def load_blurred_pixbuf(
    path: str,
    width: int,
    height: int,
    blur_radius=10,
    darken_factor=1.0,
):
    try:
        img = PILImage.open(path).convert("RGBA")
        img = img.resize((width, height))
        img = img.filter(ImageFilter.GaussianBlur(blur_radius))

        if darken_factor < 1.0:
            img = ImageEnhance.Brightness(img).enhance(darken_factor)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        loader = GdkPixbuf.PixbufLoader.new_with_type("png")
        loader.write(buf.read())
        loader.close()

        return loader.get_pixbuf()
    except Exception:
        return None
    
def load_scaled_pixbuf(path: str, width: int, height: int):
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(
            path, width, height, False
        )
    except Exception:
        return None
    
def load_cover_pixbuf(path: str, width: int, height: int):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)

    src_w = pixbuf.get_width()
    src_h = pixbuf.get_height()
    
    # Crop to centered square using the smaller dimension
    square_size = min(src_w, src_h)
    x = (src_w - square_size) // 2
    y = (src_h - square_size) // 2
    cropped = pixbuf.new_subpixbuf(x, y, square_size, square_size)

    # Now scale the square down to the target size
    return cropped.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)