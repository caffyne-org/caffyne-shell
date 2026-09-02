import os
import json
import asyncio
import aiohttp
import shutil
import threading
import subprocess
from pathlib import Path
from gi.repository import GLib
from loguru import logger

from fabric.core.service import Service, Signal, Property
from user_options import user_options
from services.pack_fetch import fetch_bytes, fetch_json, friendly_error, make_session
from services.wallpaper import WallpaperService

wp = WallpaperService.get_instance()

GITHUB_API       = "https://api.github.com"
REPO             = "caffyne-org/caffyne-themes"

THEMES_DIR       = os.path.expanduser("~/.config/caffyne-shell/themes")
LIGHT_THEMES_DIR = os.path.join(THEMES_DIR, "light")
DARK_THEMES_DIR  = os.path.join(THEMES_DIR, "dark")
CACHE_DIR        = os.path.expanduser("~/.cache/caffyne-shell/theme_packs")

WALLPAPER_THEME  = "Matugen"

VARIANTS         = ("light", "dark")

PROTECTED_PACKS = frozenset({"default"})


class ThemePackService(Service):
    allow_disable = False

    @Signal
    def theme_changed(self) -> None: ...

    @Signal
    def accent_changed(self) -> None: ...

    @Signal
    def mode_changed(self) -> None: ...
    @Signal
    def pack_changed(self, pack_name: str) -> None: ...
    @Signal
    def packs_loaded(self, packs: object): ...

    @Signal
    def pack_downloaded(self, pack_name: str): ...

    @Signal
    def pack_uninstalled(self, pack_name: str): ...

    @Signal
    def error(self, message: str): ...

    @Property(bool, "read-write", default_value=True)
    def is_dark(self) -> bool:
        return self._is_dark

    @Property(str, "read-write", default_value="")
    def active_accent(self) -> str:
        return self._active_accent

    @Property(str, "read-write", default_value="")
    def scheme_type(self) -> str:
        return self._scheme_type

    @Property(object, "read-write")
    def current_theme_data(self) -> dict | None:
        return self._current_theme_data

    @Property(object, "read-write")
    def available_accents(self) -> list[str]:
        return self._available_accents

    _instance: "ThemePackService | None" = None

    @staticmethod
    def get_instance() -> "ThemePackService":
        if ThemePackService._instance is None:
            ThemePackService._instance = ThemePackService()
        return ThemePackService._instance

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._is_dark: bool                   = user_options.theme.is_dark
        self._active_accent: str              = user_options.theme.active_accent
        self._scheme_type: str                = user_options.theme.scheme_type
        self._current_theme_data: dict | None = None
        self._available_accents: list[str]    = []

        os.makedirs(LIGHT_THEMES_DIR, exist_ok=True)
        os.makedirs(DARK_THEMES_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)

        self._connect_wallpaper_service()

        self._load_current_theme()

    def _connect_wallpaper_service(self) -> None:
        try:
            wp.connect("wallpaper-changed", self._on_wallpaper_changed)
            logger.info("[ThemePackService] connected to WallpaperService")
        except Exception as e:
            logger.warning(f"[ThemePackService] could not connect to WallpaperService: {e}")

    def _on_wallpaper_changed(self, _service, _path: str) -> None:
        if self.active_is_wallpaper:
            logger.info("[ThemePackService] wallpaper changed, re-applying wallpaper theme")
            self.apply()

    def get_active_pack(self) -> str | None:
        name = self.active_theme_name
        if name is None:
            return None
        variant = "dark" if self._is_dark else "light"
        return f"{variant}/{name}"

    def toggle_dark_mode(self) -> None:
        self.apply_dark(not self._is_dark)

    def apply_dark(self, value: bool) -> None:
        self._is_dark = value
        user_options.theme.is_dark = value
        self.notify("is-dark")
        self.emit("mode-changed")
        self._load_current_theme()
        self.apply()

    def apply_light_theme(self, name: str) -> None:
        user_options.theme.light_theme = name
        user_options.save()
        self._load_current_theme()
        self.apply()
        self.emit("theme-changed")
        self.emit("pack-changed", name)

    def apply_dark_theme(self, name: str) -> None:
        user_options.theme.dark_theme = name
        user_options.save()
        self._load_current_theme()
        self.apply()
        self.emit("theme-changed")
        self.emit("pack-changed", name)

    def apply_accent(self, accent_name: str) -> None:
        if self._current_theme_data is None:
            return
        available = self._current_theme_data.get("accents", {}).get("available", {})
        if accent_name not in available:
            return
        self._active_accent = accent_name
        user_options.theme.active_accent = accent_name
        self.notify("active-accent")
        self.emit("accent-changed")
        self.apply()

    def set_scheme_type(self, scheme_type: str) -> None:
        self._scheme_type = scheme_type
        user_options.theme.scheme_type = scheme_type
        self.notify("scheme-type")
        self.apply()

    @property
    def active_is_wallpaper(self) -> bool:
        return self.active_theme_name == WALLPAPER_THEME

    @property
    def active_theme_name(self) -> str:
        return (
            user_options.theme.dark_theme
            if self._is_dark
            else user_options.theme.light_theme
        )

    def list_themes(self, dark: bool = False) -> list[str]:
        folder = DARK_THEMES_DIR if dark else LIGHT_THEMES_DIR
        if not os.path.isdir(folder):
            return []
        return sorted(
            entry.name
            for entry in os.scandir(folder)
            if entry.is_dir() and os.path.exists(os.path.join(entry.path, "theme.json"))
        )

    def load_theme_data(self, name: str, dark: bool) -> dict | None:
        if name == WALLPAPER_THEME:
            return None
        folder = DARK_THEMES_DIR if dark else LIGHT_THEMES_DIR
        theme_path = os.path.join(folder, name, "theme.json")
        if not os.path.isfile(theme_path):
            return None
        try:
            with open(theme_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[ThemePackService] failed to read {theme_path}: {e}")
            return None

    def apply(self) -> None:
        GLib.idle_add(self._apply)

    # ── Pack Browser API ──────────────────────────────────────────────────

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

    def is_protected(self, pack_name: str | None) -> bool:
        if not pack_name:
            return False
        return pack_name.rpartition("/")[2] in PROTECTED_PACKS

    def uninstall_pack(self, pack_name: str) -> None:
        if self.is_protected(pack_name):
            return

        variant, _, name = pack_name.partition("/")
        folder = DARK_THEMES_DIR if variant == "dark" else LIGHT_THEMES_DIR
        pack_path = Path(folder) / name

        if self.active_theme_name == name:
            if self._is_dark:
                self.apply_dark_theme(WALLPAPER_THEME)
            else:
                self.apply_light_theme(WALLPAPER_THEME)

        if pack_path.exists():
            shutil.rmtree(pack_path)

        GLib.idle_add(self.emit, "pack-uninstalled", pack_name)

    def _scan_local_packs(self, dark: bool | None = None) -> dict[str, dict]:
        local = {}
        variants = []
        
        if dark is None:
            variants = [(False, LIGHT_THEMES_DIR), (True, DARK_THEMES_DIR)]
        elif dark:
            variants = [(True, DARK_THEMES_DIR)]
        else:
            variants = [(False, LIGHT_THEMES_DIR)]

        for is_dark_variant, folder in variants:
            prefix = "dark" if is_dark_variant else "light"
            if not os.path.isdir(folder):
                continue
            for entry in os.scandir(folder):
                if not entry.is_dir():
                    continue

                theme_path = os.path.join(entry.path, "theme.json")
                if not os.path.exists(theme_path):
                    continue

                try:
                    with open(theme_path) as f:
                        meta = json.load(f)

                    key = f"{prefix}/{entry.name}"
                    meta["display_name"] = meta.get("name") or entry.name
                    meta["id"]           = entry.name
                    meta["name"]         = key
                    meta["variant"]      = prefix
                    meta["local"]        = True
                    meta["downloaded"]   = True

                    preview_cache = os.path.join(CACHE_DIR, f"{prefix}_{entry.name}_thumbnail.png")
                    local_preview = os.path.join(entry.path, "thumbnail.png")

                    if os.path.exists(preview_cache):
                        meta["preview_path"] = preview_cache
                    elif os.path.exists(local_preview):
                        meta["preview_path"] = local_preview
                    else:
                        meta["preview_path"] = None

                    local[key] = meta

                except Exception as e:
                    logger.warning(f"[ThemePackService] Skipping local theme {entry.name}: {e}")

        return local

    def set_pack(self, pack_name: str | None) -> None:
        if pack_name is None:
            return
        
        variant, _, name = pack_name.rpartition("/")
        target_name = name if name else pack_name

        if target_name == WALLPAPER_THEME:
            user_options.theme.light_theme = WALLPAPER_THEME
            user_options.theme.dark_theme = WALLPAPER_THEME
            user_options.save()
            self._load_current_theme()
            self.apply()
            self.emit("theme-changed")
            self.emit("pack-changed", WALLPAPER_THEME)
            return

        if self._is_dark:
            self.apply_dark_theme(target_name)
        else:
            self.apply_light_theme(target_name)
    def _load_current_theme(self) -> None:
        active_name = self.active_theme_name

        if active_name == WALLPAPER_THEME:
            self._current_theme_data = None
            self._available_accents  = []
            self.notify("current-theme-data")
            self.notify("available-accents")
            return

        data = self.load_theme_data(active_name, dark=self._is_dark)
        if data is None:
            self._current_theme_data = None
            self._available_accents  = []
            self.notify("current-theme-data")
            self.notify("available-accents")
            return

        self._current_theme_data = data
        accents = data.get("accents", {}).get("available", {})
        self._available_accents = list(accents.keys())

        if self._active_accent not in accents:
            default_acc = data.get("accents", {}).get("default", "")
            fallback    = default_acc if default_acc in accents else next(iter(accents), "")
            if fallback:
                self._active_accent = fallback
                user_options.theme.active_accent = fallback

        self.notify("current-theme-data")
        self.notify("available-accents")

    def _apply(self) -> bool:
        from services.templates import template_service, MATUGEN_CONFIG_CACHE

        mode        = "dark" if self._is_dark else "light"
        active_name = self.active_theme_name

        try:
            if active_name == WALLPAPER_THEME:
                wp_path = wp.wallpaper_path if wp else ""
                if not wp_path or not os.path.isfile(wp_path):
                    return GLib.SOURCE_REMOVE
                cmd = [
                    "matugen", "image", wp_path,
                    "-m", mode,
                    "-t", self._scheme_type,
                    "--source-color-index", "0",
                    "--opacity", str(user_options.theme.opacity),
                ]
            else:
                if self._current_theme_data is None:
                    return GLib.SOURCE_REMOVE

                matugen_json = self._build_matugen_json()
                if not matugen_json:
                    return GLib.SOURCE_REMOVE

                cache_path = os.path.expanduser("~/.cache/caffyne-shell/theme.json")
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w") as f:
                    json.dump(matugen_json, f, indent=2)

                cmd = [
                    "matugen", "json", cache_path,
                    "-m", mode,
                    "--opacity", str(user_options.theme.opacity),
                ]

            if not os.path.isfile(MATUGEN_CONFIG_CACHE):
                template_service.build_matugen_config()

            cmd += ["-c", MATUGEN_CONFIG_CACHE]
            subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        except FileNotFoundError:
            logger.error("[ThemePackService] matugen not found — is it installed?")
        except Exception as e:
            logger.error(f"[ThemePackService] unexpected error while applying theme: {e}")

        return GLib.SOURCE_REMOVE

    def _build_matugen_json(self) -> dict:
        if self._current_theme_data is None:
            return {}

        def opacity_to_hex(opacity: float) -> str:
            return f"{round(opacity * 255):02X}"

        raw_colors  = self._current_theme_data.get("colors", {})
        accents     = self._current_theme_data.get("accents", {})
        default_acc = accents.get("default", "")
        
        accent_name = (
            self._active_accent
            if self._active_accent in accents.get("available", {})
            else default_acc
        )
        accent_color = accents.get("available", {}).get(accent_name)
        alpha        = opacity_to_hex(user_options.theme.opacity)

        colors: dict = {}
        for key, variants in raw_colors.items():
            if not isinstance(variants, dict):
                continue
            
            light_obj = variants.get("light", {})
            dark_obj  = variants.get("dark", {})

            light_hex = light_obj.get("color") if isinstance(light_obj, dict) else None
            dark_hex  = dark_obj.get("color") if isinstance(dark_obj, dict) else None

            if not light_hex or not dark_hex:
                continue

            colors[key] = {
                "light":   {"color": light_hex + alpha},
                "default": {"color": dark_hex + alpha},
                "dark":    {"color": dark_hex + alpha},
            }

        if accent_color:
            for slot in ("primary", "source_color"):
                colors[slot] = {
                    "light":   {"color": accent_color + (alpha if slot == "primary" else "")},
                    "default": {"color": accent_color + (alpha if slot == "primary" else "")},
                    "dark":    {"color": accent_color + (alpha if slot == "primary" else "")},
                }

        return {"colors": colors}

    async def _fetch_available_packs(self, force: bool = False):
        try:
            local_packs = self._scan_local_packs()

            async with make_session() as session:
                listings = await asyncio.gather(
                    *[
                        fetch_json(
                            session,
                            f"{GITHUB_API}/repos/{REPO}/contents/{variant}",
                            headers={"Accept": "application/vnd.github+json"},
                            force=force,
                        )
                        for variant in VARIANTS
                    ],
                    return_exceptions=True,
                )

                if all(isinstance(entries, BaseException) for entries in listings):
                    raise listings[0]

                meta_tasks = []
                for variant, entries in zip(VARIANTS, listings):
                    if isinstance(entries, BaseException):
                        logger.warning(
                            f"[ThemePackService] couldn't list {variant}/: {entries}"
                        )
                        continue
                    meta_tasks += [
                        self._fetch_pack_meta(session, variant, e["name"], force)
                        for e in entries
                        if e["type"] == "dir"
                    ]

                remote_packs = await asyncio.gather(*meta_tasks)

            merged: dict[str, dict] = {}

            for pack in remote_packs:
                if pack is None:
                    continue
                name = pack["name"]
                if name in local_packs:
                    merged[name] = {**pack, **local_packs[name], "downloaded": True}
                else:
                    merged[name] = {**pack, "local": False, "downloaded": False}

            for name, meta in local_packs.items():
                if name not in merged:
                    merged[name] = {**meta, "downloaded": True}

            packs_list = list(merged.values())
            GLib.idle_add(self.emit, "packs-loaded", packs_list)

        except Exception as e:
            local_packs = self._scan_local_packs()
            if local_packs:
                packs = [{**m, "downloaded": True} for m in local_packs.values()]
                GLib.idle_add(self.emit, "packs-loaded", packs)
            GLib.idle_add(self.emit, "error", friendly_error(e))

    async def _fetch_pack_meta(
        self,
        session: aiohttp.ClientSession,
        variant: str,
        pack_name: str,
        force: bool = False,
    ):
        try:
            raw_base = f"https://raw.githubusercontent.com/{REPO}/main/{variant}/{pack_name}"

            meta = await fetch_json(session, f"{raw_base}/theme.json", force=force)

            key = f"{variant}/{pack_name}"
            meta["display_name"] = meta.get("name") or pack_name
            meta["id"]           = pack_name
            meta["name"]         = key
            meta["variant"]      = variant

            preview_cache_path = os.path.join(CACHE_DIR, f"{variant}_{pack_name}_thumbnail.png")
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
            logger.warning(f"[ThemePackService] Skipping remote {variant}/{pack_name}: {e}")
            return None

    async def _download_pack(self, pack_name: str):
        try:
            variant, _, name = pack_name.partition("/")
            if not name:
                variant, name = ("dark" if self._is_dark else "light"), pack_name

            dest_folder = DARK_THEMES_DIR if variant == "dark" else LIGHT_THEMES_DIR
            pack_dir    = os.path.join(dest_folder, name)
            os.makedirs(pack_dir, exist_ok=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{GITHUB_API}/repos/{REPO}/git/trees/main:{variant}/{name}",
                    params={"recursive": "1"},
                    headers={"Accept": "application/vnd.github+json"},
                ) as resp:
                    resp.raise_for_status()
                    tree = await resp.json()

                files = [item for item in tree["tree"] if item["type"] == "blob"]
                await asyncio.gather(
                    *[
                        self._download_file(session, f"{variant}/{name}", pack_dir, f["path"])
                        for f in files
                    ]
                )

            GLib.idle_add(self.emit, "pack-downloaded", pack_name)

        except Exception as e:
            GLib.idle_add(self.emit, "error", f"Couldn't download {pack_name}. {friendly_error(e)}")

    async def _download_file(
        self,
        session: aiohttp.ClientSession,
        repo_pack_path: str,
        pack_dir: str,
        relative_path: str,
    ):
        url  = f"https://raw.githubusercontent.com/{REPO}/main/{repo_pack_path}/{relative_path}"
        dest = os.path.join(pack_dir, relative_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
            with open(dest, "wb") as f:
                f.write(data)


# theme_service = ThemePackService.get_instance()