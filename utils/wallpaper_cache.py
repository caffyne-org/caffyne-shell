import gc
import hashlib
import os

from pathlib import Path

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf
from PIL import Image as PilImage

CACHE_ROOT = Path.home() / ".cache" / "caffyne-shell"

SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def cache_key(file_path: str) -> str:
    stat = os.stat(file_path)
    raw  = f"{file_path}:{stat.st_mtime}:{stat.st_size}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_path(variant: str, file_path: str) -> Path:
    return CACHE_ROOT / variant / f"{cache_key(file_path)}.jpg"


def _center_crop(img, width: int, height: int):
    w, h   = img.size
    target = width / height
    source = w / h

    if source > target:
        new_w = int(round(h * target))
        left  = (w - new_w) // 2
        return img.crop((left, 0, left + new_w, h))

    new_h = int(round(w / target))
    top   = (h - new_h) // 2
    return img.crop((0, top, w, top + new_h))


def cached_image(
    file_path: str,
    variant: str,
    width: int,
    height: int,
    crop: bool = True,
    quality: int = 85,
) -> Path | None:
    try:
        target_dir = CACHE_ROOT / variant
        target_dir.mkdir(parents=True, exist_ok=True)

        out = target_dir / f"{cache_key(file_path)}.jpg"
        if not out.exists():
            with PilImage.open(file_path) as img:
                if hasattr(img, "draft"):
                    img.draft("RGB", (width * 2, height * 2))
                if img.mode != "RGB":
                    img = img.convert("RGB")
                if crop:
                    img = _center_crop(img, width, height)
                scaled = img.resize((width, height), PilImage.Resampling.LANCZOS)
                scaled.save(out, "JPEG", quality=quality, optimize=True)
                del scaled
            gc.collect()
        return out
    except Exception:
        return None


def load_pixbuf(cache_path: Path) -> GdkPixbuf.Pixbuf | None:
    try:
        return GdkPixbuf.Pixbuf.new_from_file(str(cache_path))
    except Exception:
        return None


def list_wallpapers(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    return sorted(
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.lower().endswith(SUPPORTED_EXTS)
    )
