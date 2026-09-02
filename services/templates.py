import json
import os
import threading
import asyncio
import aiohttp
import shutil
import subprocess
import re
from pathlib import Path

from fabric.utils import monitor_file
from fabric.core.service import Service, Signal
from gi.repository import GLib
from loguru import logger

from user_options import user_options
from services.pack_fetch import fetch_bytes, fetch_json, friendly_error, make_session

GITHUB_API            = "https://api.github.com"
REPO                  = "caffyne-org/caffyne-templates"
TEMPLATES_DIR         = os.path.expanduser("~/.config/caffyne-shell/templates")
CACHE_DIR             = os.path.expanduser("~/.cache/caffyne-shell/template_packs")

MATUGEN_CONFIG_CACHE = os.path.expanduser("~/.cache/caffyne-shell/matugen-templates.toml")
MATUGEN_CONFIG_DIR   = os.path.expanduser("~/.config/matugen")
MATUGEN_CONFIG_PATH  = os.path.join(MATUGEN_CONFIG_DIR, "config.toml")

TEMPLATES_REPO        = f"https://github.com/{REPO}"

class TemplatePackService(Service):
    allow_disable = True

    @Signal
    def packs_loaded(self, packs: object): ...

    @Signal
    def pack_downloaded(self, pack_name: str): ...

    @Signal
    def pack_changed(self, pack_name: str): ...

    @Signal
    def pack_enabled(self, pack_name: str): ...

    @Signal
    def pack_disabled(self, pack_name: str): ...

    @Signal
    def pack_uninstalled(self, pack_name: str): ...

    @Signal
    def error(self, message: str): ...

    _instance: "TemplatePackService | None" = None

    @staticmethod
    def get_instance() -> "TemplatePackService":
        if TemplatePackService._instance is None:
            TemplatePackService._instance = TemplatePackService()
        return TemplatePackService._instance

    def __init__(self):
        super().__init__()
        os.makedirs(TEMPLATES_DIR, exist_ok=True)
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._monitor       = monitor_file(TEMPLATES_DIR)
        self._pending_packs = []

    def get_pending_packs(self) -> list:
        return self._pending_packs

    @property
    def monitor(self):
        return self._monitor

    def get_active_pack(self) -> str | None:
        return None

    def is_enabled(self, template_id: str) -> bool:
        return template_id in user_options.templates.enabled

    def set_pack(self, pack_name: str | None) -> None:
        if pack_name is None:
            return
        if self.is_enabled(pack_name):
            self.disable_pack(pack_name)
        else:
            self.enable_pack(pack_name)

    def enable_pack(self, pack_name: str) -> None:
        self.set_enabled(pack_name, True)
        self.run_toggle_script(pack_name, True)
        self.build_matugen_config()
        GLib.idle_add(self.emit, "pack-enabled", pack_name)
        GLib.idle_add(self.emit, "pack-changed", pack_name)

    def disable_pack(self, pack_name: str) -> None:
        self.set_enabled(pack_name, False)
        self.run_toggle_script(pack_name, False)
        self.build_matugen_config()
        GLib.idle_add(self.emit, "pack-disabled", pack_name)
        GLib.idle_add(self.emit, "pack-changed", pack_name)

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

    def uninstall_pack(self, pack_name: str) -> None:
        if self.is_enabled(pack_name):
            self.set_enabled(pack_name, False)
            self.run_toggle_script(pack_name, False)
            self.build_matugen_config()

        pack_path = Path(TEMPLATES_DIR) / pack_name
        if pack_path.exists():
            shutil.rmtree(pack_path)

        GLib.idle_add(self.emit, "pack-uninstalled", pack_name)

    def set_enabled(self, template_id: str, enabled: bool) -> None:
        current = set(user_options.templates.enabled)
        if enabled:
            current.add(template_id)
        else:
            current.discard(template_id)
        user_options.templates.enabled = list(current)
        user_options.save()
        logger.info(f"[TemplatePackService] '{template_id}' {'enabled' if enabled else 'disabled'}")

    def run_toggle_script(self, template_id: str, enabled: bool) -> None:
        templates = self.list_templates()
        template  = next((t for t in templates if t["id"] == template_id), None)
        if template is None:
            return

        script_name = "enable.sh" if enabled else "disable.sh"
        script_path = os.path.join(template["_folder"], script_name)

        if not os.path.isfile(script_path):
            logger.info(f"[TemplatePackService] no {script_name} for '{template_id}', skipping")
            return

        def run():
            try:
                logger.info(f"[TemplatePackService] running {script_name} for '{template_id}'")
                subprocess.run(["bash", script_path], capture_output=True, text=True)
            except Exception as e:
                logger.error(f"[TemplatePackService] toggle script failed for '{template_id}': {e}")

        threading.Thread(target=run, daemon=True).start()

    def list_templates(self) -> list[dict]:
        """Existing API — returns all locally installed template metadata dicts."""
        templates = []
        if not os.path.isdir(TEMPLATES_DIR):
            return templates

        for folder_name in sorted(os.listdir(TEMPLATES_DIR)):
            folder_path = os.path.join(TEMPLATES_DIR, folder_name)
            if not os.path.isdir(folder_path):
                continue
            meta_path = os.path.join(folder_path, "meta.json")
            if not os.path.isfile(meta_path):
                continue
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
            except Exception as e:
                logger.error(f"[TemplatePackService] failed to read {meta_path}: {e}")
                continue

            template_id     = meta.get("id", folder_name)
            meta["id"]      = template_id
            meta["_folder"] = folder_path
            meta["enabled"] = self.is_enabled(template_id)
            templates.append(meta)

        return templates

    def _scan_local_packs(self) -> dict[str, dict]:
        local = {}
        if not os.path.isdir(TEMPLATES_DIR):
            return local

        for entry in os.scandir(TEMPLATES_DIR):
            if not entry.is_dir():
                continue
            meta_path = os.path.join(entry.path, "meta.json")
            if not os.path.exists(meta_path):
                continue
            try:
                with open(meta_path) as f:
                    meta = json.load(f)

                template_id        = meta.get("id", entry.name)
                meta["id"]         = template_id
                meta["name"]       = template_id
                meta["_folder"]    = entry.path
                meta["local"]      = True
                meta["downloaded"] = True
                meta["enabled"]    = self.is_enabled(template_id)

                preview_cache = os.path.join(CACHE_DIR, f"{entry.name}_thumbnail.png")
                local_preview = os.path.join(entry.path, "thumbnail.png")

                if os.path.exists(preview_cache):
                    meta["preview_path"] = preview_cache
                elif os.path.exists(local_preview):
                    meta["preview_path"] = local_preview
                else:
                    meta["preview_path"] = None

                local[template_id] = meta

            except Exception as e:
                logger.warning(f"[TemplatePackService] Skipping local template {entry.name}: {e}")

        return local

    def build_matugen_config(self) -> str:
        templates = self.list_templates()
        enabled   = [t for t in templates if t.get("enabled")]

        managed_ids: set[str] = {"caffyne"}
        for t in enabled:
            sub_templates = t.get("templates")
            if sub_templates:
                for sub in sub_templates:
                    managed_ids.add(sub["id"])
            else:
                managed_ids.add(t["id"])

        lines = ["[config]", ""]

        lines.append("[templates.caffyne]")
        lines.append(f"input_path = '{os.path.expanduser('~/.config/caffyne-shell/style/caffyne-shell-colors.css')}'")
        lines.append(f"output_path = '{os.path.expanduser('~/.config/caffyne-shell/style/colors.css')}'")
        lines.append("")

        for t in enabled:
            folder        = t["_folder"]
            template_id   = t["id"]
            sub_templates = t.get("templates")

            if sub_templates:
                for sub in sub_templates:
                    sub_id      = sub["id"]
                    raw_input   = sub.get("input_path", "")
                    input_path  = os.path.join(folder, raw_input) if not os.path.isabs(raw_input) else raw_input
                    output_path = os.path.expanduser(sub.get("output_path", ""))

                    if not input_path or not output_path:
                        logger.warning(f"[TemplatePackService] '{sub_id}' missing paths, skipping")
                        continue

                    lines.append(f"[templates.{sub_id}]")
                    lines.append(f"input_path = '{input_path}'")
                    lines.append(f"output_path = '{output_path}'")

                    if post_hook_script := sub.get("post_hook_script"):
                        lines.append(f'post_hook = "bash {os.path.join(folder, post_hook_script)}"')
                    elif post_hook := sub.get("post_hook"):
                        lines.append(f'post_hook = "{post_hook}"')
                    lines.append("")
            else:
                raw_input   = t.get("input_path", "")
                input_path  = os.path.join(folder, raw_input) if not os.path.isabs(raw_input) else raw_input
                output_path = os.path.expanduser(t.get("output_path", ""))

                if not input_path or not output_path:
                    logger.warning(f"[TemplatePackService] '{template_id}' missing paths, skipping")
                    continue

                lines.append(f"[templates.{template_id}]")
                lines.append(f"input_path = '{input_path}'")
                lines.append(f"output_path = '{output_path}'")

                if post_hook_script := t.get("post_hook_script"):
                    lines.append(f'post_hook = "bash {os.path.join(t["_folder"], post_hook_script)}"')
                elif post_hook := t.get("post_hook"):
                    lines.append(f'post_hook = "{post_hook}"')
                lines.append("")

        existing = self._parse_existing_matugen_templates(exclude_ids=managed_ids)
        if existing:
            lines.append("# --- merged from ~/.config/matugen/config.toml ---")
            for block in existing:
                lines.append(block)
                lines.append("")

        try:
            os.makedirs(os.path.dirname(MATUGEN_CONFIG_CACHE), exist_ok=True)
            with open(MATUGEN_CONFIG_CACHE, "w") as f:
                f.write("\n".join(lines))
            logger.info(f"[TemplatePackService] wrote matugen config → {MATUGEN_CONFIG_CACHE}")
        except Exception as e:
            logger.error(f"[TemplatePackService] failed to write config: {e}")

        return MATUGEN_CONFIG_CACHE

    def _parse_existing_matugen_templates(self, exclude_ids: set[str]) -> list[str]:
        if not os.path.isfile(MATUGEN_CONFIG_PATH):
            return []
        try:
            with open(MATUGEN_CONFIG_PATH) as f:
                raw = f.read()
        except Exception as e:
            logger.warning(f"[TemplatePackService] could not read existing matugen config: {e}")
            return []

        blocks = re.split(r'(?=^\[templates\.)', raw, flags=re.MULTILINE)
        kept   = []

        for block in blocks:
            m = re.match(r'^\[templates\.([^\]]+)\]', block)
            if m is None:
                continue
            template_id = m.group(1)
            if template_id in exclude_ids:
                logger.info(f"[TemplatePackService] skipping managed template '{template_id}'")
                continue

            block = re.sub(
                r"(input_path\s*=\s*)'([^']+)'",
                lambda m: (
                    f"{m.group(1)}'{os.path.join(MATUGEN_CONFIG_DIR, m.group(2))}'"
                    if not os.path.isabs(m.group(2)) and not m.group(2).startswith("~")
                    else f"{m.group(1)}'{m.group(2)}'"
                ),
                block,
            )
            kept.append(block.rstrip())

        return kept

    def fetch_templates(self, callback: callable | None = None) -> None:
        def run():
            try:
                git_dir = os.path.join(TEMPLATES_DIR, ".git")
                if os.path.isdir(git_dir):
                    logger.info("[TemplatePackService] pulling latest templates")
                    cmd = ["git", "-C", TEMPLATES_DIR, "pull"]
                else:
                    logger.info("[TemplatePackService] cloning templates repo")
                    os.makedirs(TEMPLATES_DIR, exist_ok=True)
                    cmd = ["git", "clone", TEMPLATES_REPO, TEMPLATES_DIR]

                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    logger.info("[TemplatePackService] fetch successful")
                else:
                    logger.error(f"[TemplatePackService] fetch failed: {result.stderr.strip()}")

                if callback:
                    GLib.idle_add(callback, result.returncode == 0)

            except Exception as e:
                logger.error(f"[TemplatePackService] fetch exception: {e}")
                if callback:
                    GLib.idle_add(callback, False)

        threading.Thread(target=run, daemon=True).start()

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

            packs_list = list(merged.values())
            self._pending_packs = packs_list

            GLib.idle_add(self.emit, "packs-loaded", packs_list)

        except Exception as e:
            local_packs = self._scan_local_packs()
            packs_list = [{**m, "downloaded": True} for m in local_packs.values()]
            if packs_list:
                self._pending_packs = packs_list
                GLib.idle_add(self.emit, "packs-loaded", packs_list)
            GLib.idle_add(self.emit, "error", friendly_error(e))

    async def _fetch_pack_meta(self, session: aiohttp.ClientSession, pack_name: str, force: bool = False):
        try:
            raw_base = f"https://raw.githubusercontent.com/{REPO}/main/{pack_name}"

            meta = await fetch_json(session, f"{raw_base}/meta.json", force=force)

            meta["name"] = meta.get("id", pack_name)

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
            logger.warning(f"[TemplatePackService] Skipping remote {pack_name}: {e}")
            return None

    async def _download_pack(self, pack_name: str):
        try:
            pack_dir = os.path.join(TEMPLATES_DIR, pack_name)
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
        url  = f"https://raw.githubusercontent.com/{REPO}/main/{pack_name}/{relative_path}"
        dest = os.path.join(pack_dir, relative_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
            with open(dest, "wb") as f:
                f.write(data)


template_service = TemplatePackService.get_instance()