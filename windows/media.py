
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.overlay import Overlay
from fabric.widgets.image import Image
from snippets import Icon, FlatScale
from services.player import PlayerService
from icons import MediaIcon
from snippets import ClippingBox, HackedStack
from services.singletons import player_manager
from utils.helpers import load_blurred_pixbuf, load_scaled_pixbuf, load_cover_pixbuf

class MediaPlayer(Box):
    def __init__(self, name: str, service: PlayerService, applet: "MediaApplet", **kwargs):
        self.name = name
        self.service = service
        self.applet = applet
        self._seeking = False

        art_path = service.get_artwork() or None

        self.cover_placeholder = Box(style_classes=["player-cover-placeholder"])
        self.album_placeholder = Overlay(
            child=Box(style_classes=["player-art-placeholder"]),
            overlays=[Icon(icon_name="vinyl-record-duotone", pixel_size=64)],
        )
        self.cover_image = Image(
            pixbuf=load_blurred_pixbuf(art_path, 324, 228, 10, 0.6) or None,
        )
        self.album_art = Image(
            pixbuf=load_cover_pixbuf(art_path, 76, 76) or None,
            style="border-radius: 40px;",
        )
        self.cover_stack = Stack(
            children=[self.cover_placeholder, self.cover_image]
        )
        self.album_stack = Stack(
            children=[self.album_placeholder, self.album_art]
        )
        self.artist_label = Label(
            label="",
            h_align="start",
            style="font-size: 16.5px; font-weight: bold;",
            ellipsization="end",
            max_chars_width=52,
        )

        self.title_label = Label(
            label="",
            h_align="start",
            style="font-size: 16.5px;",
            ellipsization="end",
            max_chars_width=52,
        )

        self.position_scale = FlatScale(
            style_classes=["scale"],

            h_align="fill",
            h_expand=True,
            min_value=0,
            max_value=100,
            value=0,

        )
        super().__init__(
            orientation="v",
            spacing=16,
            children=[
                Overlay(
                    style_classes=["player-cover"],
                    child=ClippingBox(style_classes=["player-cover-background"], children=self.cover_stack),
                    overlays=[
                        CenterBox(
                            orientation="v",
                            start_children=Image(
                                h_align="end",
                                icon_name=name,
                                pixel_size=24,
                                style="margin: 18px 18px 0px 0px;",
                            ),
                            center_children=ClippingBox(
                                h_align="center",
                                style="border-radius: 40px;",
                                children=[self.album_stack],
                            ),
                            end_children=Box(
                                orientation="v",
                                h_align="start",
                                style="margin: 16px;",
                                spacing=8,
                                children=[self.artist_label, self.title_label],
                            ),
                        )
                    ],
                ),
                Box(
                    spacing=12,
                    h_align="fill",
                    children=[
                        Button(
                            style_classes=["applet-misc-button"],
                            child=Icon(icon_name="skip-back-duotone"),
                            on_clicked=lambda *_: service._player.previous(),
                        ),
                        self.position_scale,
                        Button(
                            style_classes=["applet-misc-button"],
                            child=Icon(icon_name="skip-forward-duotone"),
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
            **kwargs,
        )

        try:
            metadata = service._player.props.metadata
            if metadata:
                self._on_meta_change(service, metadata, service._player)
        except Exception:
            pass
        self.cover_stack.set_visible_child(self.cover_image if art_path else self.cover_placeholder)
        self.album_stack.set_visible_child(self.album_art if art_path else self.album_placeholder)
        service.connect("meta-change", self._on_meta_change)
        service.connect("artwork-change", self._on_artwork_change)
        service.connect("track-position", self._on_track_position)
        self.position_scale.connect("button-press-event", lambda *_: setattr(self, "_seeking", True))
        self.position_scale.connect("button-release-event", self._on_seek_release)

    def _on_seek_release(self, scale, event):
        self._seeking = False
        self.service.set_position(scale.get_value())

    def _on_track_position(self, service, pos: float, dur: float):
        if self._seeking:
            return
        if dur > 0:

            self.position_scale._max_value = dur
            self.position_scale.set_value(pos)

    def _on_meta_change(self, service, metadata, player):
        keys = metadata.keys()
        self.artist_label.set_label(
            metadata["xesam:artist"][0] if "xesam:artist" in keys else ""
        )
        self.title_label.set_label(
            metadata["xesam:title"] if "xesam:title" in keys else ""
        )

    def _on_artwork_change(self, service, art_path: str):
        pixbuf_large = load_blurred_pixbuf(art_path, 324, 228, blur_radius=10, darken_factor=0.6)
        pixbuf_small = load_scaled_pixbuf(art_path, 76, 76)

        if pixbuf_large:
            self.cover_image.set_from_pixbuf(pixbuf_large)
            self.cover_stack.set_visible_child(self.cover_image)
        else:
            self.cover_stack.set_visible_child(self.cover_placeholder)

        if pixbuf_small:
            self.album_art.set_from_pixbuf(pixbuf_small)
            self.album_stack.set_visible_child(self.album_art)
        else:
            self.album_stack.set_visible_child(self.album_placeholder)

class PlayerStackSwitcher(CenterBox):
    def __init__(self, stack: Stack, **kwargs):
        self.stack = stack
        self._applet: "MediaApplet | None" = None

        self.title = Label(
            style="padding: 8px 10px; font-size: 14px;",
            ellipsization="end",
            max_chars_width=20,
        )

        super().__init__(
            start_children=self.title,
            end_children=Box(
                spacing=12,
                children=[
                    Button(
                        style_classes=["applet-misc-button"],
                        child=Icon(icon_name="arrow-left-duotone"),
                        on_clicked=lambda *_: self._navigate(-1),
                    ),
                    Button(
                        style_classes=["applet-misc-button"],
                        child=Icon(icon_name="arrow-right-duotone"),
                        on_clicked=lambda *_: self._navigate(1),
                    ),
                ],
            ),
            **kwargs,
        )

        self.stack.connect("notify::visible-child", lambda *_: self.sync())

    def sync(self):
        if not self._applet:
            return

        current = self._applet.get_current_name()
        if current:
            self.title.set_label(current.capitalize())

        player_count = len(self._applet.get_player_names())
        self.end_children[0].set_visible(player_count > 1)

    def _navigate(self, direction: int):
        if not self._applet:
            return
        names = self._applet.get_player_names()
        if not names:
            return
        current = self._applet.get_current_name()
        i = names.index(current) if current in names else 0
        target_name = names[(i + direction) % len(names)]
        self._applet.player_stack.transition_type = "slide-left" if direction > 0 else "slide-right"
        self._applet.player_stack.set_visible_child_name(target_name)

class MediaApplet(Box):
    def __init__(self, parent, **kwargs):
        self._players: dict[str, MediaPlayer] = {}
        self.player_stack = HackedStack(style_classes=["applet-stack"], bezier_curve=(0.34, 1.3, 0.64, 1.0), duration=0.45)
        self.switcher = PlayerStackSwitcher(self.player_stack)

        super().__init__(
            style_classes=["applet-menu"],
            orientation="v",
            spacing=12,
            children=[self.switcher, self.player_stack],
            **kwargs,
        )

        self.switcher._applet = self

        player_manager.connect(
            "new-player", lambda _, name, service: self._add_player(name, service)
        )
        player_manager.connect(
            "player-vanish", lambda _, name: self.remove_player(name)
        )

        for name, service in player_manager.get_all_services().items():
            self._add_player(name, service)

    def _add_player(self, name: str, service: PlayerService):
        if name in self._players:
            return
        media = MediaPlayer(name, service, self)
        self._players[name] = media
        self.player_stack.add_named(media, name)
        self.player_stack.set_visible_child(media)
        self.switcher.sync()
        self.sync()

    def remove_player(self, name: str):
        if name not in self._players:
            return
        media = self._players.pop(name)
        self.player_stack.remove(media)
        media.destroy()
        if self._players:
            self.player_stack.set_visible_child_name(
                list(self._players.keys())[-1]
            )
        self.switcher.sync()
        self.sync()

    def get_player_names(self) -> list[str]:
        return list(self._players.keys())

    def get_current_name(self) -> str | None:
        visible = self.player_stack.get_visible_child()
        for name, media in self._players.items():
            if media is visible:
                return name
        return None
    
    def sync(self):
        has_players = bool(self._players)
        self.set_visible(has_players)

        if not has_players:
            parent = self.get_parent()
            while parent is not None:
                if hasattr(parent, '_keys'):
                    if parent._keys == ["Media"] or len(parent._keys) <= 1:
                        if parent.get_visible():
                            parent.hide()
                    break
                parent = parent.get_parent()