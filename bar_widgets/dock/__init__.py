from __future__ import annotations

from gi.repository import Gtk, Gdk, GLib

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.overlay import Overlay
from snippets import ClippingBox
from services.singletons import wm
from user_options import user_options
from utils.monitors import get_connector_from_monitor_id

from .dock_state import DockState
from .dock_item import DockItem
from .separator import DockSeparator
from ..workspaces import WorkspacePill


class Dock(EventBox):
    def __init__(self, monitor_id: int, vertical: bool = False, variant="", **kwargs):
        self._monitor_id = monitor_id
        self._vertical = vertical
        self._monitor_output = get_connector_from_monitor_id(monitor_id)
        self._state = DockState(user_options)

        super().__init__(
            style_classes=["dock"],
            **kwargs,
        )

        self._pinned_box = ClippingBox(
            orientation="h",
            spacing=1,
            style_classes=["dock-pinned"],
        )

        self._pinned_container = EventBox(
            child=self._pinned_box,
        )
        self._setup_pinned_drop()

        self._workspace_box = Box(
            orientation="h",
            spacing=6,
            style_classes=["dock-workspaces"],
        )

        self._box = Box(
            orientation="h",
            spacing=12,
            style_classes=["dock-inner"],
            children=[self._pinned_container, self._workspace_box],
        )

        self._pill = WorkspacePill(offset=17, width=12)
        self._overlay = Overlay(
            child=self._box,
            overlays=[self._pill],
        )
        self._pill.set_halign(Gtk.Align.FILL)
        self._pill.set_valign(Gtk.Align.FILL)
        self._overlay.set_overlay_pass_through(self._pill, True)
        self._pill.show_all()
        self.add(self._overlay)

        wm.connect("notify::active-window", lambda *_: self._update_pill())
        wm.connect("notify::windows", lambda *_: self._rebuild())
        wm.connect("notify::workspaces", lambda *_: self._rebuild())

        self._rebuild()

    def _rebuild(self) -> None:
        for child in self._pinned_box.get_children():
            self._pinned_box.remove(child)
        for child in self._workspace_box.get_children():
            self._workspace_box.remove(child)

        windows = wm.windows
        workspaces = wm.workspaces

        pinned_items = self._state.build_pinned(windows)
        for item_data in pinned_items:
            item = DockItem(
                app_id=item_data["app_id"],
                pinned=True,
                running=item_data["running"],
                window=item_data["window"],
                workspace_id=-1,
                wm_service=wm,
                dock_state=self._state,
                on_reorder=self._on_reorder,
                on_workspace_move=self._on_workspace_move,
                on_pin_toggle=self._on_pin_toggle,
            )
            item._icon_container.add_style_class("pinned")
            self._pinned_box.add(item)
            # item._setup_drag()
            item.show_all()

        self._pinned_container.set_visible(len(pinned_items) > 0)

        if not workspaces or not self._monitor_output:
            # self._box.show_all()
            self._pinned_container.set_visible(len(pinned_items) > 0)
            self._update_pill()
            return

        groups = self._state.build_workspace_groups(windows, workspaces, self._monitor_output)

        first = True
        for ws_id, items in groups.items():
            if not items:
                continue
            if not first:
                sep = DockSeparator()
                self._workspace_box.add(sep)
                sep.show()
            first = False

            for item_data in items:
                item = DockItem(
                    app_id=item_data["app_id"],
                    pinned=False,
                    running=True,
                    window=item_data["window"],
                    workspace_id=item_data["workspace_id"],
                    wm_service=wm,
                    dock_state=self._state,
                    on_reorder=self._on_reorder,
                    on_workspace_move=self._on_workspace_move,
                    on_pin_toggle=self._on_pin_toggle,
                )
                self._workspace_box.add(item)
                item.show_all()

        self._workspace_box.set_visible(len(self._workspace_box.children) > 0)
        self._pinned_container.set_visible(len(pinned_items) > 0)
        self._update_pill()

    def _update_pill(self, _retries: int = 0) -> None:
        active = wm.active_window
        if not active:
            self._pill.hide_pill()
            return
        for child in self._workspace_box.get_children():
            if isinstance(child, DockItem) and child.window and child.window.id == active.id:
                GLib.idle_add(self._move_pill_to_item, child)
                return
        if _retries < 5:
            GLib.timeout_add(16, self._update_pill, _retries + 1)
        else:
            self._pill.hide_pill()

    def _move_pill_to_item(self, item: DockItem) -> bool:
        try:
            x, y = item.translate_coordinates(self._overlay, 0, 0)
        except Exception:
            return False
        alloc = item.get_allocation()
        if alloc.width <= 1 or alloc.height <= 1 or x < 0 or y < 0:
            GLib.timeout_add(16, self._move_pill_to_item, item)
            return False
        self._pill.move_to(x + alloc.width / 2, workspace_id=item.workspace_id)
        return False

    def _setup_pinned_drop(self) -> None:
        from .dock_item import DOCK_DRAG_TARGET, DOCK_DRAG_INFO
        target_entry = Gtk.TargetEntry.new(DOCK_DRAG_TARGET, Gtk.TargetFlags.SAME_APP, DOCK_DRAG_INFO)
        
        # Attach destination directly to the box containing the children
        self.drag_dest_set(Gtk.DestDefaults.ALL, [target_entry], Gdk.DragAction.MOVE)
        self.connect("drag-data-received", self._on_pinned_drop)
        self.connect("drag-motion", lambda w, ctx, x, y, t: self._on_drag_motion)

    def _on_drag_motion(self, widget, ctx, x, y, time):
        Gdk.drag_status(ctx, Gdk.DragAction.MOVE, time)
        return True
    
    def _on_pinned_drop(self, widget, context, x, y, data, info, time) -> None:
        print("dropa")
        src_app_id = data.get_text()
        Gtk.drag_finish(context, True, False, time)
        if not src_app_id:
            return

        # Hit-test children to find which item we dropped onto and which side
        items = [c for c in self._pinned_box.get_children() if isinstance(c, DockItem)]
        target_item = None
        before = True
        for item in items:
            try:
                item_x, _ = item.translate_coordinates(self, 0, 0)
            except Exception:
                continue
            alloc = item.get_allocation()
            if item_x <= x < item_x + alloc.width:
                target_item = item
                before = x < item_x + alloc.width / 2
                break

        if target_item is None:
            # Dropped past the last item — move to end
            if items:
                target_item = items[-1]
                before = False

        if target_item is None or target_item.app_id == src_app_id:
            return

        self._on_reorder(src_app_id, target_item.app_id, before)

    def _on_reorder(self, src_app_id: str, target_app_id: str, before: bool) -> None:
        src_entry = self._state.get_entry(src_app_id)
        target_entry = self._state.get_entry(target_app_id)
        if src_entry and target_entry:
            target_order = target_entry.order
            new_order = target_order if before else target_order + 1
            self._state.reorder(src_app_id, new_order)
        self._rebuild()

    def _on_workspace_move(self, app_id: str, workspace_id: int) -> None:
        self._rebuild()

    def _on_pin_toggle(self, app_id: str) -> None:
        if self._state.is_pinned(app_id):
            self._state.unpin(app_id)
        else:
            self._state.pin(app_id)
        self._rebuild()