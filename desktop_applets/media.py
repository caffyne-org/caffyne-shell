from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.widgets.image import Image
from snippets import Icon, FlatScale
from services.player import PlayerService
from icons import MediaIcon
from snippets import ClippingBox
from services.singletons import player_manager
from utils.helpers import load_cover_pixbuf, load_scaled_pixbuf, get_app_icon_name


def format_time(seconds: float) -> str:
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins:02d}:{secs:02d}"


class DesktopNoMediaPlaceholder(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            h_align="fill",
            h_expand=True,
            v_align="fill",
            spacing=23,
            children=[
                Box(
                    children=Box(
                    style_classes=["player-art-placeholder"],
                    style="min-width: 36px; min-height: 36px;",
                    v_align="center",
                    children=[Icon(icon_name="vinyl-record", icon_size=36)],
                ),
                h_align="start", style="min-height: 36px;"),
                # Middle: "No Media" label
                Box(
                    orientation="v",
                    v_align="center",
                    v_expand=True,
                    h_align="start",
                    style="margin-left: 4px; opacity: 0.8;",
                    spacing=4,
                    children=[
                        Label(
                            label="No Media Playing",
                            h_align="start",
                            ellipsization="end",
                            max_chars_width=28,
                        ),
                    ],
                ),
                Box(
                    spacing=8,
                    h_align="fill",
                    v_align="end",
                    children=[
                        Button(
                            style_classes=["applet-misc-button"],
                            child=Icon(icon_name="skip-back"),
                            sensitive=False,
                        ),
                        FlatScale(
                            style_classes=["scale"],
                            h_align="fill",
                            h_expand=True,
                            min_value=0,
                            max_value=100,
                            value=0,
                            sensitive=False,
                        ),
                        Button(
                            style_classes=["applet-misc-button"],
                            child=Icon(icon_name="skip-forward"),
                            sensitive=False,
                        ),
                        Button(
                            style_classes=["player-media-icon-button"],
                            child=Icon(
                                icon_name="play",
                                style_classes=["player-media-icon"],
                            ),
                            sensitive=False,
                        ),
                    ],
                ),
            ],
            **kwargs,
        )


