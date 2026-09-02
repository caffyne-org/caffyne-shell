from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from snippets import Icon, SmoothSwitch
from .menu import QSAppletPage
from .tab import TabStack, TabMenu
from services.singletons import bluetooth
from services.bluetooth import BluetoothAdapter, BluetoothDevice
from enum import Enum, auto
from gi.repository import GLib, Gdk, Gtk
from utils.helpers import popup_with_blur
from user_options import user_options


class BTState(Enum):
    IDLE          = auto()
    CONNECTED     = auto()
    CONNECTING    = auto()
    DISCONNECTING = auto()
    FAILED        = auto()


class BluetoothBatteryWidget(Box):
    def __init__(self, device: BluetoothDevice, **kwargs):
        self._device = device

        self._icon  = Icon(icon_name="battery-full", icon_size=12)
        self._label = Label(label="", max_chars_width=4, ellipsize=True)

        super().__init__(
            style_classes=["qs-device-item-detail"],
            style="margin-right: 6px;",
            spacing=2,
            children=[self._icon, self._label],
            **kwargs,
        )

        self._device.connect("changed", self._on_changed)
        self._update()

    def _on_changed(self, *_):
        self._update()

    def _update(self, *_):
        pct        = self._device.battery_level
        has_battery = pct > 0

        self.set_visible(has_battery)
        if not has_battery:
            return

        self._label.set_label(f"{pct}%")
        self._icon.icon_name = self._get_battery_icon(pct)

    @staticmethod
    def _get_battery_icon(pct: int) -> str:
        if pct > 80:
            return "battery-vertical-full"
        elif pct > 60:
            return "battery-vertical-high"
        elif pct > 40:
            return "battery-vertical-medium"
        elif pct > 20:
            return "battery-vertical-low"
        else:
            return "battery-vertical-warning"


class BluetoothIcon(Icon):
    def __init__(self, device: BluetoothDevice, **kwargs):
        super().__init__(icon_name=self._get_icon(device.type), **kwargs)

    def _get_icon(self, device_type: str) -> str:
        return {
            "Headset":    "headset",
            "Headphones": "headphones",
            "Speaker":    "speaker-hifi",
            "Keyboard":   "keyboard",
            "Mouse":      "mouse",
            "Joypad":     "game-controller",
            "Phone":      "device-mobile-camera",
            "Printer":    "printer",
        }.get(device_type, "bluetooth")


def _build_device_menu(device: BluetoothDevice, event: Gdk.EventButton) -> None:
    menu = Gtk.Menu()

    connect_item = Gtk.MenuItem(
        label="Disconnect" if device.connected else "Connect"
    )
    connect_item.connect(
        "activate",
        lambda _: setattr(device, "connecting", not device.connected),
    )
    menu.append(connect_item)

    menu.append(Gtk.SeparatorMenuItem())

    pair_item = Gtk.MenuItem(label="Unpair" if device.paired else "Pair")
    # Can't unpair while connected — mirrors blueman behaviour
    pair_item.set_sensitive(not device.connected)
    pair_item.connect(
        "activate",
        lambda _: setattr(device, "paired", not device.paired),
    )
    menu.append(pair_item)

    trust_item = Gtk.MenuItem(label="Untrust" if device.trusted else "Trust")
    trust_item.connect(
        "activate",
        lambda _: setattr(device, "trusted", not device.trusted),
    )
    menu.append(trust_item)

    if user_options.theme.blur:
        popup_with_blur(menu, event)
    else:
        menu.show_all()
        menu.popup_at_pointer(event)


