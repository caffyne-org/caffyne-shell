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
                "Africa/Addis_Ababa"
            ]

    class Wallpaper:
        def __init__(self):
            self.path = f"{get_relative_path('wallpapers/Ventura-dark.jpg')}"

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
            self.light_theme = "catppuccin-latte"
            self.dark_theme = "catppuccin-mocha"
            self.active_accent = "accent4"
            self.is_dark = True
            self.scheme_type = "scheme-tonal-spot"
            self.opacity = 1.0
            self.blur = False
            self.border_style = "medium"

    class WorldClocks:
        def __init__(self):
            self.clocks = [
                "Europe/London",
                "Europe/Paris"
            ]

    class Wallpaper:
        def __init__(self):
            self.path = f"{get_relative_path('wallpapers/wall14.jpg')}"

    def __init__(self):
        self.user = self.User()
        self.settings = self.Settings()
        self.bars = self.Bars()
        self.timeouts = self.IdleTimeouts()
        self.theme = self.Theme()
        self.dock = self.Dock()
        self.world_clocks = self.WorldClocks()
        self.wallpaper = self.Wallpaper()
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
                    "dock",
                    "world_clocks",
                    "wallpaper"
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
