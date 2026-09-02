from fabric.widgets.label import Label
from snippets import Icon
from .button import QSButton
from services.singletons import bluetooth, network
from gi.repository import GLib

class AirplaneModeButton(QSButton):
    def __init__(self, **kwargs):
        self.network_state: bool = False
        self.bluetooth_state: bool = False

        super().__init__(
            icon=Icon(icon_name="airplane", icon_size=16),
            label=Label(label="Airplane Mode"),
            on_activate=lambda _: self._activate(),
            on_deactivate=lambda _: self._deactivate(),
            **kwargs,
        )
        network.connect("device-ready", self._on_device_ready)

    def _on_device_ready(self, *_):
        if not network.wifi_device:
            return
        network.wifi_device.connect("notify::enabled", lambda obj, _: self._on_wifi_change(obj.enabled))
        bluetooth.connect("notify::state", lambda obj, _: self._on_bluetooth_change(obj.state))

    def _on_wifi_change(self, enabled: bool):
        if self.active and enabled:
            self.active = False

    def _on_bluetooth_change(self, state: str):
        if self.active and state in ["on", "turning-on"]:
            self.active = False

    def _activate(self):
        self.network_state = network.wifi_device.enabled
        self.bluetooth_state = bluetooth.powered
        network.wifi_device.set_enabled(False)
        bluetooth.set_property("powered", False)
        GLib.timeout_add(500, lambda: (setattr(self, "active", True), False)[1])

    def _deactivate(self):
        network.wifi_device.set_enabled(self.network_state)
        bluetooth.set_property("powered", self.bluetooth_state)
        GLib.timeout_add(500, lambda: (setattr(self, "active", False), False)[1])