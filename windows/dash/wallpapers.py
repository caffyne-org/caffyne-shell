import os
import weakref
import threading

from concurrent.futures import ThreadPoolExecutor, Future

from fabric.utils import monitor_file
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.centerbox import CenterBox
from gi.repository import GLib, Gio
from snippets import Icon, ClippingScrolledWindow, ClippingBox
from services.themes import wp
from user_options import user_options
from utils.wallpaper_cache import (
    SUPPORTED_EXTS,
    cached_image,
    list_wallpapers,
    load_pixbuf,
)

THUMBNAIL_SIZE = 174

PREVIEW_WIDTH  = 918
PREVIEW_HEIGHT = 546

THUMB_VARIANT   = "thumbnails"
PREVIEW_VARIANT = "previews"

def _generate_thumb_to_cache(file_path: str, size: int):
    return cached_image(file_path, THUMB_VARIANT, size, size)

def _generate_preview_to_cache(file_path: str):
    return cached_image(
        file_path, PREVIEW_VARIANT, PREVIEW_WIDTH, PREVIEW_HEIGHT,
        crop=False, quality=88,
    )

def _load_pixbuf_from_path(cache_path):
    return load_pixbuf(cache_path)

class SelectorHeader(CenterBox):
    def __init__(self, h_stack, v_stack, left_icon_name, right_icon_name, h_target, v_target):
        super().__init__(
            h_expand=False,
            halign="center",
            start_children=Button(
                style_classes=["applet-misc-button"],
                child=Icon(icon_name=left_icon_name),
                on_pressed=lambda _: v_stack.set_visible_child_name(v_target),
            ),
            end_children=Button(
                style_classes=["applet-misc-button"],
                child=Icon(icon_name=right_icon_name),
                on_pressed=lambda _: h_stack.set_visible_child_name(h_target),
            ),
        )

class WallpaperThumb(Button):
    """
    Memory contract:
    - The executor work() closure captures only: path (str), size (int),
      generation (int), and a weakref to self.
    - self is never captured directly — if the widget is destroyed or unloaded
      before the job finishes, the weakref returns None and the result is dropped.
    - _future is tracked so unload() can cancel() before PIL even starts,
      avoiding wasted decode work on off-screen thumbs.
    """

    def __init__(self, path: str, on_select):
        self._path            = path
        self._loaded          = False
        self._load_generation = 0
        self._future: Future | None = None

        self.image = Image()
        self.box = ClippingBox(
            style_classes=["dash-grid-selector-preview"],
            children=self.image,
        )
        super().__init__(
            style_classes=["wallpaper-thumb"],
            child=self.box,
            on_clicked=lambda _: on_select(self),
        )
        self.set_size_request(THUMBNAIL_SIZE, THUMBNAIL_SIZE)

    def load(self, executor: ThreadPoolExecutor) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._load_generation += 1

        path = self._path
        gen  = self._load_generation
        ref  = weakref.ref(self)

        def work():
            cache_path = _generate_thumb_to_cache(path, THUMBNAIL_SIZE)
            if cache_path is None:
                return
            pixbuf = _load_pixbuf_from_path(cache_path)
            if pixbuf is None:
                return

            def apply():
                thumb = ref()
                if thumb is None:
                    return GLib.SOURCE_REMOVE
                if gen != thumb._load_generation:
                    return GLib.SOURCE_REMOVE
                thumb.image.set_from_pixbuf(pixbuf)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(apply)

        self._future = executor.submit(work)

    def unload(self) -> None:
        self._loaded          = False
        self._load_generation += 1

        if self._future is not None:
            self._future.cancel()
            self._future = None

        self.image.set_from_pixbuf(None)

    @property
    def path(self) -> str:
        return self._path

    def set_active(self, active: bool) -> None:
        if active:
            self.add_style_class("active")
        else:
            self.remove_style_class("active")

