import os

from ....common.components import AppPage
from ....common.rows import InfoRow, PageSection, SwitchRow, SettingRow, SliderRow
from user_options import user_options
from services.desktop_applets import DesktopAppletService
from services.singletons import theme_service
from ..packs.components import InstalledPacksBrowser, AvailablePacksBrowser, BasePackBrowser, PackCard
from .accent import AccentRow
RADIUS_MAP = {
    "Sharp":  {"radius-s": "0px",  "radius-m": "0px",  "radius-l": "0px",  "radius-xl": "0px"},
    "Medium": {"radius-s": "4px",  "radius-m": "10px", "radius-l": "16px", "radius-xl": "28px"},
    "Round":  {"radius-s": "12px", "radius-m": "18px", "radius-l": "24px", "radius-xl": "36px"},
}
FONT_MAP = {
    "None":  {"mixed-mono": "unset",  "always-mono": "unset"},
    "Mixed": {"mixed-mono": "monospace",  "always-mono": "unset"},
    "All":  {"mixed-mono": "monospace", "always-mono": "monospace"},
}

class ThemeInstalledPacksBrowser(BasePackBrowser):
    def __init__(self, service, **kwargs):
        super().__init__(
            service=service,
            show_downloaded=True,
            section_title="Installed Themes",
            **kwargs,
        )
        service.connect("mode-changed", lambda *_: self._render_grid())

    def _render_grid(self):
        for child in self.grid.get_children():
            child.destroy()

        is_dark = self.service._is_dark
        variant = "dark" if is_dark else "light"

        count = 0
        for meta in self._all_packs:
            if not meta.get("downloaded", False):
                continue
            if meta.get("variant") != variant:
                continue
            card = PackCard(meta=meta, service=self.service)
            self.grid.add(card)
            count += 1

        self.status_label.set_label(f"({count} pack{'s' if count != 1 else ''})")
        self.grid.show_all()


class ThemeSettingsPage(AppPage):
    def __init__(self, **kwargs):
        self.matugen_switch = SwitchRow(
            name="Matugen (Wallpaper Colors)",
            toggled=theme_service.active_is_wallpaper,
            on_toggle=self._on_matugen_toggled,
        )

        self.color_mode_row = SettingRow(
            name="Color Mode",
            active="Dark" if user_options.theme.is_dark else "Light",
            settings=["Light", "Dark"],
            on_changed=self._set_dark,
        )

        super().__init__(
            name="Manage",
            title="Manage",
            items=[
                PageSection(
                    title="Color Scheme",
                    items=[
                        self.color_mode_row,
                        self.matugen_switch,
                        AccentRow(),
                    ],
                ),
                PageSection(
                    title="General",
                    items=[
                        SettingRow(name="Border Radius", active=user_options.theme.border_style, settings=["Sharp", "Medium", "Round"], on_changed=self._on_radius_clicked),
                        SliderRow(name="Opacity", value=user_options.theme.opacity, on_released=self._on_opacity_released, value_formatter=lambda val: f"{round(val * 100)}%"),
                        SwitchRow(name="Blur", toggled=user_options.theme.blur, on_toggle=self._on_blur_toggled),
                        SettingRow(name="Monospace Font", active=user_options.theme.font_monospace_style, settings=["None", "Mixed", "All"], on_changed=self._on_font_clicked),
                    ],
                ),
                ThemeInstalledPacksBrowser(theme_service),
            ],
            **kwargs,
        )

        theme_service.connect("mode-changed", self._on_mode_changed)
        theme_service.connect("pack-changed", self._on_pack_changed)

    def _on_mode_changed(self, *_):
        self._sync_matugen_switch()

    def _on_pack_changed(self, _, pack_name: str):
        self._sync_matugen_switch()

    def _sync_matugen_switch(self):
        self.matugen_switch.children[1].set_active(theme_service.active_is_wallpaper)
        
    def _set_dark(self, mode) -> None:
        theme_service.apply_dark(mode == "Dark")

    def _on_matugen_toggled(self, enabled: bool) -> None:
        if enabled:
            theme_service.set_pack("Matugen")
        else:
            themes = theme_service.list_themes(dark=theme_service._is_dark)
            fallback = themes[0] if themes else None
            if fallback:
                theme_service.set_pack(fallback)

    def _on_opacity_released(self, scale, event) -> None:
        value = round(scale.get_value(), 2)
        user_options.theme.opacity = value
        user_options.save()
        theme_service.apply()

    def _on_blur_toggled(self, state: bool) -> None:
        from services.singletons import bar_manager
        user_options.theme.blur = state
        user_options.save()
        bar_manager.apply_blur(state)
        DesktopAppletService.get_instance().apply_blur(state)

    def _on_radius_clicked(self, key: str) -> None:
        user_options.theme.border_style = key
        user_options.save()
        values = RADIUS_MAP[key]
        css = "\n".join(f"@define {k} {v};" for k, v in values.items())
        path = os.path.expanduser("~/.config/caffyne-shell/style/borders.css")
        with open(path, "w") as f:
            f.write(css + "\n")

    def _on_font_clicked(self, key: str) -> None:
        user_options.theme.font_monospace_style = key
        user_options.save()
        values = FONT_MAP[key]
        css = "\n".join(f"@define {k} {v};" for k, v in values.items())
        path = os.path.expanduser("~/.config/caffyne-shell/style/fonts.css")
        with open(path, "w") as f:
            f.write(css + "\n")

class ThemeDownloadPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Download",
        title="Download",
        items=[
            PageSection(
                title="Download",
                items=[AvailablePacksBrowser(theme_service)],
            ),
        ],
        **kwargs,
    )