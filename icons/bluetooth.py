from fabric.widgets.box import Box
from services.singletons import bluetooth
from snippets import Icon

class BluetoothIcon(Box):
    def __init__(self, size, **kwargs):
        self._icon = Icon(
            icon_name=self._get_bluetooth_icon(),
            pixel_size=size,
        )

        super().__init__(children=[self._icon], **kwargs)

        bluetooth.connect("changed", self._on_bluetooth_changed)

    def _get_bluetooth_icon(self) -> str:
        if bluetooth.connected_devices:
            return "bluetooth-connected"
        if bluetooth.state in ("on", "discovering"):
            return "bluetooth"
        return "bluetooth-slash"
    
    def _on_bluetooth_changed(self, *_):
        self._icon.set_property("icon-name", self._get_bluetooth_icon())