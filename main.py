import bar
from setproctitle import setproctitle
from fabric import Application
from fabric.utils import get_relative_path, monitor_file
from services.wallpaper import WallpaperService
import services.singletons as singletons
from plugin_loader import load_plugins, apply_plugin_css
from gi.repository import GLib
setproctitle("caffyne-shell")

app = Application("caffyne-shell")

def apply_stylesheet(*_):
    app.set_stylesheet_from_file(
        file_path=get_relative_path("./style/style.css"),
    )

style_monitor = monitor_file(get_relative_path("./style"))
style_monitor.connect("changed", apply_stylesheet)

apply_stylesheet()
GLib.timeout_add(1000, apply_plugin_css, app)

bar_manager = bar.initialise_bars()
singletons.bar_manager = bar_manager
wallpaper_service = WallpaperService.get_instance()
wallpaper_service.set_bar_manager(bar_manager)
app.run()