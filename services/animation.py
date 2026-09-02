import os
import json
import asyncio
import aiohttp
import shutil
import threading
from pathlib import Path
from gi.repository import GLib
from loguru import logger

from fabric.core.service import Service, Signal
from user_options import user_options
from services.pack_fetch import fetch_bytes, fetch_json, friendly_error, make_session

GITHUB_API     = "https://api.github.com"
REPO           = "caffyne-org/caffyne-animation-packs"
LOCAL_PACKS_DIR = os.path.expanduser("~/.config/caffyne-shell/animation_packs")
CACHE_DIR       = os.path.expanduser("~/.cache/caffyne-shell/animation_packs")

TRANSITION_KEYS = ("applet_reveal", "dash_reveal", "stack_transition")

PROTECTED_PACKS = frozenset({"default"})

DEFAULT_EASING = "default"

EASING_PRESETS: dict[str, list[float]] = {
    "linear":         [0.0,  0.0,  1.0,  1.0],
    "ease_in":        [0.42, 0.0,  1.0,  1.0],
    "ease_out":       [0.0,  0.0,  0.58, 1.0],
    "ease_in_out":    [0.42, 0.0,  0.58, 1.0],
    "ease_out_expo":  [0.16, 1.0,  0.3,  1.0],
    "ease_out_back":  [0.34, 1.56, 0.64, 1.0],
    "ease_out_circ":  [0.0,  0.55, 0.45, 1.0],
    "ease_out_quart": [0.25, 1.0,  0.5,  1.0],
}

# Menu order + display names, "default" first.
EASING_LABELS: dict[str, str] = {
    DEFAULT_EASING:   "Default (Pack)",
    "linear":         "Linear",
    "ease_in":        "Ease In",
    "ease_out":       "Ease Out",
    "ease_in_out":    "Ease In Out",
    "ease_out_expo":  "Ease Out Expo",
    "ease_out_back":  "Ease Out Back",
    "ease_out_circ":  "Ease Out Circ",
    "ease_out_quart": "Ease Out Quart",
}

EASING_KEYS = tuple(EASING_LABELS)

_SHADERS_ENABLED = bool(getattr(user_options.animations, "shaders", False))


def shaders_enabled() -> bool:
    """The shader setting as it was when the shell started."""
    return _SHADERS_ENABLED


