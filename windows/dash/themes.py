from __future__ import annotations


from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.utils import get_relative_path
from gi.repository import Gtk

from snippets import Icon, AnimatedScroll, ClippingBox, SmoothSwitch, FlatScale
from services.singletons import theme_service
from services.themes import WALLPAPER_THEME
from user_options import user_options

THUMB_BG_W   = 174
THUMB_BG_H   = 174
ACCENT_DOT   = 16
MAX_DOTS     = 4

RADIUS_MAP = {
    "sharp":  {"radius-s": "0px",  "radius-m": "0px",  "radius-l": "0px",  "radius-xl": "0px"},
    "medium": {"radius-s": "4px",  "radius-m": "10px", "radius-l": "16px", "radius-xl": "28px"},
    "round":  {"radius-s": "12px", "radius-m": "18px", "radius-l": "24px", "radius-xl": "36px"},
}

FONT_MAP = {
    "none":  {"mixed-mono": "unset",  "always-mono": "unset"},
    "mixed": {"mixed-mono": "monospace",  "always-mono": "unset"},
    "all":  {"mixed-mono": "monospace", "always-mono": "monospace"},
}

def _color_dot(hex_color: str, size: int = ACCENT_DOT, active: bool = False) -> Gtk.Widget:
    dot = Box(
        v_align="center",
        v_expand=False
    )
    dot.set_size_request(size, size)
    border = f"border: 2px solid rgba(255,255,255,0.85);" if active else ""
    dot.set_style(
        f"background-color: {hex_color};"
        f"border-radius: 30px;"
        f"{border}"
        f"min-width: {size}px; min-height: {size}px;"
    )
    return dot

class Section(Box):
    """
    A labelled section with a styled background container.

    Usage:
        Section(
            title="Appearance",
            children=[widget1, widget2],
        )

    CSS targets:
        .section-header   — the title label
        .section-body     — the background box wrapping children
        .section-root     — the outer vertical box
    """
    def __init__(
        self,
        title: str,
        children: list | None = None,
        spacing: int = 1,
        **kwargs,
    ):
        self._header_label = Label(
            label=title,
            style_classes=["section-header"],
            h_align="start",
        )

        self._body = ClippingBox(
            orientation="v",
            spacing=spacing,
            style_classes=["section-body"],
        )

        if children:
            for child in children:
                self._body.add(child)
                child.add_style_class("section-child")

        super().__init__(
            orientation="v",
            spacing=12,
            h_expand=False,
            h_align="center",
            style_classes=["section-root"],
            children=[self._header_label, self._body],
            **kwargs,
        )

    def add_child(self, widget: Gtk.Widget) -> None:
        """Add a widget to the section body."""
        self._body.add(widget)

    def clear(self) -> None:
        """Remove all children from the section body."""
        for child in self._body.get_children():
            self._body.remove(child)

class ThemeThumb(Button):
    def __init__(self, name: str, data: dict, is_dark: bool, on_select):
        self._name    = name
        self._data    = data
        self._is_dark = is_dark

        mode = "dark"

        colors  = data.get("colors", {})
        accents = data.get("accents", {}).get("available", {})

        bg_color   = colors.get("background", {}).get(mode, {}).get("color", "#1e1e2e")
        surface_color = colors.get("surface_container", {}).get(mode, {}).get("color", "#cdd6f4")
        text_color = colors.get("on_background", {}).get(mode, {}).get("color", "#cdd6f4")

        self._label = Label(
            label=data.get("name", name),
            style=f"color: {text_color}; font-size: 14px;",
        )

        dot_box = Box(style_classes=["theme-preview-color-container"], style=f"background-color: {surface_color}", orientation="h", spacing=4, h_align="center")
        accent_list = list(accents.items())[:MAX_DOTS]
        for _accent_name, accent_hex in accent_list:
            dot = _color_dot(accent_hex, ACCENT_DOT)
            dot_box.add(dot)

        inner = Box(
            orientation="v",
            spacing=18,
            v_align="center",
            h_align="center",
            h_expand=True,
            v_expand=True,
            children=[self._label, dot_box],
        )

        self._clip = ClippingBox(
            style_classes=["dash-grid-selector-preview"],
            style=f"background-color: {bg_color};",
            children=inner,
        )
        self._clip.set_size_request(THUMB_BG_W, THUMB_BG_H)

        super().__init__(
            style_classes=["wallpaper-thumb"],
            child=self._clip,
            on_clicked=lambda _: on_select(self),
        )

    @property
    def theme_name(self) -> str:
        return self._name

    def set_active(self, active: bool) -> None:
        if active:
            self._clip.add_style_class("active")
        else:
            self._clip.remove_style_class("active")

