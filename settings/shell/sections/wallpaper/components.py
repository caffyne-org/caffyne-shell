import os
import threading
import weakref

from concurrent.futures import Future, ThreadPoolExecutor

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk

from fabric.utils import monitor_file
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from snippets import ClippingBox
from services.themes import wp
from user_options import user_options
from utils.wallpaper_cache import (
    SUPPORTED_EXTS,
    cached_image,
    list_wallpapers,
    load_pixbuf,
)
CARD_WIDTH   = 280
CARD_HEIGHT  = 158
CARD_VARIANT = "wallpaper-cards"

HEADER_WIDTH   = 560
HEADER_HEIGHT  = 315
HEADER_VARIANT = "wallpaper-header"


class WallpaperCard(Button):

    def __init__(self, path: str, on_select):
        self._path            = path
        self._loaded          = False
        self._load_generation = 0
        self._future: Future | None = None

        self.image = Image()
        self.preview = ClippingBox(
            style_classes=["wallpaper-card-preview"],
            children=self.image,
        )
        self.preview.set_size_request(CARD_WIDTH, CARD_HEIGHT)

        super().__init__(
            style_classes=["wallpaper-card"],
            h_expand=False,
            h_align="center",
            v_expand=False,
            v_align="center",
            child=self.preview,
            on_clicked=lambda _: on_select(self),
            tooltip_text=os.path.basename(path),
        )

    @property
    def path(self) -> str:
        return self._path

    def load(self, executor: ThreadPoolExecutor) -> None:
        if self._loaded:
            return
        self._loaded          = True
        self._load_generation += 1

        path = self._path
        gen  = self._load_generation
        ref  = weakref.ref(self)

        def work():
            cache_path = cached_image(path, CARD_VARIANT, CARD_WIDTH, CARD_HEIGHT)
            if cache_path is None:
                return
            pixbuf = load_pixbuf(cache_path)
            if pixbuf is None:
                return

            def apply():
                card = ref()
                if card is None or gen != card._load_generation:
                    return GLib.SOURCE_REMOVE
                card.image.set_from_pixbuf(pixbuf)
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

    def set_active(self, active: bool) -> None:
        if active:
            self.add_style_class("active")
        else:
            self.remove_style_class("active")


class WallpaperPreview(Box):
    def __init__(self, **kwargs):
        self._generation          = 0
        self._future: Future | None = None
        self._executor            = ThreadPoolExecutor(max_workers=1)

        self.image = Image()
        self.frame = ClippingBox(
            style_classes=["wallpaper-preview"],
            children=self.image,
        )
        self.frame.set_size_request(HEADER_WIDTH, HEADER_HEIGHT)

        # self.caption = Label(
        #     label="",
        #     h_align="start",
        #     style_classes=["wallpaper-preview-caption"],
        # )

        super().__init__(
            orientation="v",
            spacing=8,
            h_align="center",
            children=[self.frame],
            **kwargs,
        )

        self.connect("destroy", lambda *_: self._cleanup())

    def show_path(self, path: str | None) -> None:
        self._cancel()
        self._generation += 1

        if not path or not os.path.isfile(path):
            self.image.set_from_pixbuf(None)
            # self.caption.set_label("No wallpaper set")
            return

        # self.caption.set_label(os.path.basename(path))

        gen = self._generation
        ref = weakref.ref(self)

        def work():
            cache_path = cached_image(
                path, HEADER_VARIANT, HEADER_WIDTH, HEADER_HEIGHT, quality=90
            )
            if cache_path is None:
                return
            pixbuf = load_pixbuf(cache_path)
            if pixbuf is None:
                return

            def apply():
                preview = ref()
                if preview is None or gen != preview._generation:
                    return GLib.SOURCE_REMOVE
                preview.image.set_from_pixbuf(pixbuf)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(apply)

        self._future = self._executor.submit(work)

    def _cancel(self) -> None:
        if self._future is not None:
            self._future.cancel()
            self._future = None

    def _cleanup(self) -> None:
        self._cancel()
        self._generation += 1
        self.image.set_from_pixbuf(None)
        self._executor.shutdown(wait=False)


