import os
import json
import asyncio
import aiohttp
import threading
import importlib.util
import sys
from pathlib import Path
from fabric.core.service import Service, Signal
from fabric.utils import monitor_file
from gi.repository import GLib, Gdk
from user_options import user_options
from services.pack_fetch import fetch_bytes, fetch_json, friendly_error, make_session


GITHUB_API = "https://api.github.com"
REPO = "caffyne-org/caffyne-plugins"
PLUGIN_DIR = Path.home() / ".config" / "caffyne-shell" / "plugins"
CACHE_DIR = Path.home() / ".cache" / "caffyne-shell" / "plugins"


class PluginService(Service):
    @Signal
    def plugin_enabled(self, name: str): ...

    @Signal
    def plugin_disabled(self, name: str): ...

    @Signal
    def plugins_loaded(self, plugins: object): ...

    @Signal
    def plugin_downloaded(self, name: str): ...
    
    @Signal
    def plugin_uninstalled(self, name: str): ...

    @Signal
    def error(self, message: str): ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)

        self._bar_widgets: dict[str, type] = {}
        self._applet_widgets: dict[str, type] = {}
        self._incompatible_groups: set[frozenset] = set()
        self._bean_data: list = []
        self._desktop_widgets: dict[str, type] = {}
        self._desktop_canvas_sizes: dict[str, tuple[int, int]] = {}

        self._loaded: dict[str, object] = {}
        self._enabled: set[str] = set()
        self._keybinds: dict[str, callable] = {}
        self._css_monitors: list = []
        self._app = None

    # ── Init ──────────────────────────────────────────────────────────────

    def set_app(self, app) -> None:
        self._app = app


    def load_all(
        self,
        bar_widgets: dict,
        applet_widgets: dict,
        incompatible_groups: set,
        bean_data: list,
        desktop_widgets: dict,
        desktop_canvas_sizes: dict,
        desktop_applet_sizes: dict
    ) -> None:
        self._bar_widgets = bar_widgets
        self._applet_widgets = applet_widgets
        self._incompatible_groups = incompatible_groups
        self._bean_data = bean_data
        self._desktop_widgets = desktop_widgets
        self._desktop_canvas_sizes = desktop_canvas_sizes
        self._desktop_applet_sizes = desktop_applet_sizes

        if not PLUGIN_DIR.exists():
            return
        for path in sorted(PLUGIN_DIR.iterdir()):
            if path.is_dir() and (path / "__init__.py").exists():
                name = self._peek_name(path)
                should_enable = user_options.plugins.is_enabled(name)
                self._load_one(path, enable=should_enable)

    def apply_css(self, app) -> None:
        self._app = app
        if not PLUGIN_DIR.exists():
            return
        for path in sorted(PLUGIN_DIR.iterdir()):
            style = path / "style.css"
            if style.exists():
                app.set_stylesheet_from_file(str(style), append=True)
                monitor = monitor_file(str(path))
                monitor.connect(
                    "changed",
                    lambda *_, s=style: app.set_stylesheet_from_file(str(s), append=True),
                )
                self._css_monitors.append(monitor)

    def register_keybind(self, key: str, callback: callable) -> None:
        self._keybinds[key] = callback

    def unregister_keybind(self, key: str) -> None:
        self._keybinds.pop(key, None)

    def handle_keybind(self, key: str) -> bool:
        """Called by bar_manager.toggle() — returns True if handled."""
        if key in self._keybinds:
            self._keybinds[key]()
            return True
        return False

    def enable_plugin(self, name: str) -> bool:
        if name in self._enabled:
            return True
        path = self._find_plugin_path(name)
        if path is None:
            GLib.idle_add(self.emit, "error", f"Plugin '{name}' not found")
            return False
        if name not in self._loaded:
            if not self._load_one(path, enable=False):
                return False
        self._register_plugin(name)
        self._enabled.add(name)
        user_options.plugins.enable(name)
        user_options.save()
        GLib.idle_add(self.emit, "plugin-enabled", name)
        return True
    
    def disable_plugin(self, name: str) -> None:
        if name not in self._enabled:
            return
        self._unregister_plugin(name)
        self._enabled.discard(name)

        user_options.plugins.disable(name)
        user_options.desktop_applets.remove(name)
        for i in range(Gdk.Display.get_default().get_n_monitors()):
            user_options.desktop_canvas.remove(i, name)
        user_options.save()

        GLib.idle_add(self.emit, "plugin-disabled", name)

    def is_enabled(self, name: str) -> bool:
        return name in self._enabled

    def uninstall_plugin(self, name: str) -> None:
        if name in self._enabled:
            self.disable_plugin(name)

        path = self._find_plugin_path(name)
        if path is not None:
            import shutil
            shutil.rmtree(path)

        self._loaded.pop(name, None)

        GLib.idle_add(self.emit, "plugin-uninstalled", name)

    def _load_one(self, path: Path, enable: bool = True) -> bool:
        module_name = f"caffyne_plugin_{path.name}"
        try:
            spec = importlib.util.spec_from_file_location(
                module_name,
                path / "__init__.py",
                submodule_search_locations=[str(path)],
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
        except Exception as exc:
            print(f"[PluginService] Failed to load '{path.name}': {exc}")
            return False

        name: str = getattr(mod, "NAME", path.name)
        self._loaded[name] = mod

        if enable:
            self._register_plugin(name)
            self._enabled.add(name)

        return True
    def _register_plugin(self, name: str) -> None:
        mod = self._loaded.get(name)
        if mod is None:
            return

        if hasattr(mod, "BAR_WIDGET"):
            self._bar_widgets[name] = mod.BAR_WIDGET
            print(f"[PluginService] {name} — bar widget registered")

        if hasattr(mod, "APPLET_WIDGET"):
            self._applet_widgets[name] = mod.APPLET_WIDGET
            print(f"[PluginService] {name} — applet registered")

        if hasattr(mod, "DESKTOP_WIDGET"):
            self._desktop_widgets[name] = mod.DESKTOP_WIDGET
            canvas = getattr(mod, "DESKTOP_CANVAS_SIZE", (1, 1))
            self._desktop_canvas_sizes[name] = canvas
            self._desktop_applet_sizes[name] = canvas[0]
            print(f"[PluginService] {name} — desktop widget registered")

        if hasattr(mod, "INCOMPATIBLE_WITH"):
            for other in mod.INCOMPATIBLE_WITH:
                self._incompatible_groups.add(frozenset({name, other}))
                print(f"[PluginService] {name} — incompatible with '{other}'")

        if hasattr(mod, "KEYBINDS"):
            for key, cb in mod.KEYBINDS.items():
                self.register_keybind(key, cb)
                print(f"[PluginService] {name} — keybind '{key}' registered")

        icon = getattr(mod, "ICON", "placeholder")
        has_widget = hasattr(mod, "BAR_WIDGET") or hasattr(mod, "APPLET_WIDGET") or hasattr(mod, "DESKTOP_WIDGET")
        if has_widget and not any(k == name for _, k in self._bean_data):
            self._bean_data.append((icon, name))
            print(f"[PluginService] {name} — added to bean data")
        if self._app is not None:
            style = self._find_plugin_path(name)
            if style:
                css = style / "style.css"
                if css.exists():
                    self._app.set_stylesheet_from_file(str(css), append=True)

    def _unregister_plugin(self, name: str) -> None:
        self._bar_widgets.pop(name, None)
        self._applet_widgets.pop(name, None)
        self._desktop_widgets.pop(name, None)
        self._desktop_canvas_sizes.pop(name, None)
        self._desktop_applet_sizes.pop(name, None)
        self._incompatible_groups = {
            g for g in self._incompatible_groups if name not in g
        }

        mod = self._loaded.get(name)
        if mod and hasattr(mod, "KEYBINDS"):
            for key in mod.KEYBINDS:
                self.unregister_keybind(key)

        self._bean_data[:] = [(icon, k) for icon, k in self._bean_data if k != name]

        print(f"[PluginService] {name} — unregistered")

    def _peek_name(self, path: Path) -> str:
        """Read NAME from __init__.py without executing the module."""
        try:
            init = (path / "__init__.py").read_text()
            for line in init.splitlines():
                if line.startswith("NAME"):
                    return line.split("=")[1].strip().strip('"').strip("'")
        except Exception:
            pass
        return path.name

    def fetch_available_plugins(self, force: bool = False):
        threading.Thread(
            target=lambda: asyncio.run(self._fetch_available_plugins(force)),
            daemon=True,
        ).start()

    def download_plugin(self, plugin_name: str):
        threading.Thread(
            target=lambda: asyncio.run(self._download_plugin(plugin_name)),
            daemon=True,
        ).start()

    def _scan_local_plugins(self) -> dict[str, dict]:
        local = {}
        if not PLUGIN_DIR.exists():
            return local
        for entry in PLUGIN_DIR.iterdir():
            if not entry.is_dir():
                continue
            meta_path = entry / "meta.json"
            if not meta_path.exists():
                continue
            try:
                dir_name = entry.name
                with open(meta_path) as f:
                    meta = json.load(f)
                
                meta["name"] = dir_name
                meta["display_name"] = meta.get("display_name", self._peek_name(entry))
                meta["local"] = True
                meta["enabled"] = dir_name in self._enabled or self._peek_name(entry) in self._enabled

                preview_cache = CACHE_DIR / f"{dir_name}_thumbnail.png"
                local_preview = entry / "thumbnail.png"
                if preview_cache.exists():
                    meta["preview_path"] = str(preview_cache)
                elif local_preview.exists():
                    meta["preview_path"] = str(local_preview)
                else:
                    meta["preview_path"] = None

                local[dir_name] = meta
            except Exception as e:
                print(f"[PluginService] Skipping local plugin {entry.name}: {e}")
        return local



    def _find_plugin_path(self, name: str) -> Path | None:
        if not PLUGIN_DIR.exists():
            return None
        direct_path = PLUGIN_DIR / name
        if direct_path.exists():
            return direct_path
        for path in PLUGIN_DIR.iterdir():
            if path.is_dir() and (path / "__init__.py").exists():
                if path.name.lower() == name.lower() or self._peek_name(path) == name:
                    return path
        return None

    async def _fetch_plugin_meta(self, session: aiohttp.ClientSession, plugin_name: str, force: bool = False):
        try:
            raw_base = f"https://raw.githubusercontent.com/{REPO}/main/{plugin_name}"

            meta = await fetch_json(session, f"{raw_base}/meta.json", force=force)

            meta["name"] = plugin_name

            preview_cache = CACHE_DIR / f"{plugin_name}_thumbnail.png"
            if not preview_cache.exists():
                data = await fetch_bytes(session, f"{raw_base}/thumbnail.png", force=force)
                if data:
                    preview_cache.write_bytes(data)

            meta["preview_path"] = str(preview_cache) if preview_cache.exists() else None
            return meta

        except Exception as e:
            print(f"[PluginService] Skipping remote {plugin_name}: {e}")
            return None

    async def _fetch_available_plugins(self, force: bool = False):
        try:
            local = self._scan_local_plugins()

            async with make_session() as session:
                entries = await fetch_json(
                    session,
                    f"{GITHUB_API}/repos/{REPO}/contents/",
                    headers={"Accept": "application/vnd.github+json"},
                    force=force,
                )

                dirs = [e for e in entries if e["type"] == "dir"]
                remote = await asyncio.gather(
                    *[self._fetch_plugin_meta(session, d["name"], force) for d in dirs]
                )

            merged: dict[str, dict] = {}
            for plugin in remote:
                if plugin is None:
                    continue
                name = plugin["name"]
                if name in local:
                    merged[name] = {
                        **plugin,
                        **local[name],
                        "downloaded": True,
                        "enabled": name in self._enabled,
                    }
                else:
                    merged[name] = {
                        **plugin,
                        "downloaded": False,
                        "enabled": False,
                    }

            for name, meta in local.items():
                if name not in merged:
                    merged[name] = {
                        **meta,
                        "downloaded": True,
                        "enabled": name in self._enabled,
                    }

            GLib.idle_add(self.emit, "plugins-loaded", list(merged.values()))

        except Exception as e:
            local = self._scan_local_plugins()
            if local:
                packs = [
                    {**m, "downloaded": True, "enabled": n in self._enabled}
                    for n, m in local.items()
                ]
                GLib.idle_add(self.emit, "plugins-loaded", packs)
            GLib.idle_add(self.emit, "error", friendly_error(e))

    async def _download_plugin(self, plugin_name: str):
        try:
            plugin_dir = PLUGIN_DIR / plugin_name
            plugin_dir.mkdir(parents=True, exist_ok=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{GITHUB_API}/repos/{REPO}/git/trees/main:{plugin_name}",
                    params={"recursive": "1"},
                    headers={"Accept": "application/vnd.github+json"},
                ) as resp:
                    resp.raise_for_status()
                    tree = await resp.json()

                files = [item for item in tree["tree"] if item["type"] == "blob"]
                await asyncio.gather(
                    *[self._download_file(session, plugin_name, plugin_dir, f["path"]) for f in files]
                )

            GLib.idle_add(self.emit, "plugin-downloaded", plugin_name)

        except Exception as e:
            GLib.idle_add(self.emit, "error", f"Couldn't download {plugin_name}. {friendly_error(e)}")

    async def _download_file(
        self,
        session: aiohttp.ClientSession,
        plugin_name: str,
        plugin_dir: Path,
        relative_path: str,
    ):
        url = f"https://raw.githubusercontent.com/{REPO}/main/{plugin_name}/{relative_path}"
        dest = plugin_dir / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        async with session.get(url) as resp:
            resp.raise_for_status()
            dest.write_bytes(await resp.read())