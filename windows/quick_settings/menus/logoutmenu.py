from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from snippets import Icon
from .menu import QSAppletPage
from snippets import AppletPage
from fabric.utils import get_relative_path
import subprocess
import os
from services.singletons import wm
from services.wm.niri.service import Niri
from services.wm.hyprland.service import Hyprland
from services.wm.mango.service import Mango
from utils.session import SESSION_MANAGER
from gi.repository import GLib
from utils.sounds import play_sound

session_id = os.environ.get("XDG_SESSION_ID", "")


def _wm_logout():
    subprocess.Popen("loginctl terminate-session $XDG_SESSION_ID", shell=True)


class ConfirmPage(AppletPage):
    def __init__(self, stack=None, parent=None, **kwargs):  # Removed play_sound from init
        self._parent = parent
        self._play_sound = False  # Will be set dynamically in load()
        self._action_label = Label(
            label="Are you sure?",
            style="font-size: 16px;",
            h_align="center",
        )
        self._icon = Icon(icon_name="power-duotone", icon_size=64, v_expand=True, v_align="end")
        self._confirm_btn = Button(
            v_expand=True,
            v_align="end",
            style_classes=["menu-device-item"],
            label="Confirm",
            on_clicked=lambda *_: self._execute(),
        )
        self._callback = None

        super().__init__(
            title="Confirm",
            stack=stack,
            child=Box(
                v_expand=True,
                orientation="v",
                spacing=12,
                children=[
                    self._icon,
                    self._action_label,
                    self._confirm_btn,
                ],
            ),
            **kwargs,
        )

    def load(self, icon_name, label: str, callback, play_sound: bool = False):
        self._icon.icon_name = icon_name
        self._confirm_btn.set_label(label)
        self._callback = callback
        self._play_sound = play_sound

    def _execute(self):
        if self._play_sound:
            play_sound("session-quit")
            GLib.timeout_add(500, lambda: [self._callback(), False])
        else:
            self._callback()
            
        self._parent.toggle()


class PowerButton(Button):
    def __init__(self, icon_name: str, label: str, command: str = "", on_clicked=None, **kwargs):
        super().__init__(
            style_classes=["qs-power-menu-button"],
            v_align="center",
            child=Box(
                orientation="v",
                spacing=4,
                children=[
                    Icon(icon_name=icon_name, icon_size=24, v_expand=True, v_align="end"),
                    Label(label=label, v_expand=True, v_align="start"),
                ],
            ),
            on_clicked=on_clicked,
            **kwargs,
        )


class LogoutMenu(QSAppletPage):
    def __init__(self, stack=None, parent=None, qs=True, **kwargs):
        self._confirm_page = ConfirmPage(stack=stack, parent=parent)
        self._parent = parent
        self._qs = qs
        self.stack = stack

        def confirm(icon, label, callback, should_sound=False):
            self._confirm_page.load(icon, label, callback, play_sound=should_sound)
            if stack:
                stack.set_visible_child_name("power-confirm")

        self.sign_out_button = PowerButton(
            icon_name="sign-out-duotone",
            label="Logout",
            on_clicked=lambda *_: confirm("sign-out-duotone", "Logout", _wm_logout, should_sound=True),
        )

        super().__init__(
            title="Session",
            stack=stack if qs else None,
            child=Box(
                orientation="v",
                spacing=6,
                children=[
                    Box(spacing=6, h_expand=True, children=[
                        self.sign_out_button,
                        PowerButton(
                            icon_name="lock-duotone",
                            label="Lock",
                            on_clicked=lambda *_: [
                                self._parent.toggle(),
                                subprocess.Popen(
                                    f"python3 {get_relative_path('../../../lockscreen.py')}",
                                    shell=True,
                                ),
                            ],
                        ),
                    ]),
                    Box(spacing=6, h_expand=True, children=[
                        PowerButton(
                            icon_name="arrow-counter-clockwise-duotone",
                            label="Reboot",
                            on_clicked=lambda *_: confirm(
                                "arrow-clockwise-duotone", "Reboot",
                                lambda: subprocess.Popen(f"{SESSION_MANAGER} reboot", shell=True),
                                should_sound=True
                            ),
                        ),
                        PowerButton(
                            icon_name="pause-circle-duotone",
                            label="Suspend",
                            on_clicked=lambda *_: confirm(
                                "pause-circle-duotone", "Suspend",
                                lambda: subprocess.Popen(f"{SESSION_MANAGER} suspend", shell=True),
                            ),
                        ),
                    ]),
                    Box(spacing=6, h_expand=True, children=[
                        PowerButton(
                            icon_name="power-duotone",
                            label="Shutdown",
                            on_clicked=lambda *_: confirm(
                                "power-duotone", "Shutdown",
                                lambda: subprocess.Popen(f"{SESSION_MANAGER} poweroff", shell=True),
                                should_sound=True
                            ),
                        ),
                        PowerButton(
                            icon_name="circle-vertical-line",
                            label="Hibernate",
                            on_clicked=lambda *_: confirm(
                                "circle-vertical-line", "Hibernate",
                                lambda: subprocess.Popen(f"{SESSION_MANAGER} hibernate", shell=True),
                            ),
                        ),
                    ]),
                ],
            ),
            **kwargs,
        )
        self.connect("realize", self._add_confirm_menu)

    def _on_visible_changed(self, *_):
        if self._parent.is_visible():
            GLib.idle_add(self.sign_out_button.grab_focus)

    def _add_confirm_menu(self, *_):
        if self.stack:
            self.stack.add_named(self._confirm_page, "power-confirm")
        if not self._qs:
            self.sign_out_button.grab_focus()
            self._parent.connect("notify::visible", self._on_visible_changed)