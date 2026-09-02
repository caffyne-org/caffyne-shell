import os
from fabric.utils import get_relative_path

DEFAULT_PACK = "default"

def get_svg_path(svg_name, pack=None):
    if pack is not None:
        pack_path = get_relative_path(f"../icon_packs/{pack}/svgs/{svg_name}.svg")
        if os.path.isfile(pack_path):
            return pack_path
    return get_relative_path(f"../icon_packs/{DEFAULT_PACK}/svgs/{svg_name}.svg")