import os
import shutil
import subprocess
import threading
import gc
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from PIL import Image as PILImage, ImageFilter
from gi.repository import GLib, Gdk, Gtk, GtkLayerShell, GdkPixbuf
from fabric.core.service import Service, Signal, Property
from fabric.widgets.eventbox import EventBox
from fabric.widgets.wayland import WaylandWindow
from loguru import logger
from user_options import user_options
from utils.helpers import popup_with_blur
CACHE_WALLPAPER_PATH = os.path.expanduser("~/.cache/caffyne-shell/wallpaper")
CACHE_BLURRED_PATH   = os.path.expanduser("~/.cache/caffyne-shell/wallpaper_blurred")

AWWW_TRANSITION_FPS      = 60
AWWW_TRANSITION_DURATION = 1.5
AWWW_TRANSITION_BEZIER   = ".43,1.19,1,.4"

RESIZE_MODES = ("no", "crop", "fit", "stretch")

DEFAULT_WALLPAPER_PATH = os.path.join(os.path.dirname(__file__), "assets/default-wallpaper.jpg")

def _generate_blurred_cache(path: str, blur_radius: int = 20) -> None:
    try:
        tmp_path = CACHE_BLURRED_PATH
        with PILImage.open(path) as img:
            img.draft("RGB", (1920, 1080))
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((1920, 1080), PILImage.Resampling.LANCZOS)
            blurred = img.filter(ImageFilter.GaussianBlur(blur_radius))
            blurred.save(tmp_path, format="JPEG", quality=80, progressive=True)
            blurred.close()
            del blurred
        os.replace(tmp_path, CACHE_BLURRED_PATH)
    except Exception as e:
        logger.error(f"WallpaperService: failed to generate blurred cache: {e}")

def _awww_set(
    path: str,
    pos: tuple[float, float] | None = None,
) -> None:
    x, y = pos if pos is not None else (0.5, 0.5)

    opts = user_options.wallpaper

    cmd = [
        "awww", "img", path,
        "--transition-type",     "grow",
        "--transition-pos",      f"{x:.4f},{y:.4f}",
        "--transition-fps",      str(AWWW_TRANSITION_FPS),
        "--transition-duration", str(AWWW_TRANSITION_DURATION),
        "--transition-bezier",   AWWW_TRANSITION_BEZIER,
    ]

    resize = getattr(opts, "resize", "crop")
    if resize in RESIZE_MODES:
        cmd += ["--resize", resize]

    try:
        subprocess.Popen(cmd)
        logger.info(f"awww: set {path!r} with grow from ({x:.3f}, {y:.3f})")
    except FileNotFoundError:
        logger.error("awww not found — is it installed and on your PATH?")
    except Exception as e:
        logger.error(f"awww: failed to run: {e}")

class WallpaperDropWindow(WaylandWindow):
    def __init__(self, monitor_id: int) -> None:
        self._monitor_id = monitor_id
        self._box = EventBox(h_expand=True, v_expand=True)
        self.bar_manager = None

        super().__init__(
            monitor=monitor_id,
            anchor="left right top bottom",
            exclusivity="ignore",
            layer="background",
            child=self._box,
            visible=True,
            title=f"wallpaper-drop-{monitor_id}",
        )

        self.show_all()
        GtkLayerShell.set_exclusive_zone(self, -1)
        self._box.connect("button-press-event", self._on_button_press)
        self._setup_drag_and_drop()

    def _on_button_press(self, widget, event: Gdk.EventButton):
        if event.button != 3:
            return False

        menu = Gtk.Menu()

        bar_count = sum(
            1
            for bar in self.bar_manager._bars.values()
            if bar.monitor_id == self._monitor_id
        )

        if self.bar_manager and bar_count < 2:
            add_item = Gtk.MenuItem(label="Add Bar")
            add_item.connect(
                "activate",
                lambda _: self.bar_manager.add_bar_for_monitor(self._monitor_id)
            )
            menu.append(add_item)
        else:
            item = Gtk.MenuItem(label="Maximum bars(2) reached on this monitor")
            item.set_sensitive(False)
            menu.append(item)

        if user_options.theme.blur:
            popup_with_blur(menu, event)
        else:
            menu.show_all()
            menu.popup_at_pointer(event)

        return True
    def set_bar_manager(self, bar_manager) -> None:
        self.bar_manager = bar_manager
    def _setup_drag_and_drop(self) -> None:
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_set_target_list(Gtk.TargetList.new([]))
        target_list = self.drag_dest_get_target_list()
        if target_list:
            target_list.add_text_targets(0)
            target_list.add_uri_targets(0)

        self.connect("drag-data-received", self._on_drag_data_received)
        self.connect("drag-motion",        self._on_drag_motion)
        self.connect("drag-drop",          self._on_drag_drop)

    def _on_drag_motion(self, widget, context, x, y, timestamp):
        Gdk.drag_status(context, Gdk.DragAction.COPY, timestamp)
        return True

    def _on_drag_drop(self, widget, context, x, y, timestamp):
        for target in context.list_targets():
            name = target.name()
            if name in ("text/uri-list", "text/plain", "STRING"):
                self.drag_get_data(context, Gdk.Atom.intern(name, False), timestamp)
                return True
        return False

    def _on_drag_data_received(self, widget, context, x, y, data, info, timestamp):
        if data and data.get_data():
            text = data.get_data().decode("utf-8", errors="ignore")
            for line in text.strip().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    text = line
                    break

            from urllib.parse import unquote
            path = unquote(text.replace("file://", "").strip())

            if path.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")):

                alloc = self.get_allocation()
                nx = x / alloc.width  if alloc.width  > 0 else 0.5
                ny = 1.0 - (y / alloc.height if alloc.height > 0 else 0.5)
                nx = max(0.0, min(1.0, nx))
                ny = max(0.0, min(1.0, ny))

                logger.info(f"Drop on monitor {self._monitor_id}: {path!r} at ({nx:.3f}, {ny:.3f})")
                WallpaperService.get_instance().set_wallpaper(path, pos=(nx, ny))

        context.finish(True, False, timestamp)

