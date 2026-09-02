from ....common.components import AppPage
from ....common.rows import InfoRow, WebsiteRow, PageSection
from fabric.widgets.image import Image
from snippets import Icon
import os

def get_logo_name():
    with open("/etc/os-release") as f:
        for line in f:
            if line.startswith("LOGO="):
                return line.strip().split("=", 1)[1].strip('"')
    return "distributor-logo"

def get_hostname() -> str:
    with open("/etc/hostname") as f:
        return f.read().strip()

def get_kernel() -> str:
    return os.uname().release

def get_os_name() -> str:
    with open("/etc/os-release") as f:
        for line in f:
            if line.startswith("NAME="):
                return line.strip().split("=", 1)[1].strip('"')
    return "Unknown"

def get_compositor() -> str:
    return os.environ.get("XDG_CURRENT_DESKTOP")

class SystemInfoPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
            name="System",
            title="System",
            items=[
                Image(icon_name=get_logo_name(), icon_size=128),
                PageSection(
                    title="System Info",
                    items=[
                        InfoRow(name="Operating System", info=get_os_name()),
                        InfoRow(name="Compositor", info=get_compositor()),
                        InfoRow(name="Hostname", info=get_hostname()),
                        InfoRow(name="Kernel", info=get_kernel()),
                    ]
                )
            ]
        )