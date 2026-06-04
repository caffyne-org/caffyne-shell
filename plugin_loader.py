import importlib.util
import sys
from pathlib import Path
from fabric.utils import monitor_file

PLUGIN_DIRS = [
    Path(__file__).parent / "plugins",
    Path.home() / ".config" / "caffyne-shell" / "plugins",
]

_monitors = []

def apply_plugin_css(app) -> None:
    for plugin_dir in PLUGIN_DIRS:
        if not plugin_dir.exists():
            continue
        for path in sorted(plugin_dir.iterdir()):
            style = path / "style.css"
            if style.exists():
                app.set_stylesheet_from_file(str(style), append=True)
                monitor = monitor_file(str(path))
                monitor.connect("changed", lambda *_, s=style: app.set_stylesheet_from_file(str(s), append=True))
                _monitors.append(monitor)

def load_plugins(
    bar_widgets: dict,
    applet_widgets: dict,
    incompatible_groups: set | None = None,
    bean_data: list | None = None,
) -> None:
    for plugin_dir in PLUGIN_DIRS:
        if not plugin_dir.exists():
            continue

        for path in sorted(plugin_dir.iterdir()):
            if not path.is_dir() or not (path / "__init__.py").exists():
                continue

            _load_one(path, bar_widgets, applet_widgets, incompatible_groups, bean_data)


def _load_one(
    path: Path,
    bar_widgets: dict,
    applet_widgets: dict,
    incompatible_groups: set | None,
    bean_data: list | None,
) -> None:
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
        print(f"[plugins] failed to load '{path.name}': {exc}")
        return

    name: str = getattr(mod, "NAME", path.name)

    # Register bar widget
    if hasattr(mod, "BAR_WIDGET"):
        bar_widgets[name] = mod.BAR_WIDGET
        print(f"[plugins] {name} — bar widget registered")

    # Register applet
    if hasattr(mod, "APPLET_WIDGET"):
        applet_widgets[name] = mod.APPLET_WIDGET
        print(f"[plugins] {name} — applet registered")

    # Register incompatibility rules  e.g. INCOMPATIBLE_WITH = ["Settings", "Wifi"]
    if incompatible_groups is not None and hasattr(mod, "INCOMPATIBLE_WITH"):
        for other in mod.INCOMPATIBLE_WITH:
            incompatible_groups.add(frozenset({name, other}))
            print(f"[plugins] {name} — marked incompatible with '{other}'")
            
    # Register in Dash applet grid
    if bean_data is not None:
        icon = getattr(mod, "ICON", "placeholder-duotone")  # fallback icon
        if hasattr(mod, "BAR_WIDGET") or hasattr(mod, "APPLET_WIDGET"):
            if not any(k == name for _, k in bean_data):  # avoid duplicates
                bean_data.append((icon, name))
                print(f"[plugins] {name} — added to bean data")

    if not hasattr(mod, "BAR_WIDGET") and not hasattr(mod, "APPLET_WIDGET"):
        print(f"[plugins] '{path.name}' loaded but exported nothing (missing BAR_WIDGET / APPLET_WIDGET)")