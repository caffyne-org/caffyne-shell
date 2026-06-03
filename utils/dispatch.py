import os
from fabric.utils import exec_shell_command_async, DesktopApp


def dispatch_app(app: DesktopApp) -> bool:
    cmd = app.executable  # or app.name if executable isn't available
    if os.getenv("NIRI_SOCKET"):
        exec_shell_command_async(f"niri msg action spawn -- {cmd}")
    elif os.getenv("HYPRLAND_INSTANCE_SIGNATURE"):
        exec_shell_command_async(f"hyprctl dispatch exec {cmd}")
    elif os.getenv("MANGO_INSTANCE_SIGNATURE"):
        exec_shell_command_async(f"mmsg dispatch spawn, {cmd}")
    else:
        return False
    return True