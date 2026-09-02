import os
import shutil
from fabric.utils import exec_shell_command_async
from fabric.utils import get_relative_path
from user_options import user_options

DEFAULT_PACK = "default"

def _detect_player() -> str | None:
    for player in ("pw-play", "paplay"):
        if shutil.which(player):
            return player
    return None

def get_sound_path(sound_name, pack=None):
    if pack is not None:
        pack_path = get_relative_path(f"../sound_packs/{pack}/sounds/{sound_name}.wav")
        if os.path.isfile(pack_path):
            return pack_path
    return get_relative_path(f"../sound_packs/{DEFAULT_PACK}/sounds/{sound_name}.wav")

_PLAYER = _detect_player()

def play_sound(name: str) -> None:
    if _PLAYER is None:
        print("[play_sound] No audio player found (tried pw-play, paplay)")
        return
    pack = user_options.theme.sound_pack
    exec_shell_command_async(f"{_PLAYER} {get_sound_path(name, pack)}")