class BluetoothDeviceItem(Box):
    def __init__(self, device: BluetoothDevice, **kwargs):
        self.device   = device
        self._state   = BTState.IDLE
        self._destroyed  = False
        self._sig_changed = None
        self._sig_closed  = None

        self._connect_attempted = False

        self.status_icon = Icon(icon_name="plugs", icon_size=16)

        self.battery_widget = BluetoothBatteryWidget(device)

        info_box = Box(
            h_expand=True,
            h_align="end",
            spacing=4,
            children=[self.battery_widget, self.status_icon],
        )

        self.content = Button(
            style_classes=["qs-device-item", "left"],
            h_expand=True,
            h_align="fill",
            on_clicked=lambda *_: self._handle_click(),
            child=Box(
                spacing=4,
                children=[
                    BluetoothIcon(device),
                    Label(
                        style_classes=["qs-device-item-label"],
                        label=device.name or device.address,
                        max_chars_width=20,
                        ellipsize=True,
                    ),
                    info_box,
                ],
            ),
        )

        self._dots_btn = Button(
            child=Icon(icon_name="dots-three-outline-vertical", icon_size=16),
            style_classes=["qs-device-item", "right"],
        )
        self._dots_btn.connect("button-press-event", self._open_context_menu)

        super().__init__(
            spacing=1,
            children=[self.content, self._dots_btn],
            **kwargs,
        )

        self._sig_changed = self.device.connect("changed", self._on_device_changed)
        self._sig_closed  = self.device.connect(
            "notify::closed", self._on_device_closed
        )
        self._refresh_state()

    def _open_context_menu(self, _widget, event: Gdk.EventButton):
        _build_device_menu(self.device, event)
        return True

    def _on_device_closed(self, *_):
        if self.device.closed:
            self._disconnect_signals()
            GLib.idle_add(self._safe_destroy)

    def _safe_destroy(self):
        if not self._destroyed:
            self.destroy()
        return False

    def _disconnect_signals(self):
        for attr in ("_sig_changed", "_sig_closed"):
            sig_id = getattr(self, attr, None)
            if sig_id is not None:
                try:
                    self.device.disconnect(sig_id)
                except Exception:
                    pass
                setattr(self, attr, None)

    def destroy(self):
        self._destroyed = True
        self._disconnect_signals()
        super().destroy()

    def _handle_click(self, *_):
        if self._destroyed:
            return
        if self._state == BTState.CONNECTED:
            self._connect_attempted = False
            self._set_state(BTState.DISCONNECTING)
            self.device.connecting = False
        elif self._state == BTState.IDLE:
            self._connect_attempted = True
            self._set_state(BTState.CONNECTING)
            self.device.connecting = True

    def _on_device_changed(self, *_):
        if self._destroyed:
            return

        if self.device.connected:
            self._connect_attempted = False
            self._set_state(BTState.CONNECTED)

        elif self._state == BTState.CONNECTING:
            if self._connect_attempted:
                self._connect_attempted = False
                self._set_state(BTState.FAILED)

        elif self._state == BTState.DISCONNECTING:
            self._set_state(BTState.IDLE)

        else:
            self._set_state(BTState.IDLE)

    def _refresh_state(self):
        self._set_state(BTState.CONNECTED if self.device.connected else BTState.IDLE)

    def _set_state(self, state: BTState):
        if self._destroyed:
            return
        self._state = state

        for cls in ("active", "connecting", "disconnecting", "failed"):
            self.content.remove_style_class(cls)

        if state == BTState.CONNECTED:
            self.content.add_style_class("active")
            self.status_icon.set_visible(True)
            self.status_icon.icon_name = "plugs-connected"

        elif state == BTState.CONNECTING:
            self.content.add_style_class("connecting")
            self.status_icon.set_visible(True)
            self.status_icon.icon_name = "plugs"

        elif state == BTState.DISCONNECTING:
            self.content.add_style_class("disconnecting")
            self.status_icon.set_visible(True)
            self.status_icon.icon_name = "plugs"

        elif state == BTState.FAILED:
            self.content.add_style_class("failed")
            self.status_icon.set_visible(True)
            self.status_icon.icon_name = "plugs"
            GLib.timeout_add(5000, self._reset_from_failed)

        else:
            has_status = self.device.paired or self.device.trusted
            self.status_icon.set_visible(has_status)
            self.status_icon.icon_name = "plugs"

    def _reset_from_failed(self):
        if not self._destroyed:
            self._set_state(BTState.IDLE)
        return False

class BluetoothAdapterTab:

    def __init__(
        self,
        adapter: BluetoothAdapter,
        tab_stack: "TabStack",
        switch: SmoothSwitch,
    ):
        self._adapter     = adapter
        self._tab_stack   = tab_stack
        self._switch      = switch
        self._device_items: dict[str, BluetoothDeviceItem] = {}
        self._destroyed   = False

        self._devices_box = Box(orientation="v", spacing=6)

        self._placeholder = Box(
            style_classes=["menu-list-placeholder"],
            h_align="fill", v_align="fill", h_expand=True, v_expand=True,
            children=[
                Label(
                    v_expand=True, v_align="center",
                    h_expand=True, h_align="center",
                    label="No devices found",
                    style_classes=["menu-list-placeholder-label"],
                )
            ],
        )
        self._placeholder_label: Label = self._placeholder.get_children()[0]

        self._content_stack = Stack(
            transition_duration=200,
            transition_type="crossfade",
            children=[self._devices_box, self._placeholder],
        )

        self._sig_added   = adapter.connect("device-added",   self._on_device_added)
        self._sig_removed = adapter.connect("device-removed", self._on_device_removed)
        self._sig_changed = adapter.connect(
            "changed", lambda *_: self._on_adapter_changed()
        )

        for device in adapter._devices.values():
            self._add_device_item(device)

        self._update_placeholder()

        tab_name  = adapter.object_path.split("/")[-1]
        tab_label = adapter.name or tab_name

        tab_stack.add_tab(
            name=tab_name,
            label=tab_label,
            content=TabMenu(child=self._content_stack),
        )
        self._tab_name = tab_name

    def _on_adapter_changed(self):
        if self._destroyed:
            return
        if not self._adapter.scanning:
            self._prune_unknown_devices()
        self._update_placeholder()

    def _prune_unknown_devices(self):
        to_remove = [
            addr for addr, item in self._device_items.items()
            if not (item.device.paired or item.device.trusted)
        ]
        for addr in to_remove:
            item = self._device_items.pop(addr)
            item.destroy()
            try:
                self._devices_box.remove(item)
            except Exception:
                pass

    def _on_device_added(self, adapter: BluetoothAdapter, address: str):
        if self._destroyed:
            return
        device = adapter.get_device(address)
        if device:
            self._add_device_item(device)

    def _on_device_removed(self, _adapter, address: str):
        if self._destroyed:
            return
        item = self._device_items.pop(address, None)
        if item:
            item.destroy()
            try:
                self._devices_box.remove(item)
            except Exception:
                pass
        self._update_placeholder()

    def sync_switch(self):
        if not self._destroyed:
            self._switch.set_active(self._adapter.powered)

    def handle_switch_toggle(self, value: bool):
        if not self._destroyed:
            self._adapter.powered = value

    def handle_scan(self):
        if not self._destroyed:
            self._adapter.scan()

    def _add_device_item(self, device: BluetoothDevice):
        addr = device.address
        if addr in self._device_items:
            return
        item = BluetoothDeviceItem(device)
        self._device_items[addr] = item
        self._devices_box.add(item)
        self._update_placeholder()

    def _update_placeholder(self):
        if self._destroyed:
            return

        if not self._adapter.powered:
            label   = "Adapter is off"
            show_ph = True
        elif not self._device_items:
            label   = "No devices found"
            show_ph = True
        else:
            label   = ""
            show_ph = False

        self._placeholder_label.set_label(label)

        if show_ph:
            self._content_stack.set_visible_child(self._placeholder)
        else:
            self._content_stack.set_visible_child(self._devices_box)

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True

        for sig_attr in ("_sig_added", "_sig_removed", "_sig_changed"):
            sig_id = getattr(self, sig_attr, None)
            if sig_id is not None:
                try:
                    self._adapter.disconnect(sig_id)
                except Exception:
                    pass
                setattr(self, sig_attr, None)

        for item in list(self._device_items.values()):
            try:
                item.destroy()
            except Exception:
                pass
        self._device_items.clear()

        self._tab_stack.remove_tab(self._tab_name)


