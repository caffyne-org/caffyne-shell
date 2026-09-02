from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.eventbox import EventBox
from ..launcher import get_usage_count, load_usage, increment_usage
from thefuzz import process, fuzz
from utils.dispatch import dispatch_app
from fabric.utils import get_desktop_applications, DesktopApp
from .components import DashPage
from desktop_applets import DESKTOP_APPLET_SIZES, DESKTOP_APPLET_WIDGETS
from gi.repository import Gdk, Gtk, GLib
from user_options import user_options
from services.singletons import plugins
import threading

COLUMNS = 6
_TARGET = Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)


class DashLauncherAppItem(Button):
    def __init__(self, app: DesktopApp, launcher):
        self._app = app
        self._launcher = launcher
        self.box = Box(
            orientation="v",
            spacing=18,
            h_expand=False,
            h_align="center",
            v_expand=True,
            v_align="center",
            children=[
                Image(v_expand=True, v_align="end", icon_name=app.icon_name, icon_size=52),
                Label(
                    v_expand=True, v_align="start",
                    label=app.display_name or "",
                    h_align="center",
                    ellipsization="end",
                    max_chars_width=10,
                    style="font-size: 14px;",
                ),
            ],
        )
        super().__init__(
            style_classes=["dash-launcher-app"],
            on_clicked=lambda *_: self.launch(),
            child=self.box,
        )
    #     self.connect("enter-notify-event", self._on_enter)
    #     self.connect("leave-notify-event", self._on_leave)
    #     self.connect("button-press-event", self._on_press)
    #     self.connect("button-release-event", self._on_release)
    #     self.connect("focus-in-event", self._on_focus_in)
    #     self.connect("focus-out-event", self._on_focus_out)

    # def _on_enter(self, *_):
    #     self.box.add_style_class("hover")

    # def _on_leave(self, *_):
    #     self.box.remove_style_class("hover")
    #     self.box.remove_style_class("active")

    # def _on_press(self, *_):
    #     self.box.add_style_class("active")

    # def _on_release(self, *_):
    #     self.box.remove_style_class("active")

    # def _on_focus_in(self, *_):
    #     self.box.add_style_class("focus")

    # def _on_focus_out(self, *_):
    #     self.box.remove_style_class("focus")

    def launch(self):
        increment_usage(self._app)
        dispatch_app(self._app)
        self._launcher.toggle()


class LauncherDesktopAppletItem(Box):
    def __init__(self, key: str, applet_widget: Gtk.Widget, on_remove: callable,
                 on_reorder_begin: callable = None, on_reorder_end: callable = None):
        self._key = key
        self._on_remove = on_remove
        self._on_reorder_begin = on_reorder_begin
        self._on_reorder_end = on_reorder_end
        cols = DESKTOP_APPLET_SIZES.get(key, 1)

        self._inner = EventBox(
            style_classes=["launcher-desktop-applet", f"launcher-desktop-applet-{cols}col"],
        )
        self._inner.add(applet_widget)
        self._inner.connect("button-press-event", self._on_button_press)

        super().__init__(
            orientation="h",
            style_classes=["launcher-desktop-applet-wrapper"],
        )
        self.add(self._inner)

        self.col_span = cols

        self._inner.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [_TARGET],
            Gdk.DragAction.MOVE,
        )
        self._inner.connect("drag-begin",    self._on_drag_begin)
        self._inner.connect("drag-data-get", self._on_drag_data_get)
        self._inner.connect("drag-end",      self._on_drag_end)
        self._inner.connect("drag-failed",   self._on_drag_failed)

    def _on_button_press(self, widget, event: Gdk.EventButton):
        if event.button == 3:
            self._show_context_menu(event)
            return True
        return False

    def _show_context_menu(self, event: Gdk.EventButton):
        menu = Gtk.Menu()
        remove_item = Gtk.MenuItem(label="Remove")
        remove_item.connect("activate", lambda _: self._on_remove(self._key))
        menu.append(remove_item)
        menu.show_all()
        menu.popup_at_pointer(event)

    def _on_drag_begin(self, widget, ctx):
        import bar as _bar_module
        _bar_module._dragging_key = self._key
        self.set_opacity(0.0)
        if self._on_reorder_begin:
            self._on_reorder_begin(self._key)

    def _on_drag_data_get(self, widget, ctx, data_obj, info, time):
        data_obj.set_text(f"applet:{self._key}", -1)

    def _on_drag_end(self, widget, ctx):
        import bar as _bar_module
        _bar_module._dragging_key = None
        self.set_opacity(1.0)
        if self._on_reorder_end:
            self._on_reorder_end()

    def _on_drag_failed(self, widget, ctx, result):
        import bar as _bar_module
        _bar_module._dragging_key = None
        self.set_opacity(1.0)
        if self._on_reorder_end:
            self._on_reorder_end()
        return True

    @property
    def key(self) -> str:
        return self._key


