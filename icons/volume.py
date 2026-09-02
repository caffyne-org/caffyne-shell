from fabric.widgets.box import Box
from snippets import Icon
from services.singletons import audio

class VolumeIcon(Box):
    def __init__(self, size: int, stream=None, **kwargs):
        self._stream = stream
        self._icon = Icon(
            icon_name=self._get_volume_icon(),
            icon_size=size,
        )
        super().__init__(children=[self._icon], **kwargs)

        if stream:
            stream.connect("notify::muted", lambda *_: self._update_icon())
            stream.connect("notify::volume", lambda *_: self._update_icon())
        else:
            audio.connect("speaker-changed", self._on_speaker_changed)
            if audio.speaker:
                audio.speaker.connect("changed", self._update_icon)

    def _on_speaker_changed(self, *_):
        if not audio.speaker:
            return
        if getattr(self, "_bound_speaker", None) is audio.speaker:
            return

        self._bound_speaker = audio.speaker

        audio.speaker.connect("changed", self._update_icon)

        self._update_icon()

    def _update_icon(self, *_):
        if self._icon.icon_name == self._get_volume_icon():
            return
        self._icon.icon_name = self._get_volume_icon()

    def _get_volume_icon(self) -> str:
        spk = self._stream or audio.speaker
        if not spk:
            return "speaker-simple-x"
        if spk.muted:
            return "speaker-simple-slash"
        elif spk.volume > 67:
            return "speaker-simple-high"
        elif spk.volume > 33:
            return "speaker-simple-low"
        elif spk.volume > 0:
            return "speaker-simple-none"
        else:
            return "speaker-simple-x"