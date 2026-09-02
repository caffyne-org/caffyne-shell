from ..common.app import App, AppSection
from fabric.widgets.label import Label
from .sections.about import ShellInfoPage, SystemInfoPage, UserInfoPage
from .sections.themes.settings import ThemeSettingsPage, ThemeDownloadPage
from .sections.plugins.plugins import PluginManagePage, PluginDownloadPage
from .sections.packs.packs import IconInstalledPage, IconDownloadPage, StyleDownloadPage, StyleInstalledPage, TemplateDownloadPage, TemplateInstalledPage, SoundDownloadPage, SoundInstalledPage
from .sections.animations.animations import AnimationDownloadPage, AnimationSettingsPage
from .sections.wallpaper import WallpaperSettingsPage

class ShellSettingsApp(App):
    def __init__(self, **kwargs):
        super().__init__(visible=False, **kwargs)
        self.add_section(AppSection(
            name="wallpaper",
            icon="images",
            label="Wallpaper",
            pages=[
                WallpaperSettingsPage()
            ],
        ))
        self.add_section(AppSection(
            name="themes",
            icon="palette",
            label="Themes",
            pages=[
                ThemeSettingsPage(),
                ThemeDownloadPage()
            ],
        ))
        self.add_section(AppSection(
            name="icons",
            icon="smiley",
            label="Icons",
            pages=[
                IconInstalledPage(),
                IconDownloadPage()
            ],
        ))
        self.add_section(AppSection(
            name="sounds",
            icon="music-note",
            label="Sounds",
            pages=[
                SoundInstalledPage(),
                SoundDownloadPage()
            ],
        ))
        self.add_section(AppSection(
            name="animations",
            icon="bezier-curve",
            label="Animations",
            pages=[
                AnimationSettingsPage(),
                AnimationDownloadPage()
            ],
        ))
        self.add_section(AppSection(
            name="styles",
            icon="hammer",
            label="Styles",
            pages=[
                StyleInstalledPage(),
                StyleDownloadPage()
            ],
        ))
        self.add_section(AppSection(
            name="templates",
            icon="swatches",
            label="Templates",
            pages=[
                TemplateInstalledPage(),
                TemplateDownloadPage()
            ],
        ))

        self.add_section(AppSection(
            name="plugins",
            icon="puzzle-piece",
            label="Plugins",
            pages=[
                PluginManagePage(),
                PluginDownloadPage()
            ],
        ))
        self.add_section(AppSection(
            name="about",
            icon="user",
            label="About",
            pages=[
                ShellInfoPage(),
                SystemInfoPage(),
                UserInfoPage()
            ],
        ))
