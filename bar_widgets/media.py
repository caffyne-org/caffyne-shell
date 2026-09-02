from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.eventbox import EventBox
from services.player import PlayerService
from snippets import Icon, ScrollingLabel
from fabric.widgets.stack import Stack
from gi.repository import GLib
from services.singletons import player_manager, edit_mode

class MediaPlayer(Box):
    def __init__(self, name: str, service: PlayerService):
        self.name = name
        self.service = service
        self.label = ScrollingLabel(v_align="center", style_classes=["bar-media-label"], label=name, max_width=100, pixels_per_second=100)

        super().__init__(
            spacing=4,
            children=[
                Icon(icon_name="music-notes"),
                EventBox(child=self.label),
            ],
        )

        try:
            metadata = service._player.props.metadata
            if metadata:
                keys = metadata.keys()
                artist = metadata["xesam:artist"][0] if "xesam:artist" in keys else ""
                title = metadata["xesam:title"] if "xesam:title" in keys else ""
                if title or artist:
                    self.label.set_label(f"{title} - {artist}" if artist else title)
        except Exception:
            pass

        service.connect("meta-change", self._on_meta_change)

    def _on_meta_change(self, service, metadata, player):
        keys = metadata.keys()
        artist = metadata["xesam:artist"][0] if "xesam:artist" in keys else ""
        title = metadata["xesam:title"] if "xesam:title" in keys else ""
        if title or artist:
            self.label.set_label(f"{title} - {artist}" if artist else title)

class Media(Box):
    def __init__(self, monitor_id: int, vertical: bool, variant, **kwargs):
        self._players: dict[str, MediaPlayer] = {}
        self._player_order: list[str] = []

        self._stack = Stack(
            style_classes=["bar-button"],
            transition_type="crossfade",
            transition_duration=300,
        )
        self._stack.show()

        self.edit_overlay = Box(
            spacing=4,
            visible=False,
            style_classes=["bar-button", "edit-overlay"],
            children=[
                Icon(icon_name="music-notes"),
                Label(label="Media"),
            ],
        )

        self.placeholder = Box(
            spacing=4,
            visible=False,
            style_classes=["bar-button"],
            children=[
                Icon(icon_name="music-notes"),
            ],
        )

        super().__init__(
            spacing=4,
            children=[self.edit_overlay, self.placeholder, self._stack],
            **kwargs,
        )

        self.connect("realize", self._on_realize)

    def _on_realize(self, *_):
        player_manager.connect("new-player", lambda _, name, service: self._add_player(name, service))
        player_manager.connect("player-vanish", lambda _, name: self._remove_player(name))
        edit_mode.connect("notify::edit-mode", lambda *_: self._update_visibility())

        for name, service in player_manager.get_all_services().items():
            self._add_player(name, service)

        GLib.idle_add(self._update_visibility)

    def _add_player(self, name: str, service: PlayerService):
        if name in self._players:
            return
        widget = MediaPlayer(name, service)
        widget.show_all()
        self._players[name] = widget
        self._player_order.append(name)
        self._stack.add_named(widget, name)
        self._show_latest()
        self._update_visibility()

    def _remove_player(self, name: str):
        if name not in self._players:
            return
        widget = self._players.pop(name)
        self._player_order.remove(name)
        self._stack.remove(widget)
        self._show_latest()
        self._update_visibility()

    def _show_latest(self):
        if self._player_order:
            self._stack.set_visible_child_name(self._player_order[-1])

    def _update_visibility(self):
        has_players = bool(self._players)
        is_editing = edit_mode.edit_mode

        self._stack.set_visible(has_players)
        self.edit_overlay.set_visible(is_editing and not has_players)
        self.placeholder.set_visible(not has_players and not is_editing)

        if len(self.get_parent().get_parent().get_children()) > 1:
            self.get_parent().set_visible(True)
        else:
            self.get_parent().get_parent().set_visible(True)