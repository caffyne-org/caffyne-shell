from fabric.widgets.box import Box
from snippets import Icon
from services.singletons import audio

class MicrophoneIcon(Box):
    def __init__(self, size: int, stream=None, **kwargs):
        self._stream = stream
        self._icon = Icon(
            icon_name=self._get_mic_icon(),
            icon_size=size,
        )
        super().__init__(children=[self._icon], **kwargs)

        if stream:
            stream.connect("notify::muted", lambda *_: self._update_icon())
        else:
            audio.connect("microphone-changed", self._on_microphone_changed)
            if audio.microphone:
                audio.microphone.connect("changed", self._update_icon)

    def _on_microphone_changed(self, *_):
        if audio.microphone:
            audio.microphone.connect("changed", self._update_icon)
        self._update_icon()

    def _update_icon(self, *_):
        self._icon.set_icon_name(self._get_mic_icon())

    def _get_mic_icon(self) -> str:
        src = self._stream or audio.microphone
        if src and src.muted:
            return "microphone-slash"
        return "microphone"