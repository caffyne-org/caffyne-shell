from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.entry import Entry
from fabric.widgets.button import Button
from snippets import Icon
from .menu import QSAppletPage
from enum import Enum, auto

class PasswordState(Enum):
    IDLE = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()

STATE_CONFIG = {
    PasswordState.IDLE: {
        "icon": "shield-warning",
        "status": "Protected Network",
        "button": "Connect",
        "sensitive": True,
    },
    PasswordState.CONNECTING: {
        "icon": "shield-warning",
        "status": "Connecting…",
        "button": "Connecting…",
        "sensitive": False,
    },
    PasswordState.CONNECTED: {
        "icon": "shield-check",
        "status": "Connected!",
        "button": "Connected",
        "sensitive": False,
    },
    PasswordState.ERROR: {
        "icon": "shield-warning",
        "status": "Error",
        "button": "Try Again",
        "sensitive": True,
    },
}

class WifiPasswordMenu(QSAppletPage):
    def __init__(self, stack=None, **kwargs):
        self.stack = stack
        self._on_submit_cb = None
        self._on_cancel_cb = None
        self._bssid = None

        self._status_label = Label(label="Protected Network")
        self._instruction_label = Label(
            label="",
            style_classes=["menu-section-title"],
            line_wrap="word",
        )
        self._shield = Icon(icon_name="shield-warning", icon_size=50)
        self._entry = Entry(
            placeholder_text="Password",
            password=True,
            style_classes=["wifi-password-entry"],
            h_expand=True,
        )
        self._show_toggle = Button(
            child=Icon(icon_name="eye", icon_size=16),
            style_classes=["icon-button"],
            on_clicked=lambda *_: self._toggle_visibility(),
        )
        self._error_label = Label(
            label="",
            style_classes=["wifi-password-error"],
            visible=False,
        )
        self._connect_button = Button(
            label="Connect",
            style_classes=["suggested-action"],
            on_clicked=lambda *_: self._submit(),
        )

        self._entry.connect("activate", lambda *_: self._submit())

        super().__init__(
            title="Enter Password",
            stack=stack,
            child=Box(
                orientation="v",
                spacing=12,
                v_expand=True,
                v_align="center",
                children=[
                    self._shield,
                    self._status_label,
                    self._instruction_label,
                    self._error_label,
                    Box(spacing=8, children=[self._entry, self._show_toggle]),
                    self._connect_button,
                ],
            ),
            **kwargs,
        )
        self.connect("realize", lambda: self._on_realise())

    def _on_realise(self):
        if self.stack:
            self.stack.connect("notify::visible-child", lambda *_: self._on_page_changed())
    def _set_state(self, state: PasswordState, instruction: str = ""):
        cfg = STATE_CONFIG[state]
        self._shield.icon_name = cfg["icon"]
        self._status_label.set_label(cfg["status"])
        self._connect_button.set_label(cfg["button"])
        self._connect_button.set_sensitive(cfg["sensitive"])

        for cls in ["connecting", "connected", "error"]:
            self.remove_style_class(cls)
        if state == PasswordState.CONNECTING:
            self.add_style_class("connecting")
        elif state == PasswordState.CONNECTED:
            self.add_style_class("connected")
        elif state == PasswordState.ERROR:
            self.add_style_class("error")

        if instruction:
            self._instruction_label.set_label(instruction)
            self._error_label.set_visible(False)
        
        self._state = state

    def load(self, ssid: str, bssid: str, on_submit, on_cancel=None):
        self._bssid = bssid
        self._ssid = ssid
        self._on_submit_cb = on_submit
        self._on_cancel_cb = on_cancel
        self._entry.set_text("")
        self._error_label.set_visible(False)
        self._set_state(
            PasswordState.IDLE,
            instruction=f"{ssid} is a protected network. Please enter the password to proceed.",
        )

    def show_error(self, message: str = "Incorrect password. Try again."):
        self._error_label.set_label(message)
        self._error_label.set_visible(True)
        self._set_state(PasswordState.ERROR, instruction=message)

    def show_connected(self):
        self._set_state(PasswordState.CONNECTED, instruction="Successfully connected!")

    def _on_page_changed(self):

        if not hasattr(self, "_state"):
            return
        if self._state == PasswordState.CONNECTING:
            if self._on_cancel_cb:
                self._on_cancel_cb()
            self._set_state(
                PasswordState.IDLE,
                instruction=f"{self._ssid} is a protected network. Please enter the password to proceed." if hasattr(self, "_ssid") else "",
            )

    def _toggle_visibility(self):
        visible = self._entry.get_visibility()
        self._entry.set_visibility(not visible)

    def _submit(self):
        password = self._entry.get_text().strip()
        if not password:
            self.show_error("Password cannot be empty.")
            return
        self._set_state(PasswordState.CONNECTING, instruction="Attempting to connect…")
        if self._on_submit_cb:
            self._on_submit_cb(self._bssid, password)