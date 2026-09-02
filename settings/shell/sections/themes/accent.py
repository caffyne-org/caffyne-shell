from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from services.singletons import theme_service
from user_options import user_options
from gi.repository import Gtk, GLib
def _color_dot(hex_color: str, size: int = 16, active: bool = False) -> Gtk.Widget:
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
class AccentRow(Box):
    def __init__(self, on_changed: callable | None = None, **kwargs):
        self._on_changed = on_changed
        self._accent_buttons: dict[str, Button] = {}
        self._signal_handles: list[tuple[object, int]] = []

        self._dots_box = Box(
            orientation="h",
            spacing=8,
            h_align="end",
            h_expand=True,
            v_align="center",
            v_expand=False,
        )

        super().__init__(
            orientation="h",
            spacing=6,
            h_align="fill",
            h_expand=True,
            style_classes=["app-row"],
            children=[
                Label(
                    label="Accent",
                    style_classes=["dim-label"],
                    h_align="start",
                ),
                self._dots_box,
            ],
            **kwargs,
        )

        self.connect("realize", self._on_realize)
        self.connect("unrealize", self._on_unrealize)

    def _on_realize(self, *_) -> None:
        """Connect service signals when widget is mounted and perform initial sync."""
        self._disconnect_signals()

        h1 = theme_service.connect("accent-changed", self._on_service_accent_changed)
        h2 = theme_service.connect("theme-changed", self._on_service_theme_changed)
        h3 = theme_service.connect("mode-changed", self._on_service_theme_changed)

        self._signal_handles.extend([
            (theme_service, h1),
            (theme_service, h2),
            (theme_service, h3),
        ])

        self.reload_from_service()

    def _on_unrealize(self, *_) -> None:
        self._disconnect_signals()

    def _disconnect_signals(self) -> None:
        for obj, handle in self._signal_handles:
            if obj and GLib.gobject_is_valid(obj):
                obj.disconnect(handle)
        self._signal_handles.clear()

    def reload_from_service(self) -> None:
        self.load_theme_data(theme_service.current_theme_data)

    def load_theme_data(self, data: dict | None) -> None:
        """Populate accent color dots from theme data dictionary."""
        for child in self._dots_box.get_children():
            self._dots_box.remove(child)
        self._accent_buttons.clear()

        if data is None:
            self._dots_box.add(
                Label(
                    label="Colours from wallpaper",
                    style_classes=["dim-label"],
                )
            )
            self._dots_box.show_all()
            return

        accents = data.get("accents", {}).get("available", {})
        active_accent = theme_service.active_accent
        default_accent = data.get("accents", {}).get("default", "")

        if active_accent not in accents:
            active_accent = default_accent

        for accent_name, hex_color in accents.items():
            is_active = accent_name == active_accent
            dot = _color_dot(hex_color, size=24, active=is_active)
            btn = Button(
                child=dot,
                style_classes=["accent-btn"],
                on_clicked=lambda _, name=accent_name: self._on_accent_clicked(name),
            )
            self._accent_buttons[accent_name] = btn
            self._dots_box.add(btn)

        self._dots_box.show_all()

    def refresh_active_dots(self) -> None:
        if theme_service.current_theme_data is None:
            return

        accents = theme_service.current_theme_data.get("accents", {}).get("available", {})
        active = theme_service.active_accent

        for accent_name, btn in self._accent_buttons.items():
            hex_color = accents.get(accent_name, "#ffffff")
            is_active = accent_name == active
            old_child = btn.get_child()
            if old_child:
                btn.remove(old_child)
            btn.add(_color_dot(hex_color, size=24, active=is_active))
            btn.show_all()

    def _on_accent_clicked(self, accent_name: str) -> None:
        theme_service.apply_accent(accent_name)
        user_options.save()

        if self._on_changed:
            self._on_changed(accent_name)

    def _on_service_accent_changed(self, service, *args) -> None:
        self.refresh_active_dots()

    def _on_service_theme_changed(self, service, *args) -> None:
        self.reload_from_service()