class BluetoothMenu(QSAppletPage):
    def __init__(self, parent=None, stack=None, **kwargs):
        self._adapter_tabs: dict[str, tuple[BluetoothAdapterTab, int]] = {}

        self.tab_stack = TabStack()

        self.switch = SmoothSwitch(
            on_user_toggle=self._on_switch_toggled,
            style_classes=["smooth-switch"],
            v_align="center",
            v_expand=False,
            width=48,
        )

        super().__init__(
            title="Bluetooth",
            stack=stack,
            button_icon_name="arrows-clockwise",
            button_action=lambda btn: self._scan(btn),
            child=self.tab_stack,
            switch=self.switch,
            **kwargs,
        )

        bluetooth.connect("adapter-added",   self._on_adapter_added)
        bluetooth.connect("adapter-removed", self._on_adapter_removed)

        for adapter in bluetooth.adapters:
            self._add_adapter_tab(adapter)

        self.tab_stack.connect("notify::visible-child", self._on_tab_switched)
        self._sync_switch_to_active_tab()

    def _on_switch_toggled(self, value: bool):
        tab = self._get_active_tab()
        if tab:
            tab.handle_switch_toggle(value)

    def _sync_switch_to_active_tab(self):
        tab = self._get_active_tab()
        if tab:
            tab.sync_switch()

    def _on_tab_switched(self, *_):
        self._sync_switch_to_active_tab()

    def _on_adapter_added(self, _, path: str):
        adapter = bluetooth.get_adapter(path)
        if adapter:
            self._add_adapter_tab(adapter)

    def _on_adapter_removed(self, _, path: str):
        entry = self._adapter_tabs.pop(path, None)
        if entry is None:
            return
        tab, sig_id = entry
        adapter = bluetooth.get_adapter(path)
        if adapter is not None:
            try:
                adapter.disconnect(sig_id)
            except Exception:
                pass
        tab.destroy()
        self._sync_switch_to_active_tab()

    def _get_active_tab(self) -> "BluetoothAdapterTab | None":
        try:
            visible_name = self.tab_stack.get_visible_child_name()
            if visible_name:
                for tab, _ in self._adapter_tabs.values():
                    if tab._tab_name == visible_name:
                        return tab
        except Exception:
            pass
        if self._adapter_tabs:
            return next(iter(self._adapter_tabs.values()))[0]
        return None

    def _scan(self, button):
        tab = self._get_active_tab()
        if not tab:
            return
        button.get_child().set_active(True)
        tab.handle_scan()
        GLib.timeout_add(
            10_000,
            lambda: (button.get_child().set_active(False), False)[1],
        )

    def _add_adapter_tab(self, adapter: BluetoothAdapter):
        path = adapter.object_path
        if path in self._adapter_tabs:
            old_tab, old_sig = self._adapter_tabs.pop(path)
            try:
                adapter.disconnect(old_sig)
            except Exception:
                pass
            old_tab.destroy()

        tab = BluetoothAdapterTab(adapter, self.tab_stack, self.switch)
        sig_id = adapter.connect(
            "notify::powered",
            lambda *_: self._sync_switch_to_active_tab(),
        )
        self._adapter_tabs[path] = (tab, sig_id)
        self._sync_switch_to_active_tab()