class MatugenThumb(Button):
    """
    Thumbnail for the Matugen (wallpaper) theme slot.
    Shows a blurred version of the current wallpaper as the background,
    with the icon and label overlaid on top via a GTK overlay.
    """

    def __init__(self, on_select):
        self._name = WALLPAPER_THEME

        foreground = Box(
            orientation="v",
            spacing=18,
            # v_align="center",
            # h_align="center",
            h_expand=True,
            v_expand=True,
            style_classes=["matugen-thumb"],
            children=[
                Label(v_expand=True, v_align="end", label="Material Colors", style="font-size: 14px;"),
                Icon(v_expand=True, v_align="start", icon_name="android-logo-duotone", icon_size=36),
            ],
        )

        super().__init__(
            style_classes=["wallpaper-thumb"],
            v_align="center",
            h_align="center",
            h_expand=True,
            v_expand=True,
            child=foreground,
            on_clicked=lambda _: on_select(self),
        )

    @property
    def theme_name(self) -> str:
        return WALLPAPER_THEME

    def set_active(self, active: bool) -> None:
        if active:
            self.add_style_class("active")
        else:
            self.remove_style_class("active")

class ThemePreview(Box):
    def __init__(self, bar_manager):
        self._accent_buttons: dict[str, Gtk.DrawingArea] = {}
        self.bar_manager = bar_manager

        self._accent_row = Box(
            orientation="h",
            spacing=8,
            h_align="end",
            h_expand=True,
            v_align="center",
            v_expand=False,
        )
        accent_section = Box(
            orientation="h",
            spacing=6,
            h_align="fill",
            h_expand=True,
            children=[
                Label(label="Accent", style_classes=["dim-label"], h_align="start"),
                self._accent_row,
            ],
        )

        self._radius_buttons: dict[str, Button] = {}
        radius_row = Box(style_classes=["option-selection-container"], orientation="h", spacing=6, h_align="center")
        for label, key in [("Sharp", "sharp"), ("Medium", "medium"), ("Round", "round")]:
            btn = Button(
                label=label,
                style_classes=["option-selection-button"],
                on_clicked=lambda _, k=key: self._on_radius_clicked(k),
            )
            self._radius_buttons[key] = btn
            radius_row.add(btn)

        radius_section = Box(
            orientation="h",
            spacing=6,
            h_align="fill",
            children=[
                Label(label="Corners", style_classes=["dim-label"], h_expand=True, h_align="start"),
                radius_row,
            ],
        )

        self._font_buttons: dict[str, Button] = {}
        font_row = Box(style_classes=["option-selection-container"], orientation="h", spacing=6, h_align="center")
        for label, key in [("None", "none"), ("Mixed", "mixed"), ("All", "all")]:
            btn = Button(
                label=label,
                style_classes=["option-selection-button"],
                on_clicked=lambda _, k=key: self._on_font_clicked(k),
            )
            self._font_buttons[key] = btn
            font_row.add(btn)

        font_section = Box(
            orientation="h",
            spacing=6,
            h_align="fill",
            children=[
                Label(label="Monospace", style_classes=["dim-label"], h_expand=True, h_align="start"),
                font_row,
            ],
        )

        self._dark_btn = Button(
            child=Box(orientation="h", spacing=6, children=[
                Label(label="Dark")
            ]),
            style_classes=["option-selection-button"],
            on_clicked=lambda _: self._set_dark(True),
        )
        self._light_btn = Button(
            child=Box(orientation="h", spacing=6, children=[
                 Label(label="Light"),
            ]),
            style_classes=["option-selection-button"],
            on_clicked=lambda _: self._set_dark(False),
        )

        mode_section = Box(
            orientation="h",
            spacing=6,
            h_align="fill",
            children=[
                Label(label="Mode", style_classes=["dim-label"], h_expand=True, h_align="start"),
                Box(style_classes=["option-selection-container"],
                    orientation="h", spacing=6, h_align="end",
                    children=[self._light_btn, self._dark_btn]),
            ],
        )

        self._opacity_slider = FlatScale(
            style_classes=["scale"],
            min_value=0.2,
            max_value=1.0,
            step=0.05,
            value=user_options.theme.opacity,
            h_expand=True,
        )

        self._opacity_slider.connect("button-release-event", self._on_opacity_released)

        opacity_section = Box(
            orientation="h",
            spacing=6,
            h_align="fill",
            children=[
                Label(label="Opacity", style_classes=["dim-label"], h_align="start", h_expand=True),
                Box(h_align="end", style="min-width: 224px;", children=[
                    self._opacity_slider,
                ]),
            ],
        )

        self._blur_switch = SmoothSwitch(
            style_classes=["dash-switch"],
            v_expand=True,
            v_align="center",
            on_user_toggle=self._on_blur_toggled,
            width=48,
        )
        self._blur_switch.set_active(user_options.theme.blur)
        blur_section = Box(
            orientation="h",
            spacing=6,
            h_align="fill",
            v_align="center",
            children=[
                Label(label="Blur (Beta)", style_classes=["dim-label"]),
                Box(h_expand=True, h_align="end", children=self._blur_switch),
            ],
        )

        super().__init__(
            orientation="v",
            spacing=24,
            h_align="fill",

            h_expand=True,

            style_classes=["theme-preview-panel"],
            children=[
                Section(
                    title="Color Scheme",
                    children=[
                        mode_section,
                        accent_section,
                    ]
                ),
                Section(
                    title="General",
                    children=[
                        radius_section,
                        opacity_section,
                        blur_section,
                    ]
                ),
                Section(
                    title="Fonts",
                    children=[
                        font_section
                    ]
                )
            ],
        )

        self._update_mode_buttons(user_options.theme.is_dark)
        self._on_radius_clicked(user_options.theme.border_style)
        self._on_font_clicked(user_options.theme.font_monospace_style)

    def load_theme(self, data: dict | None) -> None:
        for child in self._accent_row.get_children():
            self._accent_row.remove(child)
        self._accent_buttons.clear()

        if data is None:
            self._accent_row.add(Label(
                label="Colours from wallpaper",
                style_classes=["dim-label"],
            ))
            self._accent_row.show_all()
            return

        accents        = data.get("accents", {}).get("available", {})
        active_accent  = theme_service.active_accent
        default_accent = data.get("accents", {}).get("default", "")

        if active_accent not in accents:
            active_accent = default_accent

        for accent_name, hex_color in accents.items():
            is_active = accent_name == active_accent
            dot = _color_dot(hex_color, size=22, active=is_active)
            btn = Button(
                child=dot,
                style_classes=["accent-btn"],
                on_clicked=lambda _, n=accent_name: self._on_accent_clicked(n),
            )
            self._accent_buttons[accent_name] = btn
            self._accent_row.add(btn)

        self._accent_row.show_all()

    def refresh_active_accent(self) -> None:
        if theme_service.current_theme_data is None:
            return
        accents = theme_service.current_theme_data.get("accents", {}).get("available", {})
        active  = theme_service.active_accent

        for accent_name, btn in self._accent_buttons.items():
            hex_color = accents.get(accent_name, "#ffffff")
            is_active = accent_name == active
            old = btn.get_child()
            if old:
                btn.remove(old)
            btn.add(_color_dot(hex_color, size=22, active=is_active))
            btn.show_all()

    def _on_opacity_released(self, scale, event) -> None:
        value = round(scale.get_value(), 2)
        user_options.theme.opacity = value
        user_options.save()
        theme_service.apply()

    def _on_blur_toggled(self, state: bool) -> None:
        user_options.theme.blur = state
        user_options.save()
        self.bar_manager.apply_blur(state)

    def _on_accent_clicked(self, name: str) -> None:
        theme_service.apply_accent(name)
        self.refresh_active_accent()
        user_options.save()

    def _on_radius_clicked(self, key: str) -> None:
        for k, btn in self._radius_buttons.items():
            if k == key:
                btn.add_style_class("active")
            else:
                btn.remove_style_class("active")
        user_options.theme.border_style = key
        user_options.save()
        self._write_border_css(key)

    def _on_font_clicked(self, key: str) -> None:
        for k, btn in self._font_buttons.items():
            if k == key:
                btn.add_style_class("active")
            else:
                btn.remove_style_class("active")
        user_options.theme.font_monospace_style = key
        user_options.save()
        self._write_font_css(key)

    def _set_dark(self, dark: bool) -> None:
        theme_service.apply_dark(dark)
        self._update_mode_buttons(dark)

    def _update_mode_buttons(self, is_dark: bool) -> None:
        if is_dark:
            self._dark_btn.add_style_class("active")
            self._light_btn.remove_style_class("active")
        else:
            self._light_btn.add_style_class("active")
            self._dark_btn.remove_style_class("active")

    def _write_border_css(self, key: str) -> None:
        values = RADIUS_MAP[key]
        css = "\n".join(f"@define {k} {v};" for k, v in values.items())
        path = get_relative_path("../../style/borders.css")
        with open(path, "w") as f:
            f.write(css + "\n")

    def _write_font_css(self, key: str) -> None:
        values = FONT_MAP[key]
        css = "\n".join(f"@define {k} {v};" for k, v in values.items())
        path = get_relative_path("../../style/fonts.css")
        with open(path, "w") as f:
            f.write(css + "\n")

