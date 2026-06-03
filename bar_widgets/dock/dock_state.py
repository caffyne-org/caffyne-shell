from __future__ import annotations
import json
import os
from loguru import logger
from fabric.utils import get_relative_path

DOCK_STATE_PATH = get_relative_path("../../config/dock_state.json")

class DockEntry:
    def __init__(self, app_id: str, order: int = 0):
        self.app_id = app_id
        self.order = order

    def to_dict(self) -> dict:
        return {"app_id": self.app_id, "order": self.order}

    @classmethod
    def from_dict(cls, data: dict) -> "DockEntry":
        return cls(app_id=data["app_id"], order=data.get("order", 0))

class DockState:
    def __init__(self, user_options):
        self._user_options = user_options
        self._pinned: list[DockEntry] = self._load()

    def _load(self) -> list[DockEntry]:
        try:
            if not os.path.exists(DOCK_STATE_PATH):
                return []
            with open(DOCK_STATE_PATH, "r") as f:
                raw = json.load(f)
            entries = [DockEntry.from_dict(e) for e in raw]
            for i, e in enumerate(sorted(entries, key=lambda x: x.order)):
                e.order = i
            return entries
        except Exception as e:
            logger.error(f"[DockState] Failed to load dock entries: {e}")
            return []

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(DOCK_STATE_PATH), exist_ok=True)
            with open(DOCK_STATE_PATH, "w") as f:
                json.dump([e.to_dict() for e in self._pinned], f, indent=2)
        except Exception as e:
            logger.error(f"[DockState] Failed to save dock entries: {e}")

    def get_pinned(self) -> list[DockEntry]:
        return sorted(self._pinned, key=lambda e: e.order)

    def get_entry(self, app_id: str) -> DockEntry | None:
        return next((e for e in self._pinned if e.app_id == app_id), None)

    def is_pinned(self, app_id: str) -> bool:
        return any(e.app_id == app_id for e in self._pinned)

    def pin(self, app_id: str) -> None:
        if self.is_pinned(app_id):
            return
        order = max((e.order for e in self._pinned), default=-1) + 1
        self._pinned.append(DockEntry(app_id=app_id, order=order))
        self._save()

    def unpin(self, app_id: str) -> None:
        self._pinned = [e for e in self._pinned if e.app_id != app_id]
        self._renumber()
        self._save()

    def reorder(self, app_id: str, new_order: int) -> None:
        entry = self.get_entry(app_id)
        if not entry:
            return
        sorted_entries = sorted(self._pinned, key=lambda e: e.order)
        sorted_entries.remove(entry)
        new_order = max(0, min(new_order, len(sorted_entries)))
        sorted_entries.insert(new_order, entry)
        for i, e in enumerate(sorted_entries):
            e.order = i
        self._save()

    def build_pinned(self, windows: list) -> list[dict]:
        """
        Flat list of pinned app dicts. Running state is resolved from any
        window across all workspaces — no workspace binding.
        """
        running_by_app: dict[str, list] = {}
        for w in windows:
            running_by_app.setdefault(w.app_id, []).append(w)

        result = []
        for entry in self.get_pinned():
            wins = running_by_app.get(entry.app_id, [])

            window = next((w for w in wins if w.is_focused), wins[0] if wins else None)
            result.append({
                "app_id": entry.app_id,
                "pinned": True,
                "running": len(wins) > 0,
                "window": window,
                "workspace_id": -1,
                "order": entry.order,
            })
        return result

    def build_workspace_groups(self, windows: list, workspaces: list, monitor_output: str) -> dict[int, list[dict]]:
        """
        Workspace groups for running (non-pinned) apps only.
        Pinned apps are excluded from these groups entirely.
        """
        monitor_ws = {ws.id: ws for ws in workspaces if ws.output == monitor_output}
        monitor_ws_ids = set(monitor_ws.keys())
        if not monitor_ws:
            return {}

        ws_idx = {ws.id: ws.idx for ws in monitor_ws.values()}

        groups: dict[int, list[dict]] = {}
        monitor_windows = [w for w in windows if w.workspace_id in monitor_ws_ids]

        for w in monitor_windows:
            groups.setdefault(w.workspace_id, []).append({
                "app_id": w.app_id,
                "pinned": False,
                "running": True,
                "window": w,
                "workspace_id": w.workspace_id,
                "order": 9999,
            })

        sorted_groups: dict[int, list[dict]] = {}
        for ws_id in sorted(groups.keys(), key=lambda wid: ws_idx.get(wid, wid)):
            sorted_groups[ws_id] = groups[ws_id]

        return sorted_groups

    def _renumber(self) -> None:
        for i, e in enumerate(sorted(self._pinned, key=lambda x: x.order)):
            e.order = i