from fabric.widgets.box import Box
from services.singletons import network
from snippets import Icon

class NetworkIcon(Box):
    def __init__(self, size: int, **kwargs):
        self._size = size

        self._wifi_icon = Icon(icon_name="wifi-none", icon_size=size)
        self._ethernet_icon = Icon(
            icon_name="network",
            icon_size=size,
        )

        super().__init__(children=[self._wifi_icon, self._ethernet_icon], **kwargs)

        network.connect("device-ready", self._on_device_ready)
        self._on_device_ready()

    def _on_device_ready(self, *_):
        if network.wifi_device:
            network.wifi_device.connect("changed", self._update)
        if network.ethernet_device:
            network.ethernet_device.connect("changed", self._update)
        self._update()

    def _update(self, *_):
        wifi = network.wifi_device
        eth = network.ethernet_device

        eth_active = eth and eth.internet == "activated"
        self._ethernet_icon.set_visible(eth_active)

        if wifi:
            self._wifi_icon.set_visible(not eth_active)
            self._wifi_icon.set_property("icon-name", self._get_wifi_icon())
        else:
            self._wifi_icon.set_visible(False)

    def _get_wifi_icon(self) -> str:
        wifi = network.wifi_device
        if not wifi or wifi.internet != "activated":
            return "wifi-x"

        s = wifi.strength
        if s >= 75:
            return "wifi-high"
        elif s >= 50:
            return "wifi-medium"
        elif s >= 25:
            return "wifi-low"
        else:
            return "wifi-none"