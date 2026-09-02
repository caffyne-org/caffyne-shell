from fabric.audio.service import Audio
from fabric.notifications import Notifications
from fabric.bluetooth.service import BluetoothClient
from fabric.power_profiles import PowerProfiles

from .wm import get_wm_service
from .battery import Battery
from .brightness import Brightness
from .edit_mode import EditMode
from .player import PlayerManager
from .network import NetworkClient
from .weather import Weather
from .idle import SwayidleService
from .icon_pack import IconPackService
from .timer import TimerService
from .processes import ProcessMonitorService
from .plugin import PluginService
from .themes import ThemePackService
from .night_mode import NightModeService
from .recorder import RecorderService
from .bluetooth import BluetoothClient
from .sounds import SoundPackService
from .system_tray import SystemTray
from user_options import user_options
bar_manager = None
style_service = None
toggleable_windows: dict[str, object] = {}
audio = Audio()
notifications = Notifications()
bluetooth = BluetoothClient()
player_manager = PlayerManager()
power_profiles = PowerProfiles()
plugins = PluginService()
theme_service = ThemePackService()
wm = get_wm_service()
battery = Battery()
brightness = Brightness()
edit_mode = EditMode()
network = NetworkClient()
weather = Weather()
icon_pack = IconPackService()
idle = SwayidleService(rules=user_options.timeouts.list)
sound_packs = SoundPackService()
timer = TimerService()
process_monitor = ProcessMonitorService()
night_mode = NightModeService()
recorder = RecorderService()
watcher = SystemTray()
settings = None
idle.start()