class LauncherDropPlaceholder(Box):
    def __init__(self, col_span: int = 1):
        super().__init__(
            style_classes=["launcher-drop-placeholder", f"launcher-drop-placeholder-{col_span}col"],
        )
        self.col_span = col_span


def compute_grid_layout(
    applet_items: list,
    app_items: list,
    dragging_key: str | None = None,
    placeholder_slot: int | None = None,
) -> list[tuple]:
    ph_span = DESKTOP_APPLET_SIZES.get(dragging_key, 1) if dragging_key else 1

    applet_cells: dict[int, object] = {}
    for item in applet_items:
        if item.key == dragging_key:
            continue
        s = item._slot
        for offset in range(item.col_span):
            applet_cells[s + offset] = item if offset == 0 else None

    ph_cells: dict[int, bool] = {}
    if placeholder_slot is not None:
        for offset in range(ph_span):
            ph_cells[placeholder_slot + offset] = (offset == 0)

    app_iter = iter(app_items)
    app_exhausted = False
    placed_applets: set[str] = set()
    remaining_applets = [i for i in applet_items if i.key != dragging_key]

    result: list[tuple] = []
    ci = 0
    col_cursor = 0
    row_cursor = 0

    def place(widget, span):
        nonlocal col_cursor, row_cursor
        if widget is not None:
            result.append((widget, col_cursor, row_cursor, span))
        col_cursor += span
        if col_cursor >= COLUMNS:
            col_cursor = 0
            row_cursor += 1

    def fill_to_fit(span):
        nonlocal col_cursor, row_cursor, app_exhausted, ci
        while col_cursor + span > COLUMNS:
            if not app_exhausted:
                try:
                    app = next(app_iter)
                    place(app, 1)
                except StopIteration:
                    app_exhausted = True
                    place(None, 1)
            else:
                place(None, 1)
            ci += 1

    while True:
        if ci in applet_cells:
            item = applet_cells[ci]
            if item is not None and item.key not in placed_applets:
                fill_to_fit(item.col_span)
                place(item, item.col_span)
                placed_applets.add(item.key)
                ci += item.col_span
            else:
                ci += 1
                continue
        elif ci in ph_cells:
            if ph_cells[ci]:
                fill_to_fit(ph_span)
                result.append(("__placeholder__", col_cursor, row_cursor, ph_span))
                col_cursor += ph_span
                if col_cursor >= COLUMNS:
                    col_cursor = 0
                    row_cursor += 1
                ci += ph_span
            else:
                ci += 1
                continue
        else:
            if not app_exhausted:
                try:
                    app = next(app_iter)
                    place(app, 1)
                except StopIteration:
                    app_exhausted = True
                    place(None, 1)
            else:
                place(None, 1)
            ci += 1

        all_applets_placed = all(i.key in placed_applets for i in remaining_applets)
        if app_exhausted and all_applets_placed and placeholder_slot is None:
            break
        if (
            placeholder_slot is not None
            and ci > placeholder_slot + ph_span
            and app_exhausted
            and all_applets_placed
        ):
            break
        if ci > 10000:
            break

    return result


