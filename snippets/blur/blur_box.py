from functools import partial

from gi.repository import Gtk, GLib

from fabric.widgets.box import Box

from .blur import (
    enable_blur,
    disable_blur,
    free_blur,
    has_wl_surface,
    set_blur_regions,
)
from .region_trace import Rect, trace_widget


class _SurfaceBlur:
    _instances: dict[int, "_SurfaceBlur"] = {}

    @classmethod
    def acquire(cls, window: Gtk.Window) -> "_SurfaceBlur | None":
        key = id(window)
        instance = cls._instances.get(key)
        if instance is None:
            ctx = enable_blur(window)
            if not ctx:
                return None
            instance = cls(key, window, ctx)
            cls._instances[key] = instance
        instance._users += 1
        return instance

    def __init__(self, key: int, window: Gtk.Window, ctx):
        self._key    = key
        self._window = window
        self._ctx    = ctx
        self._users  = 0
        self._parts: dict[int, list[tuple[int, int, int, int]]] = {}
        self._last: list[tuple[int, int, int, int]] = []
 
        disable_blur(ctx)

    def submit(self, owner, rects: list[Rect]):
        self._parts[id(owner)] = [(r.x, r.y, r.width, r.height) for r in rects]
        self._flush()

    def withdraw(self, owner):
        if self._parts.pop(id(owner), None) is not None:
            self._flush()

    def release(self, owner):
        self.withdraw(owner)
        self._users -= 1
        if self._users > 0:
            return

        _SurfaceBlur._instances.pop(self._key, None)
        if self._ctx:
            if has_wl_surface(self._window):
                disable_blur(self._ctx)
            free_blur(self._ctx)
            self._ctx = None

    def _flush(self):
        if not self._ctx or not has_wl_surface(self._window):
            return

        combined = [rect for part in self._parts.values() for rect in part]
        if combined == self._last:
            return
        self._last = combined

        if combined:
            set_blur_regions(self._ctx, combined)
        else:
            disable_blur(self._ctx)


def _find_reveals(widget, found: list | None = None) -> list:
    """Every descendant that reports the regions it renders."""
    if found is None:
        found = []
    if hasattr(widget, "region_cb"):
        found.append(widget)
        return found          # a reveal draws its whole subtree itself
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            _find_reveals(child, found)
    return found


class _Source:
    __slots__ = ("widget", "rects", "callback")

    def __init__(self, widget, callback=None):
        self.widget   = widget
        self.rects: list[Rect] = []
        self.callback = callback


class BlurBox(Box):
    def __init__(
        self,
        child: Gtk.Widget | None = None,
        reveal: Gtk.Widget | None = None,
        enabled: bool = True,
        inset: int = 0,
        min_alpha: int = 8,
        relative_alpha: float = 0.5,
        step: int = 1,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._content        = child
        self._pinned_reveal  = reveal
        self._enabled        = enabled
        self._inset          = inset
        self._min_alpha      = min_alpha
        self._relative_alpha = relative_alpha
        self._step           = max(1, step)

        self._surface: _SurfaceBlur | None = None
        self._sources: dict[int, _Source] = {}
        self._refresh_id = 0
        self._attach_id  = 0

        if child is not None:
            self.add(child)
            child.show()

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)
        self.connect("size-allocate", lambda *_: self.queue_refresh())

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        if value == self._enabled:
            return
        self._enabled = value
        if value:
            self._queue_attach()
        else:
            self._detach()

    def queue_refresh(self):
        if self._refresh_id or not self._enabled:
            return
        self._refresh_id = GLib.idle_add(
            self._idle_refresh, priority=GLib.PRIORITY_LOW
        )

    def refresh(self):
        """Re-trace every source that is not currently being animated."""
        if self._surface is None:
            return

        self._sync_sources()
        for source in self._sources.values():
            if getattr(source.widget, "animating", False):
                continue
            if not source.widget.get_mapped():
                source.rects = []
                continue
            source.rects = self._to_window(
                source.widget, self._static_regions(source.widget)
            )
        self._push()

    def _sync_sources(self):
        if self._pinned_reveal is not None:
            found = [self._pinned_reveal]
        else:
            found = _find_reveals(self._content or self)
        if not found:
            found = [self._content or self]

        live = {id(widget): widget for widget in found}

        for key in [k for k in self._sources if k not in live]:
            self._unhook(self._sources.pop(key))

        for key, widget in live.items():
            if key in self._sources:
                continue
            source = _Source(widget)
            if hasattr(widget, "region_cb"):
                if hasattr(widget, "region_inset"):
                    widget.region_inset = self._inset
                if hasattr(widget, "region_settle_step"):
                    widget.region_settle_step = self._step
                source.callback = partial(self._on_source_regions, key)
                widget.region_cb = source.callback
            self._sources[key] = source

    def _unhook(self, source: _Source):
        if source.callback is None:
            return
        if getattr(source.widget, "region_cb", None) is source.callback:
            source.widget.region_cb = None

    def _static_regions(self, widget) -> list[Rect]:
        settled = getattr(widget, "settled_regions", None)
        if settled is not None:
            return settled()
        return trace_widget(
            widget,
            min_alpha=self._min_alpha,
            relative_alpha=self._relative_alpha,
            inset=self._inset,
            step=self._step,
        )

    def _on_source_regions(self, key: int, rects: list[Rect]):
        source = self._sources.get(key)
        if source is None:
            return
        source.rects = self._to_window(source.widget, rects)
        self._push()

    def _to_window(self, widget, rects: list[Rect]) -> list[Rect]:
        if not rects:
            return []
        offset = widget.translate_coordinates(self.get_toplevel(), 0, 0)
        if offset is None:
            return []
        dx, dy = offset
        return [Rect(r.x + dx, r.y + dy, r.width, r.height) for r in rects]

    def _push(self):
        if self._surface is None:
            return
        self._surface.submit(
            self, [rect for s in self._sources.values() for rect in s.rects]
        )


    def _on_map(self, *_):
        if self._enabled:
            self._queue_attach()

    def _on_unmap(self, *_):
        self._detach()

    def _queue_attach(self, delay: int = 0):
        if self._attach_id or self._surface is not None:
            return
        self._attach_id = (
            GLib.timeout_add(delay, self._on_attach_tick)
            if delay
            else GLib.idle_add(self._on_attach_tick)
        )

    def _on_attach_tick(self):
        self._attach_id = 0
        if self._enabled and self.get_mapped() and not self._try_attach():
            self._queue_attach(delay=16)
        return GLib.SOURCE_REMOVE

    def _try_attach(self) -> bool:
        if self._surface is not None:
            return True

        window = self.get_toplevel()
        if not isinstance(window, Gtk.Window) or not window.get_realized():
            return False
        if not has_wl_surface(window):
            return False

        self._surface = _SurfaceBlur.acquire(window)
        if self._surface is None:
            return True

        self._sync_sources()
        self.queue_refresh()
        return True

    def _detach(self):
        if self._attach_id:
            GLib.source_remove(self._attach_id)
            self._attach_id = 0
        if self._refresh_id:
            GLib.source_remove(self._refresh_id)
            self._refresh_id = 0

        for source in self._sources.values():
            self._unhook(source)
        self._sources.clear()

        if self._surface is not None:
            self._surface.release(self)
            self._surface = None

    def _idle_refresh(self):
        self._refresh_id = 0
        self.refresh()
        return GLib.SOURCE_REMOVE
