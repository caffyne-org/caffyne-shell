import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from snippets import Icon

class FilePickerRow(Box):
    def __init__(
        self,
        name,
        value,
        on_file_picked=None,
        title: str = "Choose a File",
        select_folder: bool = False,
        **kwargs,
    ):
        self.title = title
        self.select_folder = select_folder
        self._value_label = Label(
            style="opacity: 0.8", h_expand=True, h_align="end", label=value
        )
        super().__init__(
            style_classes=["app-row"],
            children=[
                Label(h_expand=True, h_align="start", label=name),
                Button(
                    child=Box(
                        spacing=4,
                        children=[
                            self._value_label,
                            Icon(h_expand=False, icon_name="caffyne")
                        ]
                    ),
                    on_clicked=lambda *_: self.open_file_picker(on_file_picked)
                )
            ],
            **kwargs
        )
        self.on_file_picked = on_file_picked

    def set_value(self, value: str):
        self._value_label.set_label(value)

    def open_file_picker(self, callback):
        dialog = Gtk.FileChooserDialog(
            title=self.title,
            action=Gtk.FileChooserAction.SELECT_FOLDER
            if self.select_folder
            else Gtk.FileChooserAction.OPEN,
        )
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dialog.add_button(Gtk.STOCK_OPEN, Gtk.ResponseType.OK)

        if not self.select_folder:
            filter_image = Gtk.FileFilter()
            filter_image.set_name("Image Files")
            filter_image.add_mime_type("image/png")
            filter_image.add_mime_type("image/jpeg")
            filter_image.add_mime_type("image/webp")
            dialog.add_filter(filter_image)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            if callback and filename:
                callback(filename)
        dialog.destroy()