class WallpaperService(Service):

    _instance: "WallpaperService | None" = None

    @staticmethod
    def get_instance() -> "WallpaperService":
        if WallpaperService._instance is None:
            WallpaperService._instance = WallpaperService()
        return WallpaperService._instance

    @Signal
    def wallpaper_changed(self, path: str) -> None: ...

    @Property(str, "readable", default_value="")
    def wallpaper_path(self) -> str:
        return self._wallpaper_path

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._blurred_pixbuf: GdkPixbuf.Pixbuf | None = None
        # self._windows: dict[int, WallpaperDropWindow] = {}
        self._bar_manager = None

        self._wallpaper_path: str = (
            user_options.wallpaper.path
            or (CACHE_WALLPAPER_PATH if os.path.isfile(CACHE_WALLPAPER_PATH) else "")
            or (DEFAULT_WALLPAPER_PATH if os.path.isfile(DEFAULT_WALLPAPER_PATH) else "")
        )

        os.makedirs(os.path.dirname(CACHE_WALLPAPER_PATH), exist_ok=True)

        # display = Gdk.Display.get_default()
        # if display:
            # display.connect("monitor-added",  self._on_monitor_added)
            # display.connect("monitor-removed", self._on_monitor_removed)

        self._ensure_awww_daemon()
        # self._sync_monitors()

        if self._wallpaper_path and os.path.isfile(self._wallpaper_path):
            _awww_set(self._wallpaper_path)

    def _ensure_awww_daemon(self) -> None:
        """Start awww-daemon if it isn't already running."""
        try:
            result = subprocess.run(["awww", "query"], capture_output=True)
            if result.returncode == 0:
                logger.info("awww-daemon already running")
                return
        except FileNotFoundError:
            logger.error("awww not found — install it with your package manager")
            return

        try:
            subprocess.Popen(["awww-daemon"])

            GLib.timeout_add(500, lambda: None)
            logger.info("awww-daemon started")
        except Exception as e:
            logger.error(f"Failed to start awww-daemon: {e}")

    def _clear_blurred_pixbuf(self) -> None:
        """Explicitly unref and clear the cached pixbuf to free memory."""
        if self._blurred_pixbuf is not None:
            self._blurred_pixbuf = None

    def set_wallpaper(self, path: str, pos: tuple[float, float] | None = None) -> None:
        if not os.path.isfile(path):
            logger.warning(f"WallpaperService: path does not exist: {path}")
            return

        _awww_set(path, pos)
        self._clear_blurred_pixbuf()

        def copy_to_cache():
            try:
                shutil.copyfile(path, CACHE_WALLPAPER_PATH)
                self._wallpaper_path = path
                user_options.wallpaper.path = path
                user_options.save()
                self.notify("wallpaper-path")
                self.wallpaper_changed(path)

                threading.Thread(
                    target=_generate_blurred_cache,
                    args=(CACHE_WALLPAPER_PATH,),
                    daemon=True,
                ).start()

            except shutil.SameFileError:
                self._wallpaper_path = path
                user_options.wallpaper.path = path
                user_options.save()
                self.notify("wallpaper-path")
                self.wallpaper_changed(path)

                threading.Thread(
                    target=_generate_blurred_cache,
                    args=(CACHE_WALLPAPER_PATH,),
                    daemon=True,
                ).start()

            except Exception as e:
                logger.error(f"WallpaperService: failed to copy to cache: {e}")

            return GLib.SOURCE_REMOVE
        def cleanup_mem():
                gc.collect()
                return False
        GLib.timeout_add(4000, cleanup_mem)
        GLib.timeout_add(int(AWWW_TRANSITION_DURATION * 1000) + 100, copy_to_cache)
        # self.emit("wallpaper-changed", path)

    def _sync_monitors(self) -> None:
        display  = Gdk.Display.get_default()
        current  = set(range(display.get_n_monitors()))
        existing = set(self._windows.keys())
        for mid in existing - current:
            self._remove_window(mid)
        for mid in current - existing:
            self._add_window(mid)

    def _add_window(self, monitor_id: int) -> None:
        if monitor_id in self._windows:
            return
        window = WallpaperDropWindow(monitor_id)
        self._windows[monitor_id] = window

    def set_bar_manager(self, bar_manager) -> None:
        self._bar_manager = bar_manager
        for window in self._windows.values():
            window.set_bar_manager(bar_manager)
    def _remove_window(self, monitor_id: int) -> None:
        window = self._windows.pop(monitor_id, None)
        if window:
            window.destroy()
            logger.info(f"WallpaperService: removed drop window for monitor {monitor_id}")

    def _on_monitor_added(self, _display, _monitor) -> None:
        logger.info("WallpaperService: monitor added, resyncing...")
        self._sync_monitors()

    def _on_monitor_removed(self, _display, _monitor) -> None:
        logger.info("WallpaperService: monitor removed, resyncing...")
        self._sync_monitors()
    