class DashThemePage(Box):

    def __init__(self, bar_manager):
        self._active_thumb: ThemeThumb | MatugenThumb | None = None

        self._preview = ThemePreview(bar_manager)
        self._preview_box = ClippingBox(
            style_classes=["dash-grid-selector-preview", "theme-preview-box"],
            spacing=16,
            orientation="v",
            h_align="center",
            v_align="start",
            h_expand=True,
            v_expand=True,
            children=[Label(label="Theming", h_expand=True, h_align="start", style_classes=["dash-theme-preview-title"]), self._preview],
        )
        self._thumb_strip = Box(
            orientation="v",
            spacing=12,
            style_classes=["wallpaper-thumb-strip"],
        )
        self._scroll = AnimatedScroll(
            v_expand=True,
            style_classes=["grid-selector-thumb-scroll"],
            max_content_size=(174, 630),
            fade_distance=60,
            child=self._thumb_strip,
            overlay_scroll=True,
            kinetic_scroll=True,
        )

        super().__init__(
            orientation="v",
            v_align="start",
            h_align="center",
            h_expand=True,
            v_expand=True,
            children=[
                Box(
                    orientation="h",
                    spacing=12,
                    h_expand=True,
                    v_expand=True,
                    children=[self._preview_box, self._scroll],
                ),
            ],
        )

        self._load_thumbs()
        self._restore_active(theme_service.active_theme_name)

        theme_service.connect("mode-changed", self._on_mode_changed)
        theme_service.connect("accent-changed", lambda _: self._preview.refresh_active_accent())

        self.connect("realize", self._on_realize)

    def _on_realize(self, *_) -> None:
        stack = self.get_parent()
        if stack:
            stack.connect("notify::visible-child", self._on_stack_switch)
        toplevel = self.get_toplevel()
        if toplevel:
            toplevel.connect("destroy", lambda *_: self._cleanup())

    def _on_stack_switch(self, stack, *_) -> None:
        if stack.get_visible_child() == self:
            if not self._thumb_strip.get_children():
                self._load_thumbs()
                self._restore_active(theme_service.active_theme_name)
        else:
            self._unload_thumbs()

    def _cleanup(self) -> None:
        self._unload_thumbs()

    def _unload_thumbs(self) -> None:
        for child in self._thumb_strip.get_children():
            self._thumb_strip.remove(child)
            child.destroy()
        self._active_thumb = None

    def _load_thumbs(self) -> None:
        for child in self._thumb_strip.get_children():
            self._thumb_strip.remove(child)
        self._active_thumb = None

        is_dark     = theme_service.is_dark
        theme_names = theme_service.list_themes(dark=is_dark)

        matugen = MatugenThumb(self._on_thumb_clicked)

        for name in theme_names:
            data = theme_service.load_theme_data(name, dark=is_dark)
            if data is None:
                continue
            thumb = ThemeThumb(name, data, is_dark, self._on_thumb_clicked)
            self._thumb_strip.add(thumb)
        self._thumb_strip.add(matugen)

        self._thumb_strip.show_all()

    def _on_thumb_clicked(self, thumb: ThemeThumb | MatugenThumb) -> None:
        self._set_active(thumb)
        if isinstance(thumb, MatugenThumb):
            if theme_service.is_dark:
                theme_service.apply_dark_theme(WALLPAPER_THEME)
            else:
                theme_service.apply_light_theme(WALLPAPER_THEME)
        else:
            if theme_service.is_dark:
                theme_service.apply_dark_theme(thumb.theme_name)
            else:
                theme_service.apply_light_theme(thumb.theme_name)
        user_options.save()

    def _set_active(self, thumb: ThemeThumb | MatugenThumb) -> None:
        if self._active_thumb:
            self._active_thumb.set_active(False)
        self._active_thumb = thumb
        thumb.set_active(True)
        if isinstance(thumb, MatugenThumb):
            self._preview.load_theme(None)
        else:
            self._preview.load_theme(
                theme_service.load_theme_data(thumb.theme_name, dark=theme_service.is_dark)
            )

    def _restore_active(self, name: str) -> None:
        for thumb in self._thumb_strip.get_children():
            if isinstance(thumb, (ThemeThumb, MatugenThumb)) and thumb.theme_name == name:
                if self._active_thumb:
                    self._active_thumb.set_active(False)
                self._active_thumb = thumb
                thumb.set_active(True)
                if isinstance(thumb, MatugenThumb):
                    self._preview.load_theme(None)
                else:
                    self._preview.load_theme(
                        theme_service.load_theme_data(name, dark=theme_service.is_dark)
                    )
                return

    def _on_mode_changed(self, _service) -> None:
        self._load_thumbs()
        self._restore_active(theme_service.active_theme_name)
        self._preview._update_mode_buttons(theme_service.is_dark)
