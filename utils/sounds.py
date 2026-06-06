import ctypes
import shutil
from fabric.utils import get_relative_path

def get_sound_path(name: str) -> str:
    return get_relative_path("../sounds/" + name + ".wav")

try:
    _ca = ctypes.CDLL("libcanberra.so.0")
    _ctx = ctypes.c_void_p()
    _ca.ca_context_create(ctypes.byref(_ctx))
    _BACKEND = "canberra"
except OSError:
    _BACKEND = next((p for p in ("pw-play", "paplay") if shutil.which(p)), None)

def play_sound(name: str) -> None:
    path = get_sound_path(name)
    if _BACKEND == "canberra":
        _ca.ca_context_play(_ctx, 0, b"media.filename", path.encode(), None)
    elif _BACKEND:
        from fabric.utils import exec_shell_command_async
        exec_shell_command_async(f"{_BACKEND} {path}")
    else:
        print("[play_sound] No audio backend found (tried libcanberra, pw-play, paplay)")