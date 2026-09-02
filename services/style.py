import os
import json
import asyncio
import aiohttp
import threading
from pathlib import Path
from fabric.core.service import Service, Signal, Property
from fabric.utils import monitor_file
from gi.repository import GLib
from user_options import user_options
from services.pack_fetch import fetch_bytes, fetch_json, friendly_error, make_session

GITHUB_API = "https://api.github.com"
REPO = "caffyne-org/caffyne-styles"
LOCAL_PACKS_DIR = os.path.expanduser("~/.config/caffyne-shell/style_packs")
CACHE_DIR = os.path.expanduser("~/.cache/caffyne-shell/style_packs")

class StyleService(Service):
    allow_disable = False
    allow_deactivate = True

    @Signal
    def packs_loaded(self, packs: object): ...

    @Signal
    def pack_downloaded(self, pack_name: str): ...

    @Signal
    def pack_changed(self, pack_name: str): ...

    @Signal
    def pack_uninstalled(self, pack_name: str): ...

    @Signal
    def error(self, message: str): ...

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._style_changed = False
        self.style_monitor = monitor_file(os.path.expanduser("~/.config/caffyne-shell/style"))
        self.style_monitor.connect("changed", lambda *_: self.reload())

        os.makedirs(LOCAL_PACKS_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)

    def get_active_pack(self) -> str | None:
        return user_options.theme.style_pack

    def set_pack(self, pack: str | None):
        user_options.theme.style_pack = pack
        user_options.save()
        self.reload()
        self.emit("pack-changed", pack)

    def uninstall_pack(self, pack_name: str) -> None:
        import shutil

        if self.get_active_pack() == pack_name:
            self.set_pack(None)

        pack_path = Path(LOCAL_PACKS_DIR) / pack_name
        if pack_path.exists():
            shutil.rmtree(pack_path)

        # Do NOT unlink preview from CACHE_DIR so card preview stays intact!
        GLib.idle_add(self.emit, "pack-uninstalled", pack_name)

    def _reset_style_providers(self) -> None:
        while self.app.style_providers:
            self.app.reset_styles()

    def reload(self, *_):
        try:
            self._reset_style_providers()
            self.app.set_stylesheet_from_file(
                file_path=os.path.expanduser("~/.config/caffyne-shell/style/style.css"),
            )
            self._apply_style_pack()

            self._style_changed = not self._style_changed
            self.notify("style-changed")
        except Exception as e:
            print(f"[StyleService] Error reloading styles: {e}")

    def _apply_style_pack(self):
        pack = self.get_active_pack()
        if not pack:
            return
        pack_path = os.path.expanduser(
            f"~/.config/caffyne-shell/style_packs/{pack}/style/style.css"
        )
        if os.path.isfile(pack_path):
            self.app.set_stylesheet_from_file(file_path=pack_path, append=True)

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
                print(f"[StyleService] Skipping local pack {entry.name}: {e}")

        return local

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
            print(f"[StyleService] Skipping remote {pack_name}: {e}")
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