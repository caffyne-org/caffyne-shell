from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from services.singletons import battery, recorder, bluetooth, audio
from icons import NetworkIcon, BatteryIcon, BluetoothIcon, VolumeIcon
from snippets import Icon
from gi.repository import Gdk

class QuickSettingsButton(Box):
    VARIANTS=["single", "default", "battery", "battery+percent"]
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        self._record_icon = Icon(icon_name="record", icon_size=16, visible=False, style_classes=["recording-indicator"])
        self._bluetooth_icon = BluetoothIcon(16)
        self._scroll_accumulator = 0.0

        inner = Box(
            style_classes=["bar-button"],
            spacing=4,
            children=[Icon(icon_name="sliders-horizontal")] if variant == "single" else [
                NetworkIcon(16),
                self._bluetooth_icon,
                VolumeIcon(16),
                self._record_icon,
            ],
        )

        self._event_box = EventBox(
            events=["scroll", "smooth-scroll"],
            child=inner,
            on_scroll_event=self._on_scroll,
        )

        super().__init__(children=[self._event_box], **kwargs)

        if battery.available:
            if variant == "battery+percent":
                inner.add(BatteryIcon(16, True))
            elif variant == "battery":
                inner.add(BatteryIcon(16, False))
            
        recorder.connect("notify::active", self._on_recorder_changed)
        bluetooth.connect("notify::enabled", self._on_bt_state_changed)
        self._bluetooth_icon.set_visible(bluetooth.enabled)

    def _on_scroll(self, _, event):
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            _, dx, dy = event.get_scroll_deltas()
            self._scroll_accumulator += dy
            if abs(self._scroll_accumulator) >= 1.0:
                self._adjust(int(self._scroll_accumulator))
                self._scroll_accumulator = 0.0
        else:
            match event.direction:
                case Gdk.ScrollDirection.UP:
                    self._adjust(-1)
                case Gdk.ScrollDirection.DOWN:
                    self._adjust(1)

    def _adjust(self, direction: int):
        if audio.speaker:
            audio.speaker.volume -= direction
            self._on_recorder_changed
    def _on_bt_state_changed(self, obj, _):
        self._bluetooth_icon.set_visible(obj.enabled)
    def _on_recorder_changed(self, obj, _):
        self._record_icon.set_visible(obj.active)