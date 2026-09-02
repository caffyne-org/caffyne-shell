import os

from ....common.components import AppPage
from ....common.rows import FilePickerRow, PageSection, SettingRow

from services.themes import wp
from user_options import user_options

from .components import WallpaperBrowser, WallpaperPreview

FIT_MODES = {
    "Fill":    "crop",
    "Fit":     "fit",
    "Stretch": "stretch",
    "Center":  "no",
}
FIT_LABELS = {value: label for label, value in FIT_MODES.items()}


class WallpaperSettingsPage(AppPage):
    def __init__(self, **kwargs):
        options = user_options.wallpaper

        self.preview = WallpaperPreview()
        self.browser = WallpaperBrowser(self.preview)

        self.folder_row = FilePickerRow(
            name="Wallpaper Folder",
            value=options.folder,
            on_file_picked=self._on_folder_picked,
            title="Choose Wallpaper Folder",
            select_folder=True,
        )

        super().__init__(
            name="Wallpaper",
            title="Wallpaper",
            items=[
                self.preview,
                PageSection(
                    title="General",
                    items=[
                        SettingRow(
                            name="Fit",
                            active=FIT_LABELS.get(options.resize, "Fill"),
                            settings=list(FIT_MODES),
                            on_changed=self._on_fit_changed,
                        ),
                        self.folder_row,
                    ],
                ),
                self.browser,
            ],
            **kwargs,
        )

        self.preview.show_path(wp.wallpaper_path or None)

    def _on_fit_changed(self, label: str) -> None:
        user_options.wallpaper.resize = FIT_MODES[label]
        user_options.save()
        if wp.wallpaper_path:
            wp.set_wallpaper(wp.wallpaper_path)

    def _on_folder_picked(self, folder: str) -> None:
        if not os.path.isdir(folder):
            return
        user_options.wallpaper.folder = folder
        user_options.save()
        self.folder_row.set_value(folder)
        self.browser.set_folder(folder)