class DesktopMediaPlayer(Box):
    def __init__(self, name: str, service: PlayerService, **kwargs):
        self.name = name
        self.service = service

        art_path = service.get_artwork() or None

        self.album_placeholder = Box(
            style_classes=["player-art-placeholder"],
            style="min-width: 36px; min-height: 36px;",
            children=[Icon(icon_name="vinyl-record", icon_size=36)],
        )
        self.album_art = Image(size=(36, 36), style="border-radius: 12px;")

        if art_path:
            self.album_art.set_from_pixbuf(load_cover_pixbuf(art_path, 36, 36))

        self.album_stack = Stack(children=[self.album_placeholder, self.album_art])
        self.album_stack.set_visible_child(
            self.album_art if art_path else self.album_placeholder
        )

        self.artist_label = Label(
            label="",
            h_align="start",
            style="font-weight: bold;",
            ellipsization="end",
            max_chars_width=28,
        )
        self.title_label = Label(
            label="",
            h_align="start",
            ellipsization="end",
            max_chars_width=28,
        )

        # Seek scale
        self.position_scale = FlatScale(
            style_classes=["scale"],
            h_align="fill",
            h_expand=True,
            min_value=0,
            max_value=100,
            value=0,
            value_formatter=lambda val: (
                f"{format_time(val)} / {format_time(self.position_scale._max_value)}"
            ),
        )

        super().__init__(
            # style_classes=["desktop-applet"],
            orientation="h",
            h_align="fill",
            v_align="fill",
            spacing=0,
            children=[
                # Left: album art

                # Right column
                Box(
                    orientation="v",
                    h_align="fill",
                    h_expand=True,
                    v_align="fill",
                    spacing=11,
                    children=[
                        # Top-right: player app icon
                        Box(
                            # h_align="end",
                            style="margin: 0px 6px 0px 0px;",
                            children=[
                                ClippingBox(
                                    style="border-radius: 18px;",
                                    v_align="center",
                                    children=[self.album_stack],
                                    h_expand=True,
                                    h_align="start",
                                ),
                                Image(icon_name=get_app_icon_name(name), pixel_size=24),
                            ],
                        ),
                        # Middle: artist + title
                        Box(
                            orientation="v",
                            v_align="center",
                            v_expand=True,
                            h_align="start",
                            style="margin-left: 4px;",
                            spacing=4,
                            children=[self.artist_label, self.title_label],
                        ),
                        # Bottom: controls
                        Box(
                            spacing=8,
                            h_align="fill",
                            v_align="end",
                            # style="margin: 8px;",
                            children=[
                                Button(
                                    style_classes=["applet-misc-button"],
                                    child=Icon(icon_name="skip-back"),
                                    on_clicked=lambda *_: service._player.previous(),
                                ),
                                self.position_scale,
                                Button(
                                    style_classes=["applet-misc-button"],
                                    child=Icon(icon_name="skip-forward"),
                                    on_clicked=lambda *_: service._player.next(),
                                ),
                                Button(
                                    style_classes=["player-media-icon-button"],
                                    child=MediaIcon(
                                        service._player,
                                        pixel_size=16,
                                        style_classes=["player-media-icon"],
                                    ),
                                    on_clicked=lambda *_: service._player.play_pause(),
                                ),
                            ],
                        ),
                    ],
                ),
            ],
            **kwargs,
        )

        # Init metadata
        try:
            metadata = service._player.props.metadata
            if metadata:
                self._on_meta_change(service, metadata, service._player)
        except Exception:
            pass

        service.connect("meta-change", self._on_meta_change)
        service.connect("artwork-change", self._on_artwork_change)
        service.connect("track-position", self._on_track_position)
        self.position_scale.connect("button-release-event", self._on_seek_release)

    def _on_seek_release(self, scale, event):
        self.service.set_position(scale.get_value())

    def _on_track_position(self, service, position, total_duration=None):
        if self.position_scale._dragging:
            return
        if total_duration:
            self.position_scale._max_value = total_duration
        self.position_scale.set_value(position)

    def _on_meta_change(self, service, metadata, player):
        keys = metadata.keys()
        self.artist_label.set_label(
            metadata["xesam:artist"][0] if "xesam:artist" in keys else ""
        )
        self.title_label.set_label(
            metadata["xesam:title"] if "xesam:title" in keys else ""
        )

    def _on_artwork_change(self, service, art_path: str):
        pixbuf = load_cover_pixbuf(art_path, 36, 36)
        if pixbuf:
            self.album_art.set_from_pixbuf(pixbuf)
            self.album_stack.set_visible_child(self.album_art)
        else:
            self.album_stack.set_visible_child(self.album_placeholder)


class DesktopMediaApplet(Box):
    """
    Desktop widget version of the media applet.
    Always visible; shows a placeholder when no players are active.
    Tracks player recency and always shows the most recently active player.
    """

    def __init__(self, **kwargs):
        self._players: dict[str, DesktopMediaPlayer] = {}
        self._player_order: list[str] = []  # most recent last

        self.player_stack = Stack(style_classes=["applet-stack"])
        self.no_media_placeholder = DesktopNoMediaPlaceholder()
        self.player_stack.add_named(self.no_media_placeholder, "__placeholder__")

        super().__init__(
            style_classes=["desktop-applet", "large"],
            orientation="v",
            children=[self.player_stack],
            **kwargs,
        )

        player_manager.connect(
            "new-player", lambda _, name, service: self._add_player(name, service)
        )
        player_manager.connect(
            "player-vanish", lambda _, name: self._remove_player(name)
        )

        for name, service in player_manager.get_all_services().items():
            self._add_player(name, service)

    def _add_player(self, name: str, service: PlayerService):
        if name in self._players:
            return

        player = DesktopMediaPlayer(name, service)
        self._players[name] = player
        self.player_stack.add_named(player, name)

        if name in self._player_order:
            self._player_order.remove(name)
        self._player_order.append(name)

        service.connect("play", lambda *_: self._on_player_played(name))

        self._sync()

    def _remove_player(self, name: str):
        if name not in self._players:
            return

        player = self._players.pop(name)
        self.player_stack.remove(player)
        player.destroy()

        if name in self._player_order:
            self._player_order.remove(name)

        self._sync()

    def _on_player_played(self, name: str):
        """Bump a player to most recent when it starts playing."""
        if name not in self._player_order:
            return
        self._player_order.remove(name)
        self._player_order.append(name)
        self._sync()

    def _sync(self):
        if self._player_order:
            self.player_stack.set_visible_child_name(self._player_order[-1])
        else:
            self.player_stack.set_visible_child_name("__placeholder__")
