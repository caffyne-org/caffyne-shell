import os
import json
from loguru import logger
from fabric.utils import get_relative_path

CONFIG_PATH = os.path.expanduser("~/.config/caffyne-shell/config/config.json")


class UserOptions:
    class User:
        def __init__(self):
            self.avatar = f"/var/lib/AccountsService/icons/{os.getenv('USER')}"

    class Settings:
        def __init__(self):
            self.dnd = False

    class Bars:
        def __init__(self):
            self.configs = [
                {
                    "monitor": 0,
                    "bars": [
                        {
                            "alignment": "bottom",
                            "floating_bar": False,
                            "floating_applets": True,
                            "rounded_edges": True,
                            "min_width": False,
                            "auto_hide": False,
                            "left": [
                                "Dash",
                                {"widget": "Launcher", "variant": "icon"},
                                {"widget": "Processes", "variant": "scale"},
                                "Weather",
                                "Media"
                            ],
                            "center": ["Dock"],
                            "right": [
                                "Tray",
                                "Calendar",
                                {"widget": "Clock", "variant": "icon+label"},
                                {"widget": "Settings", "variant": "single"},
                                "Notifications"
                            ]
                        }
                    ],
                    "alignment": "bottom",
                    "floating_bar": True
                },
                {
                    "monitor": 1,
                    "bars": [
                        {
                            "alignment": "bottom",
                            "floating_bar": False,
                            "floating_applets": True,
                            "rounded_edges": True,
                            "min_width": False,
                            "auto_hide": False,
                            "left": [
                                "Dash",
                                {"widget": "Launcher", "variant": "icon"},
                                {"widget": "Processes", "variant": "scale"},
                                "Weather",
                                "Media"
                            ],
                            "center": ["Dock"],
                            "right": [
                                "Tray",
                                "Calendar",
                                {"widget": "Clock", "variant": "icon+label"},
                                {"widget": "Settings", "variant": "single"},
                                "Notifications"
                            ]
                        }
                    ],
                    "alignment": "bottom",
                    "floating_bar": True
                },
            ]

    class WorldClocks:
        def __init__(self):
            self.clocks = [
                "Europe/London",
                "Europe/Paris"
            ]

    class Dock:
        def __init__(self):
            self.entries = []

    class IdleTimeouts:
        def __init__(self):
            self.list = [
                {"name": "screen-off", "timeout_ac": 10, "timeout_bat": 2, "enabled": True},
                {"name": "lock", "timeout_ac": 15, "timeout_bat": 5, "enabled": True},
                {"name": "suspend", "timeout_ac": 15, "timeout_bat": 10, "enabled": True}
            ]

    class Theme:
        def __init__(self):
            self.light_theme = "default"
            self.dark_theme = "default"
            self.active_accent = "accent4"
            self.is_dark = True
            self.scheme_type = "scheme-tonal-spot"
            self.opacity = 1.0
            self.blur = False
            self.border_style = "medium"
            self.font_monospace_style = "none"
            self.icon_pack = "default"
            self.style_pack = None
            self.sound_pack = None

    class Templates:
        def __init__(self):
            self.enabled: list[str] = []

    class Launcher:
        def __init__(self):
            self.grid = False

    class Wallpaper:
        def __init__(self):
            self.path = f"{get_relative_path('wallpapers/wall14.jpg')}"
            # Directory the wallpaper pickers list images from.
            self.folder = f"{get_relative_path('wallpapers')}"
            # How awww scales the image onto the output:
            # "crop" (fill), "fit", "stretch" or "no".
            self.resize = "crop"

    class DesktopApplets:
        def __init__(self):
            self.applets: list[dict] = []

        def get_applets(self) -> list[dict]:
            return self.applets

        def place(self, key: str, slot: int) -> bool:
            if any(e["key"] == key for e in self.applets):
                return False
            self.applets.append({"key": key, "slot": slot})
            return True

        def remove(self, key: str) -> bool:
            new_applets = [e for e in self.applets if e["key"] != key]
            if len(new_applets) == len(self.applets):
                return False
            self.applets = new_applets
            return True

        def update_slot(self, key: str, slot: int) -> None:
            for e in self.applets:
                if e["key"] == key:
                    e["slot"] = slot
                    break

        def is_placed(self, key: str) -> bool:
            return any(e["key"] == key for e in self.applets)

    class DesktopCanvas:
        def __init__(self):
            self.placements: dict[str, list[dict]] = {}

        def get_applets(self, monitor_id: int) -> list[dict]:
            return self.placements.get(str(monitor_id), [])

        def is_placed(self, monitor_id: int, key: str) -> bool:
            return any(e["key"] == key for e in self.get_applets(monitor_id))

        @staticmethod
        def _compute_anchor(grid_x: int, cc: int, cols: int) -> tuple[str, int]:
            left_boundary  = int(cols * 0.4)
            right_boundary = int(cols * 0.6)
            center_col     = cols // 2

            if grid_x < left_boundary:
                return "left", grid_x
            elif grid_x >= right_boundary:
                return "right", cols - grid_x - cc
            else:
                return "center", grid_x - center_col

        def place(self, monitor_id: int, key: str, grid_x: int, grid_y: int, cols: int, ry: float) -> bool:
            mid = str(monitor_id)
            if any(e["key"] == key for e in self.placements.get(mid, [])):
                return False
            from desktop_applets import DESKTOP_CANVAS_SIZES
            base_cols, _ = DESKTOP_CANVAS_SIZES.get(key, (1, 1))
            cc = base_cols * 2
            ax, dx = self._compute_anchor(grid_x, cc, cols)
            self.placements.setdefault(mid, []).append(
                {"key": key, "grid_x": grid_x, "grid_y": grid_y, "ax": ax, "dx": dx, "ry": ry}
            )
            return True

        def remove(self, monitor_id: int, key: str) -> bool:
            mid = str(monitor_id)
            before = self.placements.get(mid, [])
            after  = [e for e in before if e["key"] != key]
            if len(after) == len(before):
                return False
            self.placements[mid] = after
            return True

        def move(self, monitor_id: int, key: str, grid_x: int, grid_y: int, cols: int) -> None:
            from desktop_applets import DESKTOP_CANVAS_SIZES
            for e in self.placements.get(str(monitor_id), []):
                if e["key"] == key:
                    base_cols, _ = DESKTOP_CANVAS_SIZES.get(key, (1, 1))
                    cc = base_cols * 2
                    ax, dx = self._compute_anchor(grid_x, cc, cols)
                    e["grid_x"] = grid_x
                    e["grid_y"] = grid_y
                    e["ax"]     = ax
                    e["dx"]     = dx
                    break

        def clear_monitor(self, monitor_id: int) -> None:
            self.placements.pop(str(monitor_id), None)

        def resolve(self, monitor_id: int, cols: int, rows: int) -> None:
            from desktop_applets import DESKTOP_CANVAS_SIZES

            def _applet_cell_size(key: str) -> tuple[int, int]:
                base_cols, base_rows = DESKTOP_CANVAS_SIZES.get(key, (1, 1))
                return base_cols * 2, base_rows * 2

            def _cells(gx: int, gy: int, cc: int, cr: int) -> set[tuple[int, int]]:
                return {(gx + dx, gy + dy) for dx in range(cc) for dy in range(cr)}

            center_col = cols // 2
            entries    = self.placements.get(str(monitor_id), [])
            occupied: set[tuple[int, int]] = set()

            for entry in entries:
                key = entry["key"]
                ry  = entry.get("ry", 0.0)
                cc, cr = _applet_cell_size(key)

                ax = entry.get("ax")
                if ax == "left":
                    gx = max(0, min(entry["dx"], cols - cc))
                elif ax == "right":
                    gx = max(0, min(cols - entry["dx"] - cc, cols - cc))
                elif ax == "center":
                    gx = max(0, min(center_col + entry["dx"], cols - cc))
                else:
                    rx = entry.get("rx", 0.0)
                    gx = max(0, min(round(rx * cols), cols - cc))
                    ax, dx = self._compute_anchor(gx, cc, cols)
                    entry["ax"] = ax
                    entry["dx"] = dx
                    entry.pop("rx", None)

                gy = max(0, min(round(ry * rows), rows - cr))

                candidate_gy = gy
                while _cells(gx, candidate_gy, cc, cr) & occupied:
                    candidate_gy += 1
                    if candidate_gy + cr > rows:
                        candidate_gy = gy
                        break

                entry["grid_x"] = gx
                entry["grid_y"] = candidate_gy
                occupied |= _cells(gx, candidate_gy, cc, cr)

    class Plugins:
        def __init__(self):
            self.enabled: list[str] = []

        def enable(self, name: str) -> None:
            if name not in self.enabled:
                self.enabled.append(name)

        def disable(self, name: str) -> None:
            self.enabled = [n for n in self.enabled if n != name]

        def is_enabled(self, name: str) -> bool:
            return name in self.enabled
    class Animations:
        def __init__(self):
            self.active_pack: str | None = "default"
            self.shaders: bool = False
            self.applet_reveal = {
                "shader": "applet_reveal.frag",
                "open_bezier":   [0.17, 0.67, 0, 1],
                "close_bezier":  [0.16, 1.0, 0.3, 1.0],
                "open_easing":   "default",
                "close_easing":  "default",
                "open_duration":  0.3,
                "close_duration": 0.2,
            }
            self.dash_reveal = {
                "shader": "dash_reveal.frag",
                "open_bezier":   [0.16, 1.0, 0.3, 1.0],
                "close_bezier":  [0.16, 1.0, 0.3, 1.0],
                "open_easing":   "default",
                "close_easing":  "default",
                "open_duration":  0.3,
                "close_duration": 0.3,
            }
            self.stack_transition = {
                "shader":   "stack_transition.frag",
                "bezier":   [0.4, 0.0, 0.2, 1.0],
                "easing":   "default",
                "duration": 0.25,
            }
    def __init__(self):
        self.user = self.User()
        self.settings = self.Settings()
        self.bars = self.Bars()
        self.timeouts = self.IdleTimeouts()
        self.theme = self.Theme()
        self.templates = self.Templates()
        self.launcher = self.Launcher()
        self.dock = self.Dock()
        self.world_clocks = self.WorldClocks()
        self.wallpaper = self.Wallpaper()
        self.desktop_applets = self.DesktopApplets()
        self.desktop_canvas = self.DesktopCanvas()
        self.plugins = self.Plugins()
        self.animations = self.Animations()
        self._load()

    def _load(self) -> None:
        if not os.path.isfile(CONFIG_PATH):
            logger.info(f"[UserOptions] no config found at {CONFIG_PATH}, using defaults")
            return

        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)

            for section, values in data.items():
                obj = getattr(self, section, None)
                if obj is None or not isinstance(values, dict):
                    continue

                for key, value in values.items():
                    if hasattr(obj, key):
                        setattr(obj, key, value)
                    else:
                        logger.warning(f"[UserOptions] unknown key '{section}.{key}', skipping")

            logger.info(f"[UserOptions] loaded config from {CONFIG_PATH}")

        except Exception as e:
            logger.error(f"[UserOptions] failed to load config: {e}")

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)

            data = {
                section: vars(getattr(self, section))
                for section in (
                    "user",
                    "settings",
                    "bars",
                    "timeouts",
                    "theme",
                    "launcher",
                    "dock",
                    "world_clocks",
                    "wallpaper",
                    "templates",
                    "desktop_applets",
                    "desktop_canvas",
                    "plugins",
                    "animations"
                )
            }

            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w") as f:
                json.dump(data, f, indent=2)

            os.replace(tmp, CONFIG_PATH)

            logger.info(f"[UserOptions] saved config to {CONFIG_PATH}")

        except Exception as e:
            logger.error(f"[UserOptions] failed to save config: {e}")


user_options = UserOptions()
