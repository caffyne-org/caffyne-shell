import os
import json
import asyncio
import aiohttp
import shutil
import threading
from pathlib import Path
from fabric.core.service import Service, Signal
from fabric.utils import exec_shell_command_async, get_relative_path
from gi.repository import GLib
from user_options import user_options
from services.pack_fetch import fetch_bytes, fetch_json, friendly_error, make_session

GITHUB_API = "https://api.github.com"
REPO = "caffyne-org/caffyne-sounds"
LOCAL_PACKS_DIR = os.path.expanduser("~/.config/caffyne-shell/sound_packs")
CACHE_DIR = os.path.expanduser("~/.cache/caffyne-shell/sound_packs")
DEFAULT_PACK = "default"

# The pack bundled with the shell. Every fallback path reads from it, so it is
# never offered for removal — the UI shows a lock in place of Remove and
# uninstall_pack refuses outright.
PROTECTED_PACKS = frozenset({"default"})


def _detect_player() -> str | None:
    for player in ("pw-play", "paplay"):
        if shutil.which(player):
            return player
    return None


_PLAYER = _detect_player()


class SoundPackService(Service):
    allow_disable = False

    @Signal
    def pack_changed(self, pack_name: str): ...

    @Signal
    def packs_loaded(self, packs: object): ...

    @Signal
    def pack_downloaded(self, pack_name: str): ...

    @Signal
    def pack_uninstalled(self, pack_name: str): ...

    @Signal
    def error(self, message: str): ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._active_pack = user_options.theme.sound_pack
        os.makedirs(LOCAL_PACKS_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)

    @property
    def active_pack(self):
        return self._active_pack

    def get_active_pack(self) -> str | None:
        return self._active_pack

    # ── Sound playback ────────────────────────────────────────────────────

    def get_sound_path(self, sound_name: str, pack: str | None = None) -> str:
        pack = pack or self._active_pack
        if pack is not None:
            pack_path = os.path.join(LOCAL_PACKS_DIR, pack, "sounds", f"{sound_name}.wav")
            if os.path.isfile(pack_path):
                return pack_path
        # Fall back to default pack (bundled with the shell)
        return get_relative_path(f"../sound_packs/{DEFAULT_PACK}/sounds/{sound_name}.wav")

    def play_sound(self, name: str) -> None:
        if _PLAYER is None:
            print("[SoundPackService] No audio player found (tried pw-play, paplay)")
            return
        exec_shell_command_async(f"{_PLAYER} {self.get_sound_path(name)}")

    # ── Pack management ───────────────────────────────────────────────────

    def set_pack(self, pack: str | None):
        self._active_pack = pack
        user_options.theme.sound_pack = pack
        user_options.save()
        self.emit("pack-changed", pack or "")

    # ── Public API ────────────────────────────────────────────────────────

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
        return pack_name in PROTECTED_PACKS

    def uninstall_pack(self, pack_name: str) -> None:
        if self.is_protected(pack_name):
            return

        if self._active_pack == pack_name:
            self.set_pack(None)

        pack_path = Path(LOCAL_PACKS_DIR) / pack_name
        if pack_path.exists():
            shutil.rmtree(pack_path)

        # Retain thumbnail cache so UI cards still display thumbnails after uninstall
        GLib.idle_add(self.emit, "pack-uninstalled", pack_name)

    # ── Local scanning ────────────────────────────────────────────────────

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
                meta["name"] = entry.name
                meta["local"] = True

                preview_cache = os.path.join(CACHE_DIR, f"{entry.name}_thumbnail.png")
                local_preview = os.path.join(entry.path, "thumbnail.png")
                if os.path.exists(preview_cache):
                    meta["preview_path"] = preview_cache
                elif os.path.exists(local_preview):
                    meta["preview_path"] = local_preview
                else:
                    meta["preview_path"] = None

                local[entry.name] = meta
            except Exception as e:
                print(f"[SoundPackService] Skipping local pack {entry.name}: {e}")

        return local

    # ── Async internals ───────────────────────────────────────────────────

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
                if name in local_packs:
                    merged[name] = {**pack, **local_packs[name], "downloaded": True}
                else:
                    merged[name] = {**pack, "local": False, "downloaded": False}

            for name, meta in local_packs.items():
                if name not in merged:
                    merged[name] = {**meta, "downloaded": True}

            GLib.idle_add(self.emit, "packs-loaded", list(merged.values()))

        except Exception as e:
            local_packs = self._scan_local_packs()
            if local_packs:
                packs = [{**m, "downloaded": True} for m in local_packs.values()]
                GLib.idle_add(self.emit, "packs-loaded", packs)
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
            print(f"[SoundPackService] Skipping remote {pack_name}: {e}")
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
                    *[self._download_file(session, pack_name, pack_dir, f["path"]) for f in files]
                )

            GLib.idle_add(self.emit, "pack-downloaded", pack_name)

        except Exception as e:
            GLib.idle_add(self.emit, "error", f"Couldn't download {pack_name}. {friendly_error(e)}")

    async def _download_file(
        self,
        session: aiohttp.ClientSession,
        pack_name: str,
        pack_dir: str,
        relative_path: str,
    ):
        url = f"https://raw.githubusercontent.com/{REPO}/main/{pack_name}/{relative_path}"
        dest = os.path.join(pack_dir, relative_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
            with open(dest, "wb") as f:
                f.write(data)