class WallpaperBrowser(Box):    
    def __init__(self, preview: WallpaperPreview, **kwargs):
        super().__init__(orientation="v", spacing=12, **kwargs)

        self._preview      = preview
        self._executor     = ThreadPoolExecutor(max_workers=1)
        self._active_card: WallpaperCard | None = None
        self._monitor      = None
        self._folder       = user_options.wallpaper.folder

        self._scan_generation = 0

        self.title_label = Label(
            label="Wallpapers", h_align="start", style_classes=["pack-section-title"]
        )
        self.status_label = Label(label="Loading wallpapers...", h_align="start")
        self.add(Box(
            orientation="h",
            spacing=12,
            children=[self.title_label, self.status_label],
        ))

        self.grid = Gtk.FlowBox()
        self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.grid.set_column_spacing(12)
        self.grid.set_row_spacing(12)
        self.add(self.grid)

        self.connect("map", lambda *_: self._on_mapped())
        self.connect("unmap", lambda *_: self._unload_all())
        self.connect("destroy", lambda *_: self._cleanup())

        wp.connect("wallpaper-changed", self._on_wallpaper_changed)

        self._load_wallpapers()

    def set_folder(self, folder: str) -> None:
        """Point the grid at a different directory and rebuild it."""
        if folder == self._folder:
            return
        self._folder = folder
        self._clear_grid()
        self.status_label.set_label("Loading wallpapers...")
        self._load_wallpapers()

    def _clear_grid(self) -> None:
        self._scan_generation += 1
        self._active_card = None
        if self._monitor is not None:
            self._monitor.cancel()
            self._monitor = None
        for card in self._cards():
            card.unload()
        for child in self.grid.get_children():
            child.destroy()

    def _load_wallpapers(self) -> None:
        folder = self._folder
        gen    = self._scan_generation

        def scan():
            paths = list_wallpapers(folder)

            def apply():
                if gen != self._scan_generation:
                    return GLib.SOURCE_REMOVE
                for path in paths:
                    self.grid.add(WallpaperCard(path, self._on_card_clicked))
                self.grid.show_all()
                self._update_status()
                self._restore_active(wp.wallpaper_path)
                if self.get_mapped():
                    self._load_all()
                if self._monitor is None and os.path.isdir(folder):
                    self._monitor = monitor_file(folder)
                    self._monitor.connect("changed", self._on_dir_changed)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(apply)

        threading.Thread(target=scan, daemon=True).start()

    def _cards(self) -> list[WallpaperCard]:
        # FlowBox wraps every child in a FlowBoxChild.
        cards = []
        for child in self.grid.get_children():
            inner = child.get_child() if isinstance(child, Gtk.FlowBoxChild) else child
            if isinstance(inner, WallpaperCard):
                cards.append(inner)
        return cards

    def _update_status(self) -> None:
        count = len(self._cards())
        self.status_label.set_label(
            f"({count} wallpaper{'s' if count != 1 else ''})"
        )

    def _on_mapped(self) -> None:
        self._restore_active(wp.wallpaper_path)
        if self._active_card is None:
            self._preview.show_path(wp.wallpaper_path or None)
        self._load_all()

    def _load_all(self) -> None:
        for card in self._cards():
            card.load(self._executor)

    def _unload_all(self) -> None:
        for card in self._cards():
            card.unload()

    def _cleanup(self) -> None:
        self._unload_all()
        if self._monitor is not None:
            self._monitor.cancel()
            self._monitor = None
        self._executor.shutdown(wait=False)

    def _on_card_clicked(self, card: WallpaperCard) -> None:
        self._set_active(card)
        wp.set_wallpaper(card.path)

    def _set_active(self, card: WallpaperCard | None) -> None:
        if self._active_card is not None:
            self._active_card.set_active(False)
        self._active_card = card
        if card is not None:
            card.set_active(True)
            self._preview.show_path(card.path)

    def _restore_active(self, path: str | None) -> None:
        if not path:
            return
        for card in self._cards():
            if card.path == path:
                self._set_active(card)
                return
        if self._active_card is not None:
            self._active_card.set_active(False)
            self._active_card = None

    def _on_wallpaper_changed(self, _service, path: str) -> None:
        def apply():
            self._restore_active(path)
            if self._active_card is None:
                self._preview.show_path(path)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(apply)

    def _on_dir_changed(self, _monitor, file, _other_file, event_type) -> None:
        path = file.get_path()
        if not path or not path.lower().endswith(SUPPORTED_EXTS):
            return
        if event_type == Gio.FileMonitorEvent.CREATED:
            GLib.idle_add(self._add_card, path)
        elif event_type == Gio.FileMonitorEvent.DELETED:
            GLib.idle_add(self._remove_card, path)

    def _add_card(self, path: str) -> bool:
        cards = self._cards()
        if any(card.path == path for card in cards):
            return GLib.SOURCE_REMOVE

        card  = WallpaperCard(path, self._on_card_clicked)
        index = sorted([c.path for c in cards] + [path]).index(path)
        self.grid.insert(card, index)
        card.show_all()
        self._update_status()
        if self.get_mapped():
            card.load(self._executor)
        if path == wp.wallpaper_path:
            self._set_active(card)
        return GLib.SOURCE_REMOVE

    def _remove_card(self, path: str) -> bool:
        for card in self._cards():
            if card.path != path:
                continue
            if self._active_card is card:
                self._active_card = None
            card.unload()
            parent = card.get_parent()
            (parent if isinstance(parent, Gtk.FlowBoxChild) else card).destroy()
            self._update_status()
            break
        return GLib.SOURCE_REMOVE
