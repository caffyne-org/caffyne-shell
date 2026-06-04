import os
import json
from loguru import logger

from gi.repository import Gio, GLib

from fabric.core.service import Property
from fabric.utils.helpers import idle_add

from ..base.service import WMService
from .window import MangoWindow
from .workspace import MangoWorkspace
from .keyboard import MangoKeyboardLayouts

MANGO_BUFFER_SIZE = 1_048_576


class MangoSocketNotFoundError(Exception): ...


class Mango(WMService):

    @Property(bool, "readable", default_value=False)
    def is_available(self) -> bool:
        return self._is_available

    @Property(object, "readable", default_value=None)
    def windows(self) -> list[MangoWindow]:
        return list(self._windows.values())

    @Property(object, "readable", default_value=None)
    def active_window(self) -> MangoWindow | None:
        return self._active_window

    @Property(object, "readable", default_value=None)
    def workspaces(self) -> list[MangoWorkspace]:
        return list(self._workspaces.values())

    @Property(str, "readable", default_value="")
    def active_output(self) -> str:
        return self._active_output

    @Property(object, "readable", default_value=None)
    def keyboard_layouts(self) -> MangoKeyboardLayouts | None:
        return self._keyboard_layouts

    def __init__(self, **kwargs):
        self._windows: dict[int, MangoWindow] = {}
        self._active_window: MangoWindow | None = None
        self._active_window_id: int = -1  # track by id, not object identity
        self._workspaces: dict[int, MangoWorkspace] = {}
        self._active_output: str = ""
        self._keyboard_layouts: MangoKeyboardLayouts | None = None
        self._is_available: bool = False
        self._monitor_cache: dict[str, dict] = {}
        self._pending_monitor_change: bool = False

        socket_path = os.getenv("MANGO_INSTANCE_SIGNATURE")
        if not socket_path or not os.path.exists(socket_path):
            raise MangoSocketNotFoundError(
                f"Mango socket not found (MANGO_INSTANCE_SIGNATURE={socket_path!r}). "
                "Is mango running?"
            )

        self._socket_address = Gio.UnixSocketAddress.new(socket_path)
        self._is_available = True

        super().__init__(**kwargs)

        GLib.Thread.new("mango-watch-monitors", self._watch_thread, "all-monitors")
        GLib.Thread.new("mango-watch-clients", self._watch_thread, "all-clients")
        # GLib.Thread.new("mango-watch-tags", self._watch_thread, "all-tags")
        self._initial_sync()

        self.notify("is-available")
        self.emit("ready")

    # ------------------------------------------------------------------
    # IPC
    # ------------------------------------------------------------------

    def send_command(self, command: str) -> dict:
        try:
            client = Gio.SocketClient()
            conn: Gio.SocketConnection = client.connect(self._socket_address, None)
            conn.get_output_stream().write_all((command + "\n").encode(), None)
            inp = Gio.DataInputStream.new(conn.get_input_stream())
            line, _ = inp.read_line(None)
            conn.close(None)
            if line:
                return json.loads(line.decode())
        except Exception as e:
            logger.error(f"[MangoService] send_command({command!r}) failed: {e}")
        return {}

    # ------------------------------------------------------------------
    # Initial sync — clients first so active_window_id is known when
    # monitors sync runs and tries to set workspace.active_window_id
    # ------------------------------------------------------------------

    def _initial_sync(self) -> None:
        self._apply_clients(self.send_command("get all-clients"))
        self._apply_monitors(self.send_command("get all-monitors"))

    # ------------------------------------------------------------------
    # State application
    # ------------------------------------------------------------------

    def _apply_monitors(self, data: dict) -> None:
        monitors: list[dict] = data.get("monitors", [])
        if not monitors:
            return

        self._monitor_cache = {m["name"]: m for m in monitors}
        new_workspaces: dict[int, MangoWorkspace] = {}

        for m in monitors:
            monitor_name: str = m["name"]
            active_tags: list[int] = m.get("active_tags", [])
            focused = m.get("active", False)

            for tag in m.get("tags", []):
                idx: int = tag["index"]
                synth_id = _synth_workspace_id(monitor_name, idx)
                ws = self._workspaces.get(synth_id) or MangoWorkspace(self)
                ws.sync(
                    monitor_name=monitor_name,
                    tag=tag,
                    active_tags=active_tags,
                    is_focused_monitor=focused,
                    active_window_id=(
                        self._active_window_id
                        if (focused and idx in active_tags)
                        else 0
                    ),
                )
                new_workspaces[synth_id] = ws

        for sid, ws in self._workspaces.items():
            if sid not in new_workspaces:
                ws.emit("destroyed")

        self._workspaces = new_workspaces
        self.notify("workspaces")

        focused_name = next(
            (m["name"] for m in monitors if m.get("active", False)), ""
        )
        if focused_name != self._active_output:
            self._active_output = focused_name
            self.notify("active-output")
            # Don't resolve active window here — the all-clients watch will
            # fire shortly after with updated is_focused states. Resolving now
            # risks a race where active_output is already DP-1 but no window
            # on DP-1 has is_focused=True yet, producing a spurious None.
            # Instead, set a flag so the next _resolve_active_window call
            # from _apply_clients forces a notify even if the ID is unchanged.
            self._pending_monitor_change = True

        focused_mon = self._monitor_cache.get(focused_name, {})
        if focused_mon:
            if self._keyboard_layouts is None:
                self._keyboard_layouts = MangoKeyboardLayouts(self)
            self._keyboard_layouts.sync(focused_mon)
            self.notify("keyboard-layouts")

    def _apply_clients(self, data: dict) -> None:
        clients: list[dict] = data.get("clients", [])
        if not isinstance(clients, list):
            return

        new_windows: dict[int, MangoWindow] = {}
        new_active_id: int = -1

        for c in clients:
            cid: int = c["id"]
            # Reuse existing window object to avoid churn
            win = self._windows.get(cid) or MangoWindow(self)
            win.sync(c)
            new_windows[cid] = win
            if c.get("is_focused", False):
                new_active_id = cid

        # emit destroyed for windows that vanished
        for wid, win in self._windows.items():
            if wid not in new_windows:
                win.emit("destroyed")

        self._windows = new_windows
        self.notify("windows")

        # Update active_window_id from clients directly — don't defer
        self._active_window_id = new_active_id
        self._resolve_active_window()
        
    def _resolve_active_window(self, force_notify: bool = False) -> None:
        # Drop the _pending_monitor_change flag entirely.
        # Instead, always re-resolve from current state — it's cheap.
        new_active = self._windows.get(self._active_window_id)
        if new_active != self._active_window or force_notify:
            self._active_window = new_active
            self.notify("active-window")

    def _get_window_output(self, window) -> str:
        """Get the output/monitor name for a window via its workspace."""
        ws = self._workspaces.get(window.workspace_id)
        return ws.output if ws else ""

    # ------------------------------------------------------------------
    # Watch threads
    # ------------------------------------------------------------------

    def _watch_thread(self, topic: str) -> bool:
        RETRY_DELAY_MS = 2000
        while True:
            try:
                client = Gio.SocketClient()
                conn = client.connect(self._socket_address, None)
                conn.get_output_stream().write_all(f"watch {topic}\n".encode(), None)
                inp = Gio.DataInputStream.new(conn.get_input_stream())
                while True:
                    line, _ = inp.read_line(None)
                    if line is None:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode())
                    except Exception as e:
                        logger.error(f"[MangoService] watch {topic!r} JSON decode error: {e}")
                        continue
                    idle_add(self._dispatch_watch_event, topic, data)  # <-- this was missing
                conn.close(None)
            except Exception as e:
                logger.error(f"[MangoService] watch {topic!r} error: {e}")

            logger.warning(f"[MangoService] watch {topic!r} reconnecting in {RETRY_DELAY_MS}ms")
            GLib.usleep(RETRY_DELAY_MS * 1000)

    def _dispatch_watch_event(self, topic: str, data: dict) -> None:
        if "error" in data:
            logger.warning(f"[MangoService] watch {topic!r} received error: {data}")
            return
        if topic == "all-monitors":
            self._apply_monitors(data)
        elif topic == "all-clients":
            self._apply_clients(data)

    # ------------------------------------------------------------------
    # WMService interface
    # ------------------------------------------------------------------

    def switch_to_workspace(self, idx: int) -> None:
        self.send_command(f"dispatch view,{idx},0,{self._active_output}")

    def switch_to_workspace_by_id(self, workspace_id: int) -> None:
        ws = self.get_workspace_by_id(workspace_id)
        if ws:
            ws.switch_to()

    def get_workspace_by_id(self, workspace_id: int) -> MangoWorkspace | None:
        return self._workspaces.get(workspace_id)


def _synth_workspace_id(monitor_name: str, tag_index: int) -> int:
    return hash((monitor_name, tag_index)) & 0x7FFFFFFF