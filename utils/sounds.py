import shutil
from fabric.utils import exec_shell_command_async
from fabric.utils import get_relative_path

def _detect_player() -> str | None:
    for player in ("pw-play", "paplay"):
        if shutil.which(player):
            return player
    return None

def get_sound_path(svg_name):
    return get_relative_path("../sounds/" + svg_name + ".wav")

_PLAYER = _detect_player()

def play_sound(name: str) -> None:
    print("play")
    if _PLAYER is None:
        print("[play_sound] No audio player found (tried pw-play, paplay)")
        return
    exec_shell_command_async(f"{_PLAYER} {get_sound_path(name)}")