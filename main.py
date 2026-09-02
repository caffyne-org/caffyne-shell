import bar
import services.singletons as singletons
from setproctitle import setproctitle
from fabric import Application
from services.wallpaper import WallpaperService
from services.style import StyleService
from utils.sounds import play_sound

setproctitle("caffyne-shell")

app = Application("caffyne-shell")

singletons.style_service = StyleService(app)

singletons.style_service.reload()

bar_manager = bar.initialise_bars()
singletons.bar_manager = bar_manager

wallpaper_service = WallpaperService.get_instance()
# wallpaper_service.set_bar_manager(bar_manager)
play_sound("session-start")
from settings.shell.app import ShellSettingsApp

singletons.settings = ShellSettingsApp()

app.run()