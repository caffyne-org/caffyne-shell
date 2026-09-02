import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from snippets import Icon, enable_blur, set_blur_regions_from_widget
from user_options import user_options


class DropdownRow(Box):
    def __init__(self, name, options, active, on_changed, **kwargs):
        self.options = list(options)
        self.on_changed = on_changed
        self._value = active if active in self.options else (self.options[0] if self.options else "")

        self._value_label = Label(style_classes=["dropdown-row-value"], label=self._value)
        self._button = Button(
            style_classes=["dropdown-row-button"],
            child=Box(
                spacing=4,
                children=[
                    self._value_label,
                    Icon(icon_name="caret-down", icon_size=14),
                ],
            ),
            on_clicked=lambda button: self.open_menu(button),
        )

        super().__init__(
            style_classes=["app-row"],
            children=[
                Label(h_expand=True, h_align="start", label=name),
                self._button,
            ],
            **kwargs
        )

    def get_value(self) -> str:
        return self._value

    def set_value(self, value: str, notify: bool = True):
        if value not in self.options:
            return
        self._value = value
        self._value_label.set_label(value)
        if notify:
            self.on_changed(value)

    def open_menu(self, button):
        menu = Gtk.Menu()
        for option in self.options:
            item = Gtk.MenuItem(label=option)
            if option == self._value:
                item.get_style_context().add_class("dropdown-row-item-active")
            item.connect("activate", lambda _, o=option: self.set_value(o))
            menu.append(item)

        menu.show_all()
        menu.popup_at_widget(
            button,
            Gdk.Gravity.SOUTH_EAST,
            Gdk.Gravity.NORTH_EAST,
            Gtk.get_current_event(),
        )

        if user_options.theme.blur:
            GLib.idle_add(self._blur_menu, menu)

    def _blur_menu(self, menu: Gtk.Menu):
        blur_ctx = enable_blur(menu)

        def do_set_regions():
            if blur_ctx:
                set_blur_regions_from_widget(blur_ctx, menu)
            return False

        GLib.timeout_add(50, do_set_regions)
        return False