class AnimationService(Service):
    allow_disable = False

    @Signal
    def packs_loaded(self, packs: object): ...

    @Signal
    def pack_downloaded(self, pack_name: str): ...

    @Signal
    def pack_changed(self, pack_name: str): ...

    @Signal
    def pack_uninstalled(self, pack_name: str): ...

    @Signal
    def transition_changed(self, transition: str): ...

    @Signal
    def error(self, message: str): ...

    _instance: "AnimationService | None" = None

    @staticmethod
    def get_instance() -> "AnimationService":
        if AnimationService._instance is None:
            AnimationService._instance = AnimationService()
        return AnimationService._instance

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        os.makedirs(LOCAL_PACKS_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)


    def get_shaders_enabled(self) -> bool:
        return bool(getattr(user_options.animations, "shaders", False))

    def set_shaders_enabled(self, enabled: bool) -> None:
        user_options.animations.shaders = bool(enabled)
        user_options.save()

    def get_active_pack(self) -> str | None:
        return user_options.animations.active_pack

    def set_pack(self, pack_name: str | None):
        user_options.animations.active_pack = pack_name
        user_options.save()

        if pack_name:
            meta = self._load_pack_meta(pack_name)
            if meta:
                self._apply_pack_defaults(meta)
        else:
            self._restore_builtin_defaults()

        for key in TRANSITION_KEYS:
            GLib.idle_add(self.emit, "transition-changed", key)

        GLib.idle_add(self.emit, "pack-changed", pack_name or "")

    def is_protected(self, pack_name: str | None) -> bool:
        return pack_name in PROTECTED_PACKS

    def uninstall_pack(self, pack_name: str) -> None:
        if self.is_protected(pack_name):
            return

        if self.get_active_pack() == pack_name:
            self.set_pack(None)

        pack_path = Path(LOCAL_PACKS_DIR) / pack_name
        if pack_path.exists():
            shutil.rmtree(pack_path)

        GLib.idle_add(self.emit, "pack-uninstalled", pack_name)

    def get_transition_settings(self, transition: str) -> dict:
        """Returns the current settings dict for a transition type."""
        return dict(getattr(user_options.animations, transition, {}))

    def set_transition_shader(self, transition: str, shader_filename: str) -> None:
        settings = getattr(user_options.animations, transition, None)
        if settings is None:
            logger.warning(f"[AnimationService] unknown transition '{transition}'")
            return
        settings["shader"] = shader_filename
        user_options.save()
        GLib.idle_add(self.emit, "transition-changed", transition)

    def set_transition_bezier(self, transition: str, bezier: list[float], which: str = "both") -> None:
        settings = getattr(user_options.animations, transition, None)
        if settings is None:
            return

        if "bezier" in settings:
            settings["bezier"] = bezier
        else:
            if which in ("open", "both"):
                settings["open_bezier"] = bezier
            if which in ("close", "both"):
                settings["close_bezier"] = bezier

        user_options.save()
        GLib.idle_add(self.emit, "transition-changed", transition)

    def set_transition_duration(self, transition: str, duration: float, which: str = "both") -> None:
        settings = getattr(user_options.animations, transition, None)
        if settings is None:
            return

        if "duration" in settings:
            settings["duration"] = duration
        else:
            if which in ("open", "both"):
                settings["open_duration"] = duration
            if which in ("close", "both"):
                settings["close_duration"] = duration

        user_options.save()
        GLib.idle_add(self.emit, "transition-changed", transition)

    def _easing_keys(self, settings: dict, which: str) -> list[tuple[str, str]]:
        if "bezier" in settings:
            return [("easing", "bezier")]
        sides = ("open", "close") if which == "both" else (which,)
        return [(f"{side}_easing", f"{side}_bezier") for side in sides]

    def get_default_bezier(self, transition: str, which: str = "both") -> list[float]:
        bezier_key = "bezier" if which == "both" else f"{which}_bezier"

        pack_name = self.get_active_pack()
        if pack_name:
            meta = self._load_pack_meta(pack_name) or {}
            pack_defaults = meta.get(transition, {})
            if bezier_key in pack_defaults:
                return list(pack_defaults[bezier_key])

        builtin = getattr(type(user_options.animations)(), transition, {})
        return list(builtin.get(bezier_key, [0.4, 0.0, 0.2, 1.0]))

    def get_transition_easing(self, transition: str, which: str = "both") -> str:
        settings = getattr(user_options.animations, transition, None)
        if settings is None:
            return DEFAULT_EASING

        easing_key, bezier_key = self._easing_keys(settings, which)[0]
        stored = settings.get(easing_key)
        if stored in EASING_LABELS:
            return stored

        bezier = settings.get(bezier_key)
        if bezier:
            if list(bezier) == self.get_default_bezier(transition, which):
                return DEFAULT_EASING
            for key, preset in EASING_PRESETS.items():
                if all(abs(a - b) < 1e-6 for a, b in zip(bezier, preset)):
                    return key
        return DEFAULT_EASING

    def set_transition_easing(self, transition: str, easing: str, which: str = "both") -> None:
        settings = getattr(user_options.animations, transition, None)
        if settings is None or easing not in EASING_LABELS:
            return

        for easing_key, bezier_key in self._easing_keys(settings, which):
            side = "both" if bezier_key == "bezier" else bezier_key.removesuffix("_bezier")
            settings[easing_key] = easing
            settings[bezier_key] = (
                list(EASING_PRESETS[easing]) if easing in EASING_PRESETS
                else self.get_default_bezier(transition, side)
            )

        user_options.save()
        GLib.idle_add(self.emit, "transition-changed", transition)

    def get_frag_src(self, transition: str) -> str | None:
        pack_name = self.get_active_pack()
        if not pack_name:
            return None

        settings = getattr(user_options.animations, transition, {})
        shader_file = settings.get("shader")
        if not shader_file:
            return None

        shader_path = os.path.join(LOCAL_PACKS_DIR, pack_name, "shaders", shader_file)
        if not os.path.isfile(shader_path):
            logger.warning(f"[AnimationService] shader not found: {shader_path}")
            return None

        try:
            with open(shader_path) as f:
                return f.read()
        except Exception as e:
            logger.error(f"[AnimationService] failed to read shader {shader_path}: {e}")
            return None

    def _load_pack_meta(self, pack_name: str) -> dict | None:
        meta_path = os.path.join(LOCAL_PACKS_DIR, pack_name, "meta.json")
        if not os.path.isfile(meta_path):
            return None
        try:
            with open(meta_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[AnimationService] failed to read meta for {pack_name}: {e}")
            return None

    def _apply_pack_defaults(self, meta: dict) -> None:
        for key in TRANSITION_KEYS:
            pack_defaults = meta.get(key, {})
            if not pack_defaults:
                continue
            settings = getattr(user_options.animations, key, None)
            if settings is None:
                continue
            for field, value in pack_defaults.items():
                if field.endswith("bezier"):
                    which = "both" if field == "bezier" else field.removesuffix("_bezier")
                    if self.get_transition_easing(key, which) != DEFAULT_EASING:
                        continue
                settings[field] = value

        user_options.save()

    def _restore_builtin_defaults(self) -> None:
        for key in TRANSITION_KEYS:
            settings = getattr(user_options.animations, key, None)
            if settings is None:
                continue
            for _, bezier_key in self._easing_keys(settings, "both"):
                which = "both" if bezier_key == "bezier" else bezier_key.removesuffix("_bezier")
                if self.get_transition_easing(key, which) == DEFAULT_EASING:
                    settings[bezier_key] = self.get_default_bezier(key, which)

        user_options.save()

    def _scan_local_packs(self) -> dict[str, dict]:
        local = {}
        if not os.path.isdir(LOCAL_PACKS_DIR):
            return local

        for entry in os.scandir(LOCAL_PACKS_DIR):
            if not entry.is_dir():
                continue
            meta_path = os.path.join(entry.path, "meta.json")
            if not os.path.exists(meta_path):
                continue
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                meta["name"]       = entry.name
                meta["local"]      = True
                meta["downloaded"] = True

                preview_cache = os.path.join(CACHE_DIR, f"{entry.name}_thumbnail.png")
                local_preview = os.path.join(entry.path, "thumbnail.png")
                meta["preview_path"] = (
                    preview_cache if os.path.exists(preview_cache)
                    else local_preview if os.path.exists(local_preview)
                    else None
                )
                local[entry.name] = meta
            except Exception as e:
                logger.warning(f"[AnimationService] skipping {entry.name}: {e}")

        return local

    def fetch_available_packs(self, force: bool = False):
        threading.Thread(
            target=lambda: asyncio.run(self._fetch_available_packs(force)),
            daemon=True,
        ).start()

    def download_pack(self, pack_name: str):
        threading.Thread(
            target=lambda: asyncio.run(self._download_pack(pack_name)),
            daemon=True,
        ).start()

    async def _fetch_available_packs(self, force: bool = False):
        try:
            local_packs = self._scan_local_packs()

            async with make_session() as session:
                entries = await fetch_json(
                    session,
                    f"{GITHUB_API}/repos/{REPO}/contents/",
                    headers={"Accept": "application/vnd.github+json"},
                    force=force,
                )

                dirs = [e for e in entries if e["type"] == "dir"]
                remote_packs = await asyncio.gather(
                    *[self._fetch_pack_meta(session, d["name"], force) for d in dirs]
                )

            merged: dict[str, dict] = {}
            for pack in remote_packs:
                if pack is None:
                    continue
                name = pack["name"]
                merged[name] = (
                    {**pack, **local_packs[name], "downloaded": True}
                    if name in local_packs
                    else {**pack, "local": False, "downloaded": False}
                )
            for name, meta in local_packs.items():
                if name not in merged:
                    merged[name] = {**meta, "downloaded": True}

            GLib.idle_add(self.emit, "packs-loaded", list(merged.values()))

        except Exception as e:
            local_packs = self._scan_local_packs()
            if local_packs:
                GLib.idle_add(self.emit, "packs-loaded",
                              [{**m, "downloaded": True} for m in local_packs.values()])
            GLib.idle_add(self.emit, "error", friendly_error(e))

    async def _fetch_pack_meta(self, session: aiohttp.ClientSession, pack_name: str, force: bool = False):
        try:
            raw_base = f"https://raw.githubusercontent.com/{REPO}/main/{pack_name}"

            meta = await fetch_json(session, f"{raw_base}/meta.json", force=force)

            meta["name"] = pack_name

            preview_cache_path = os.path.join(CACHE_DIR, f"{pack_name}_thumbnail.png")
            if not os.path.exists(preview_cache_path):
                data = await fetch_bytes(session, f"{raw_base}/thumbnail.png", force=force)
                if data:
                    with open(preview_cache_path, "wb") as f:
                        f.write(data)

            meta["preview_path"] = (
                preview_cache_path if os.path.exists(preview_cache_path) else None
            )
            return meta

        except Exception as e:
            logger.warning(f"[AnimationService] skipping remote {pack_name}: {e}")
            return None

    async def _download_pack(self, pack_name: str):
        try:
            pack_dir = os.path.join(LOCAL_PACKS_DIR, pack_name)
            os.makedirs(pack_dir, exist_ok=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{GITHUB_API}/repos/{REPO}/git/trees/main:{pack_name}",
                    params={"recursive": "1"},
                    headers={"Accept": "application/vnd.github+json"},
                ) as resp:
                    resp.raise_for_status()
                    tree = await resp.json()

                files = [item for item in tree["tree"] if item["type"] == "blob"]
                await asyncio.gather(
                    *[self._download_file(session, pack_name, pack_dir, f["path"])
                      for f in files]
                )

            GLib.idle_add(self.emit, "pack-downloaded", pack_name)

        except Exception as e:
            GLib.idle_add(self.emit, "error", f"Couldn't download {pack_name}. {friendly_error(e)}")

    async def _download_file(self, session, pack_name, pack_dir, relative_path):
        url  = f"https://raw.githubusercontent.com/{REPO}/main/{pack_name}/{relative_path}"
        dest = os.path.join(pack_dir, relative_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
            with open(dest, "wb") as f:
                f.write(data)


animation_service = AnimationService.get_instance()