class DashSelectorPage(Box):
    def __init__(self):
        self._preview_box = ClippingBox(
            style_classes=["dash-grid-selector-preview"],
            orientation="v",
            h_align="center",
            v_align="start",
            h_expand=False,
        )
        self._thumb_strip = Box(
            orientation="v",
            spacing=12,
            style_classes=["wallpaper-thumb-strip"],
        )
        self._scroll = ClippingScrolledWindow(
            v_expand=True,
            style_classes=["grid-selector-thumb-scroll"],
            max_content_size=(174, 630),
            fade_distance=60,
            child=self._thumb_strip,
            overlay_scroll=True,
            kinetic_scroll=True,
        )
        super().__init__(
            orientation="v",
            v_align="start",
            h_align="center",
            h_expand=True,
            v_expand=True,
            spacing=12,
            children=[
                Box(
                    orientation="h",
                    spacing=12,
                    h_expand=True,
                    v_expand=True,
                    children=[self._preview_box, self._scroll],
                ),
            ],
        )

class DashWallpaperPage(DashSelectorPage):
    """
    Memory contract
    - All preview and thumb loads use weakrefs + generation counters.
    - No closure ever captures self directly.
    - In-flight futures are cancelled on hide/unload so no stale pixbufs
      can land on the main thread after the page is hidden.
    """

    def __init__(self):
        super().__init__()

        self._executor                    = ThreadPoolExecutor(max_workers=1)
        self._active_thumb: WallpaperThumb | None = None
        self._preview_generation          = 0
        self._preview_future: Future | None = None

        self._preview_image = Image()
        self._preview_box.add(self._preview_image)

        self.connect("realize", self._on_realize)
        self._load_wallpapers()

        if wp.wallpaper_path:
            self._restore_active(wp.wallpaper_path)

        wp.connect("wallpaper-changed", self._on_wallpaper_changed)

    def _on_wallpaper_changed(self, service, path: str) -> None:
        GLib.idle_add(self._refresh_and_select, path)

    def _refresh_and_select(self, path: str) -> None:
        if self.is_visible():
            self._restore_active(path)
            self._update_preview(path)

    def _on_realize(self, *_) -> None:
        h_stack = self.get_parent()
        v_stack = h_stack.get_parent() if h_stack else None

        if v_stack:
            v_stack.connect("notify::visible-child", self._on_v_stack_switch)
        if h_stack:
            h_stack.connect("notify::visible-child", self._on_h_stack_switch)

        toplevel = self.get_toplevel()
        if toplevel:
            toplevel.connect("destroy", lambda *_: self._cleanup())

    def _on_v_stack_switch(self, stack, *_) -> None:
        if stack.get_visible_child() == self.get_parent():
            self._on_became_visible()
        else:
            self._on_became_hidden()

    def _on_h_stack_switch(self, stack, *_) -> None:
        if stack.get_visible_child() == self:
            self._on_became_visible()
        else:
            self._on_became_hidden()

    def _on_became_visible(self) -> None:
        if not self._thumb_strip.get_children():
            self._load_wallpapers()
            if wp.wallpaper_path:
                self._restore_active(wp.wallpaper_path)
        else:
            GLib.idle_add(self._on_scroll_changed, self._scroll.get_vadjustment())
            if self._active_thumb:
                self._update_preview(self._active_thumb.path)
            elif wp.wallpaper_path:
                self._update_preview(wp.wallpaper_path)

    def _on_became_hidden(self) -> None:
        self._unload_all_thumbs()

    def _cleanup(self) -> None:
        self._cancel_preview()
        self._unload_all_thumbs()
        self._preview_image.set_from_pixbuf(None)
        self._executor.shutdown(wait=False)
        if hasattr(self, "_walls_monitor"):
            self._walls_monitor.cancel()

    def _cancel_preview(self) -> None:
        if self._preview_future is not None:
            self._preview_future.cancel()
            self._preview_future = None

    def _unload_all_thumbs(self) -> None:
        self._cancel_preview()
        for thumb in self._thumb_strip.get_children():
            if isinstance(thumb, WallpaperThumb):
                thumb.unload()
        self._active_thumb = None
        self._preview_image.set_from_pixbuf(None)

    def _load_wallpapers(self) -> None:
        walls_dir = user_options.wallpaper.folder
        if not os.path.isdir(walls_dir):
            return

        def load():
            paths = list_wallpapers(walls_dir)
            def apply():
                for path in paths:
                    thumb = WallpaperThumb(path, self._on_thumb_clicked)
                    self._thumb_strip.add(thumb)
                self._thumb_strip.show_all()
                adj = self._scroll.get_vadjustment()
                adj.connect("value-changed", self._on_scroll_changed)
                GLib.idle_add(self._on_scroll_changed, adj)
                self._walls_monitor = monitor_file(walls_dir)
                self._walls_monitor.connect("changed", self._on_dir_changed)
            GLib.idle_add(apply)

        threading.Thread(target=load, daemon=True).start()

    def _on_dir_changed(self, monitor, file, other_file, event_type) -> None:
        path = file.get_path()
        if not path.lower().endswith(SUPPORTED_EXTS):
            return
        if event_type == Gio.FileMonitorEvent.CREATED:
            GLib.idle_add(self._add_thumb, path)
        elif event_type == Gio.FileMonitorEvent.DELETED:
            GLib.idle_add(self._remove_thumb, path)

    def _on_scroll_changed(self, adj) -> None:
        visible_start = adj.get_value()
        visible_end   = visible_start + adj.get_page_size()
        buffer        = THUMBNAIL_SIZE * 2

        y = 0
        for thumb in self._thumb_strip.get_children():
            if not isinstance(thumb, WallpaperThumb):
                continue
            in_view = (
                y + THUMBNAIL_SIZE >= visible_start - buffer and
                y                  <= visible_end   + buffer
            )
            if in_view:
                thumb.load(self._executor)
            else:
                thumb.unload()
            y += THUMBNAIL_SIZE + 8

    def _on_thumb_clicked(self, thumb: WallpaperThumb) -> None:
        self._set_active(thumb)
        wp.set_wallpaper(thumb.path)

    def _set_active(self, thumb: WallpaperThumb) -> None:
        if self._active_thumb:
            self._active_thumb.set_active(False)
        self._active_thumb = thumb
        thumb.set_active(True)
        self._update_preview(thumb.path)

    def _restore_active(self, path: str) -> None:
        self._update_preview(path)
        for thumb in self._thumb_strip.get_children():
            if isinstance(thumb, WallpaperThumb) and thumb.path == path:
                if self._active_thumb:
                    self._active_thumb.set_active(False)
                self._active_thumb = thumb
                thumb.set_active(True)
                return

    def _update_preview(self, path: str | None) -> None:
        self._cancel_preview()
        self._preview_generation += 1

        if path is None:
            return

        gen = self._preview_generation
        ref = weakref.ref(self)

        def load():
            cache_path = _generate_preview_to_cache(path)
            if cache_path is None:
                return
            pixbuf = _load_pixbuf_from_path(cache_path)
            if pixbuf is None:
                return

            def apply():
                page = ref()
                if page is None or gen != page._preview_generation:

                    return GLib.SOURCE_REMOVE
                page._preview_image.set_from_pixbuf(pixbuf)

                return GLib.SOURCE_REMOVE

            GLib.idle_add(apply)

        self._preview_future = self._executor.submit(load)

    def _add_thumb(self, path: str) -> None:
        existing = [
            t.path for t in self._thumb_strip.get_children()
            if isinstance(t, WallpaperThumb)
        ]
        if path in existing:
            return
        thumb     = WallpaperThumb(path, self._on_thumb_clicked)
        all_paths = sorted(existing + [path])
        index     = all_paths.index(path)
        self._thumb_strip.pack_start(thumb, False, False, 0)
        self._thumb_strip.reorder_child(thumb, index)
        thumb.show_all()
        thumb.load(self._executor)

    def _remove_thumb(self, path: str) -> None:
        for thumb in self._thumb_strip.get_children():
            if isinstance(thumb, WallpaperThumb) and thumb.path == path:
                if self._active_thumb == thumb:
                    self._active_thumb = None
                    self._preview_area.set_style("background-image: none;")
                thumb.destroy()
                break