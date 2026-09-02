from fabric.widgets.box import Box
from snippets import Icon, ScrollingLabel
from ..sliders import SliderBox
from icons import VolumeIcon, MicrophoneIcon
from .menu import QSAppletPage
from .tab import TabStack, TabMenu
from services.singletons import audio

class StreamItem(Box):
    def __init__(self, stream, microphone: bool):
        self.checkmark = Icon(
            icon_name="check-circle",
            icon_size=16,
            # style_classes=["qs-checkmark-active"] if self._is_default(stream) else [],
        )

        self.slider = SliderBox(
            left_icon=MicrophoneIcon(stream=stream, size=16) if microphone else VolumeIcon(stream=stream, size=16),
            on_left_click=lambda *_, stream=stream: stream.set_muted(not stream.muted),
            scale_min=0,
            scale_max=100,
            scale_value=stream.volume,
            on_scale_change=lambda s, stream=stream: stream.set_volume(s.get_value()),
            on_right_click=lambda *_, stream=stream: (
                audio._control.set_default_source(stream.stream)
                if microphone
                else audio._control.set_default_sink(stream.stream)
            ),
            right_icon=self.checkmark,
        )
        
        super().__init__(
            orientation="v",
            spacing=8,
            h_expand=True, h_align="fill",
            children=[
                Box(
                    style_classes=["audio-device-label-container"],
                    children=ScrollingLabel(
                    style_classes=["qs-description-label"],
                    label=stream.description or "",
                    max_width=250,
                    pixels_per_second=100,
                    h_align="start",
                )),
                self.slider
            ],
        )
        stream.connect("notify::volume", lambda obj, _, stream=stream: self.slider.scale.set_value(obj.volume))
        stream.connect("closed", lambda *_, stream=stream: self.unparent())

        audio.connect("speaker-changed", lambda *_: self._update_checkmark(stream))
        audio.connect("microphone-changed", lambda *_: self._update_checkmark(stream))
        self._update_checkmark(stream)

    def _is_default(self, stream) -> bool:
        if stream.type == "speakers":
            return bool(audio.speaker and audio.speaker.id == stream.id)
        elif stream.type == "microphones":
            return bool(audio.microphone and audio.microphone.id == stream.id)
        return False

    def _update_checkmark(self, stream):
        if self._is_default(stream):
            self.slider.icon_button.add_style_class("active")
        else:
            self.slider.icon_button.remove_style_class("active")

def _make_output_box():
    box = Box(orientation="v", spacing=12)

    def rebuild(*_):
        box.children = [StreamItem(s, False) for s in audio.speakers or []]

    audio.connect("notify::speakers", lambda *_: rebuild())
    rebuild()
    return box

def _make_input_box():
    box = Box(orientation="v", spacing=12)

    def rebuild(*_):
        box.children = [StreamItem(s, True) for s in audio.microphones or []]

    audio.connect("notify::microphones", lambda *_: rebuild())
    rebuild()
    return box

class AudioMenu(QSAppletPage):
    def __init__(self, parent=None, stack=None, **kwargs):
        self.tab_stack = TabStack()

        super().__init__(
            title="Volume",
            stack=stack,
            child=self.tab_stack,
            **kwargs,
        )

        self.tab_stack.add_tab(
            name="output",
            label="Output",
            content=TabMenu(child=_make_output_box()),
        )
        self.tab_stack.add_tab(
            name="input",
            label="Input",
            content=TabMenu(child=_make_input_box()),
        )