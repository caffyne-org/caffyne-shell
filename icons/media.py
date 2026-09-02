from snippets import Icon
from gi.repository import Playerctl

class MediaIcon(Icon):
    def __init__(self, player, **kwargs):
        super().__init__(
            icon_name="pause" if player.props.playback_status == Playerctl.PlaybackStatus.PLAYING else "play",
            **kwargs,
        )

        player.connect(
            "playback-status",
            lambda obj, status: setattr(
                self,
                "icon_name",
                "pause" if status == Playerctl.PlaybackStatus.PLAYING else "play",
            ),
        )