class HybridGrid(Gtk.Grid):
    def __init__(self, on_placeholder_changed=None, on_applet_dropped=None):
        super().__init__()
        self.set_column_homogeneous(True)
        self.set_row_homogeneous(True)
        self.set_column_spacing(12)
        self.set_row_spacing(12)

        self._placeholder_slot: int | None = None
        self._drop_pending: bool = False
        self._on_placeholder_changed = on_placeholder_changed
        self._on_applet_dropped = on_applet_dropped
        self._grid_cache: dict[str, Gtk.Widget] = {}
        self._grid_positions: dict[str, tuple[int, int, int]] = {}
        self.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [_TARGET],
            Gdk.DragAction.MOVE,
        )
        self.connect("drag-motion", self._on_drag_motion)
        self.connect("drag-leave",  self._on_drag_leave)
        self.connect("drag-data-received", self._on_drag_received)

    def layout(
        self,
        applet_items: list,
        app_items: list,
        dragging_key: str | None = None,
        placeholder_slot: int | None = None,
        app_widget_cache: dict | None = None,
    ) -> None:
        ph_span = DESKTOP_APPLET_SIZES.get(dragging_key, 1) if dragging_key else 1
        desired_layout = compute_grid_layout(
            applet_items, app_items, dragging_key, placeholder_slot
        )

        desired: dict[str, tuple] = {}
        for entry in desired_layout:
            widget, col, row, span = entry
            if widget is None:
                continue
            if widget == "__placeholder__":
                cache_key = "__placeholder__"
                existing_ph = self._grid_cache.get(cache_key)
                if existing_ph is None or existing_ph.col_span != ph_span:
                    if existing_ph is not None:
                        self.remove(existing_ph)
                        existing_ph.destroy()
                    existing_ph = LauncherDropPlaceholder(ph_span)
                    self._grid_cache[cache_key] = existing_ph
                desired[cache_key] = (existing_ph, col, row, span)
            elif isinstance(widget, DashLauncherAppItem):
                app_id = widget._app._app.get_id()
                cache_key = f"app:{app_id}"
                desired[cache_key] = (widget, col, row, span)
            elif isinstance(widget, LauncherDesktopAppletItem):
                cache_key = f"applet:{widget.key}"
                desired[cache_key] = (widget, col, row, span)

        current_positions = self._grid_positions
        for key in list(self._grid_cache):
            if key not in desired:
                widget = self._grid_cache.pop(key)
                self._grid_positions.pop(key, None)  # ← clean up
                self.remove(widget)
                if isinstance(widget, LauncherDropPlaceholder):
                    widget.destroy()

        for key, (widget, col, row, span) in desired.items():
            self._grid_cache[key] = widget
            if key in current_positions:
                old_col, old_row, old_span = current_positions[key]
                if (old_col, old_row, old_span) == (col, row, span):
                    continue
                self.remove(widget)
            self.attach(widget, col, row, span, 1)
            self._grid_positions[key] = (col, row, span)
            widget.show_all()

    def clear_all(self):
        for key, widget in list(self._grid_cache.items()):
            self.remove(widget)
            if isinstance(widget, LauncherDropPlaceholder):
                widget.destroy()
        self._grid_cache.clear()

    def _on_drag_motion(self, widget, ctx, x, y, time):
        import bar as _bar_module
        dragging_key = _bar_module._dragging_key
        if dragging_key is None or dragging_key not in DESKTOP_APPLET_SIZES:
            Gdk.drag_status(ctx, 0, time)
            return True

        slot = self._xy_to_slot(x, y)
        if slot != self._placeholder_slot:
            self._placeholder_slot = slot
            if self._on_placeholder_changed:
                self._on_placeholder_changed(slot, dragging_key)

        Gdk.drag_status(ctx, Gdk.DragAction.MOVE, time)
        return True

    def _on_drag_leave(self, widget, ctx, time):
        self._drop_pending = True
        def _check():
            if self._drop_pending:
                self._drop_pending = False
                self._placeholder_slot = None
                if self._on_placeholder_changed:
                    self._on_placeholder_changed(-1, "")
            return False
        GLib.idle_add(_check)

    def _on_drag_received(self, widget, ctx, x, y, data_obj, info, time):
        self._drop_pending = False
        payload = data_obj.get_text() or ""
        parts = payload.split(":")
        if len(parts) != 2 or parts[0] != "applet":
            Gtk.drag_finish(ctx, False, False, time)
            return
        key = parts[1]
        if key not in DESKTOP_APPLET_SIZES:
            Gtk.drag_finish(ctx, False, False, time)
            return
        if self._placeholder_slot is None:
            Gtk.drag_finish(ctx, False, False, time)
            return
        slot = self._placeholder_slot
        if self._on_applet_dropped:
            self._on_applet_dropped(key, slot)
        Gtk.drag_finish(ctx, True, False, time)

    def _xy_to_slot(self, x: int, y: int) -> int:
        alloc = self.get_allocation()
        cell_w = alloc.width / COLUMNS if alloc.width > 0 else 1
        cell_h = cell_w + self.get_row_spacing()
        col = max(0, min(COLUMNS - 1, int(x / cell_w)))
        row = max(0, int(y / cell_h))
        return row * COLUMNS + col


