import os
import pwd
import shutil
import getpass
from fabric.widgets.image import Image
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from ....common.components import AppPage
from ....common.rows import InfoRow, PageSection, FilePickerRow
from utils.helpers import load_scaled_pixbuf


def get_username() -> str:
    return getpass.getuser()


def get_display_name() -> str:
    user = pwd.getpwuid(os.getuid())
    return user.pw_gecos.split(",")[0] or user.pw_name


def get_avatar_path() -> str:
    username = get_username()
    accounts_service_path = f"/var/lib/AccountsService/icons/{username}"
    home_face_png = os.path.expanduser("~/.face")
    home_face_icon = os.path.expanduser("~/.face.icon")

    if os.path.exists(accounts_service_path):
        return accounts_service_path
    elif os.path.exists(home_face_png):
        return home_face_png
    elif os.path.exists(home_face_icon):
        return home_face_icon
    return "avatar-default"


def persist_avatar(src_path: str) -> None:
    """Copy the chosen image to ~/.face so it persists."""
    dest = os.path.expanduser("~/.face")
    if os.path.abspath(src_path) != os.path.abspath(dest):
        shutil.copy2(src_path, dest)


class ProfileHeader(Box):
    def __init__(self, avatar_path: str, username: str, display_name: str, **kwargs):
        super().__init__(
            orientation="v",
            spacing=8,
            h_align="center",
            v_align="center",
            children=[
                Image(
                    pixbuf=load_scaled_pixbuf(avatar_path, 128, 128) if os.path.isabs(avatar_path) else None,
                    icon_name=avatar_path if not os.path.isabs(avatar_path) else None,
                    pixel_size=128,
                ),
                Label(label=display_name or username, style_classes="profile-display-name"),
                Label(label=username, style_classes="profile-username"),
            ],
            **kwargs,
        )
        self.avatar_image = self.children[0]

    def update_avatar(self, avatar_path: str):
        if os.path.isabs(avatar_path):
            self.avatar_image.set_from_pixbuf(load_scaled_pixbuf(avatar_path, 128, 128))
        else:
            self.avatar_image.set_from_icon_name(avatar_path, 128)


class UserInfoPage(AppPage):
    def __init__(self, **kwargs):
        self.username = get_username()
        self.display_name = get_display_name()
        self.avatar_path = get_avatar_path()

        self.profile_header = ProfileHeader(
            avatar_path=self.avatar_path,
            username=self.username,
            display_name=self.display_name,
        )
        self.avatar_row = FilePickerRow(
            name="Avatar Path",
            value=self.avatar_path,
            on_file_picked=self.update_user_avatar,
            title="Choose User Avatar",
        )

        super().__init__(
            name="User",
            title="User",
            items=[
                self.profile_header,
                PageSection(
                    title="User Info",
                    items=[
                        InfoRow(name="Display Name", info=self.display_name),
                        InfoRow(name="Username", info=self.username),
                        self.avatar_row,
                    ],
                ),
            ],
            **kwargs,
        )

    def update_user_avatar(self, new_path: str):
        persist_avatar(new_path)
        self.avatar_path = new_path
        self.profile_header.update_avatar(new_path)
        self.avatar_row.children[1].child.children[0].set_label(new_path)