class DashLauncherPage(DashPage):
    def __init__(self, window):
        self.window = window
        self._all_apps = get_desktop_applications()
        self._search_entry: Entry | None = None
        self._applet_page_ref = None

        self._placed_items: list[LauncherDesktopAppletItem] = []
        self._applet_widget_cache: dict[str, Gtk.Widget] = {}

        self._app_widget_cache: dict[str, DashLauncherAppItem] = {}

        self._rebuild_generation: int = 0
        self._rebuild_pending_id: int | None = None

        self._drag_receive_mode: bool = False
        self._drag_key: str | None = None
        self._placeholder_slot: int | None = None
        self._reorder_mode: bool = False

        super().__init__(grid_children=[])
        self._hybrid_grid = HybridGrid(
            on_placeholder_changed=self._on_placeholder_changed,
            on_applet_dropped=self._on_applet_dropped,
        )

        old_grid = self.grid
        self.scroll.get_child().get_child().remove(old_grid)
        self.scroll.get_child().get_child().add(self._hybrid_grid)
        self._hybrid_grid.show()

        self.connect("realize", self._on_realise)
        self._load_placed_applets()
        self._rebuild()
        plugins.connect("plugin-disabled", self._on_plugin_disabled)

    def _on_plugin_disabled(self, _, name: str) -> None:
        # Remove from placed items if it was dragged into the launcher grid
        if any(i.key == name for i in self._placed_items):
            self._remove_applet(name)
            
    def _load_placed_applets(self) -> None:
        entries = user_options.desktop_applets.get_applets()
        items = []
        seen_keys: set[str] = set()
        for entry in entries:
            key = entry["key"]
            slot = entry["slot"]
            seen_keys.add(key)
            if key not in self._applet_widget_cache:
                cls = DESKTOP_APPLET_WIDGETS.get(key)
                if cls is None:
                    continue
                try:
                    self._applet_widget_cache[key] = cls()
                except Exception as e:
                    print(f"[launcher] failed to build desktop applet {key!r}: {e}")
                    continue
            item = LauncherDesktopAppletItem(
                key=key,
                applet_widget=self._applet_widget_cache[key],
                on_remove=self._remove_applet,
                on_reorder_begin=self._on_reorder_begin,
                on_reorder_end=self._on_reorder_end,
            )
            item._slot = slot
            items.append(item)
        for stale_key in list(self._applet_widget_cache):
            if stale_key not in seen_keys:
                self._applet_widget_cache.pop(stale_key).destroy()
        self._placed_items = items

    def _get_app_widgets(self, apps: list[DesktopApp]) -> list[DashLauncherAppItem]:
        wanted_ids = {a._app.get_id() for a in apps}

        for stale_id in [k for k in self._app_widget_cache if k not in wanted_ids]:
            widget = self._app_widget_cache.pop(stale_id)
            grid_key = f"app:{stale_id}"
            if grid_key not in self._hybrid_grid._grid_cache:
                widget.destroy()

        for app in apps:
            if app._app.get_id() not in self._app_widget_cache:
                self._app_widget_cache[app._app.get_id()] = DashLauncherAppItem(app, self.window)

        return [self._app_widget_cache[a._app.get_id()] for a in apps]

    def _rebuild(self, apps=None, placeholder_slot=None, dragging_key=None, applet_items_override=None):
        if self._rebuild_pending_id is not None:
            GLib.source_remove(self._rebuild_pending_id)
            self._rebuild_pending_id = None

        if apps is None:
            apps = self._sorted_by_usage(self._all_apps)

        self._rebuild_generation += 1
        generation = self._rebuild_generation
        applet_items = applet_items_override if applet_items_override is not None else self._placed_items

        wanted_ids = {a._app.get_id() for a in apps}
        needs_creation = [a for a in apps if a._app.get_id() not in self._app_widget_cache]

        def _build_new_widgets():
            new_widgets = {
                a._app.get_id(): DashLauncherAppItem(a, self.window)
                for a in needs_creation
            }

            def _commit():
                if generation != self._rebuild_generation:
                    for w in new_widgets.values():
                        w.destroy()
                    return
                self._app_widget_cache.update(new_widgets)
                for stale_id in [k for k in self._app_widget_cache if k not in wanted_ids]:
                    widget = self._app_widget_cache.pop(stale_id)
                    if f"app:{stale_id}" not in self._hybrid_grid._grid_cache:
                        widget.destroy()
                app_widgets = [self._app_widget_cache[a._app.get_id()] for a in apps]
                self._hybrid_grid.layout(
                    applet_items=applet_items,
                    app_items=app_widgets,
                    dragging_key=dragging_key,
                    placeholder_slot=placeholder_slot,
                )

            GLib.idle_add(_commit)

        if needs_creation:
            threading.Thread(target=_build_new_widgets, daemon=True).start()
        else:
            app_widgets = [self._app_widget_cache[a._app.get_id()] for a in apps]
            GLib.idle_add(lambda: (
                self._hybrid_grid.layout(
                    applet_items=applet_items,
                    app_items=app_widgets,
                    dragging_key=dragging_key,
                    placeholder_slot=placeholder_slot,
                ) if generation == self._rebuild_generation else None
            ))

    def _rebuild_debounced(
        self,
        apps: list | None = None,
        placeholder_slot: int | None = None,
        dragging_key: str | None = None,
        applet_items_override: list | None = None,
        delay_ms: int = 40,
    ) -> None:
        if self._rebuild_pending_id is not None:
            GLib.source_remove(self._rebuild_pending_id)
            self._rebuild_pending_id = None

        def _fire():
            self._rebuild_pending_id = None
            self._rebuild(apps, placeholder_slot, dragging_key, applet_items_override)
            return False

        self._rebuild_pending_id = GLib.timeout_add(delay_ms, _fire)

    def _on_reorder_begin(self, key: str) -> None:
        self._reorder_mode = True
        self._drag_key = key
        self._placeholder_slot = None
        self._rebuild(dragging_key=key)

    def _on_reorder_end(self) -> None:
        if self._reorder_mode:
            self._reorder_mode = False
            self._drag_key = None
            self._placeholder_slot = None
            self._rebuild()

    def enter_drag_receive_mode(self, key: str) -> None:
        if key not in DESKTOP_APPLET_SIZES:
            return
        self._drag_receive_mode = True
        self._drag_key = key
        self._placeholder_slot = 0
        self._rebuild(placeholder_slot=0, dragging_key=key)

    def exit_drag_receive_mode(self) -> None:
        self._drag_receive_mode = False
        self._drag_key = None
        self._placeholder_slot = None
        self._reorder_mode = False
        self._rebuild()

    def _on_placeholder_changed(self, slot: int, key: str) -> None:
        if slot < 0:
            self._placeholder_slot = None
            self._rebuild_debounced(dragging_key=self._drag_key)
        else:
            self._placeholder_slot = slot
            self._rebuild_debounced(placeholder_slot=slot, dragging_key=self._drag_key or key)

    def _find_free_slot(self, key: str, preferred_slot: int, exclude_key: str | None = None) -> int:
        span = DESKTOP_APPLET_SIZES.get(key, 1)
        occupied: set[int] = set()
        for item in self._placed_items:
            if item.key == exclude_key:
                continue
            item_span = DESKTOP_APPLET_SIZES.get(item.key, 1)
            for offset in range(item_span):
                occupied.add(item._slot + offset)
        slot = preferred_slot
        while True:
            if not any((slot + offset) in occupied for offset in range(span)):
                return slot
            slot += 1

    def _on_applet_dropped(self, key: str, slot: int) -> None:
        if key not in DESKTOP_APPLET_SIZES:
            return

        if self._reorder_mode and user_options.desktop_applets.is_placed(key):
            slot = self._find_free_slot(key, slot, exclude_key=key)
            user_options.desktop_applets.remove(key)
            user_options.desktop_applets.place(key, slot)
            user_options.save()
            for item in self._placed_items:
                if item.key == key:
                    item._slot = slot
                    break
            self._reorder_mode = False
            self._drag_key = None
            self._placeholder_slot = None
            self._rebuild()
            if self._applet_page_ref is not None:
                self._applet_page_ref.on_launcher_applet_changed()
            from utils.sounds import play_sound
            play_sound("widget-placed")
            return

        if user_options.desktop_applets.is_placed(key):
            return

        cls = DESKTOP_APPLET_WIDGETS.get(key)
        if cls is None:
            return
        try:
            applet_widget = cls()
        except Exception as e:
            print(f"[launcher] failed to build desktop applet {key!r}: {e}")
            return

        item = LauncherDesktopAppletItem(
            key=key,
            applet_widget=applet_widget,
            on_remove=self._remove_applet,
            on_reorder_begin=self._on_reorder_begin,
            on_reorder_end=self._on_reorder_end,
        )
        slot = self._find_free_slot(key, slot)
        item._slot = slot
        self._placed_items.append(item)

        user_options.desktop_applets.place(key, slot)
        user_options.save()
        self.exit_drag_receive_mode()

        if self._applet_page_ref is not None:
            self._applet_page_ref.on_launcher_applet_changed()
        from utils.sounds import play_sound
        play_sound("widget-placed")

    def _remove_applet(self, key: str) -> None:
        self._placed_items = [i for i in self._placed_items if i.key != key]
        if key in self._applet_widget_cache:
            self._applet_widget_cache.pop(key).destroy()
        user_options.desktop_applets.remove(key)
        user_options.save()
        self._rebuild()
        if self._applet_page_ref is not None:
            self._applet_page_ref.on_launcher_applet_changed()

    def _attach_search_entry(self, entry: Entry):
        if self._search_entry is entry:
            return
        if self._search_entry is not None:
            try:
                self._search_entry.disconnect_by_func(self._search)
                self._search_entry.disconnect_by_func(self._on_entry_key_press)
            except Exception as e:
                print(f"[launcher] disconnect failed: {e}")
        self._search_entry = entry
        entry.connect("changed", self._search)
        entry.connect("activate", lambda *_: self._launch_first())
        entry.connect("key-press-event", self._on_entry_key_press)

    def _launch_first(self):
        for child in reversed(self._hybrid_grid.get_children()):
            if isinstance(child, DashLauncherAppItem):
                child.launch()
                return

    def _on_entry_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Down:
            best = None
            best_pos = (float("inf"), float("inf"))
            for key, pos in self._hybrid_grid._grid_positions.items():
                if not key.startswith("app:"):
                    continue
                col, row, span = pos
                if (row, col) < best_pos:
                    best_pos = (row, col)
                    best = self._hybrid_grid._grid_cache.get(key)
            
            if best is not None:
                result = best.grab_focus()
                return True
        return False

    def _on_realise(self, *_):
        self.window.connect("notify::visible", self._on_visibility_changed)

    def _on_visibility_changed(self, *_):
        if not self.window.get_visible():
            self._all_apps = get_desktop_applications()
            if self._search_entry:
                self._search_entry.set_text("")
            self.exit_drag_receive_mode()
            self._rebuild()
            adj = self.scroll.get_vadjustment()
            adj.set_value(adj.get_lower())

    def _sorted_by_usage(self, apps: list) -> list:
        usage = load_usage()
        return sorted(apps, key=lambda a: get_usage_count(a, usage), reverse=True)

    def _search(self, entry):
        query = entry.get_text()
        if not query:
            self._rebuild()
            return

        usage = load_usage()
        raw_results = process.extract(
            query,
            self._all_apps,
            processor=lambda a: a.display_name if isinstance(a, DesktopApp) else a,
            scorer=fuzz.WRatio,
            limit=50,
        )
        filtered = [(app, score) for app, score in raw_results if score >= 60]
        boosted = sorted(
            filtered,
            key=lambda pair: (round(pair[1] / 10) * 10, get_usage_count(pair[0], usage)),
            reverse=True,
        )
        adj = self.scroll.get_vadjustment()
        adj.set_value(adj.get_lower())
        self._rebuild(
            apps=[app for app, _ in boosted],
            placeholder_slot=None,
            applet_items_override=[],
        )