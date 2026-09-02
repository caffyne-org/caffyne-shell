from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.button import Button
from gi.repository import GdkPixbuf, Gtk
from snippets import Icon, ClippingScrolledWindow, ClippingBox
from ....common.components import AppPage
from ....common.rows import PageSection
from services.singletons import plugins

class BasePluginCard(ClippingBox):
    def __init__(self, meta: dict, **kwargs):
        super().__init__(
            orientation="v",
            spacing=0,
            h_expand=False,
            h_align="center",
            v_expand=False,
            style_classes=["pack-card"],
            **kwargs,
        )
        self.meta = meta
        self._plugins = plugins

        preview_path = meta.get("preview_path")
        if preview_path:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(preview_path, 280, 153, False)
                preview = Image(pixbuf=pixbuf, style_classes=["pack-card-preview"])
            except Exception:
                preview = Box(style_classes=["pack-card-preview", "pack-card-preview-empty"])
        else:
            preview = Box(style_classes=["pack-card-preview", "pack-card-preview-empty"])

        name_label = Label(
            label=meta.get("display_name", meta.get("name", "Unknown")),
            h_align="start",
            style_classes=["pack-card-name"],
        )
        author_label = Label(
            label=meta.get("author", ""),
            h_align="start",
            style_classes=["pack-card-author"],
        )
        name_box = Box(
            orientation="v",
            spacing=2,
            h_expand=True,
            children=[name_label, author_label],
        )

        description = meta.get("description", "")
        info_btn = Button(
            style_classes=["pack-card-info-button"],
            tooltip_text=description if description else "No description available",
            child=Icon(icon_name="info", icon_size=16),
        )
        info_btn.set_relief(Gtk.ReliefStyle.NONE)

        info_row = Box(
            orientation="h",
            spacing=8,
            style_classes=["pack-card-info-row"],
            children=[name_box, info_btn],
        )

        self.btn_row = Box(
            orientation="h",
            spacing=1,
            style_classes=["pack-card-btn-row"],
        )

        self.add(preview)
        self.add(info_row)
        self.add(self.btn_row)

class DownloadPluginCard(BasePluginCard):
    def __init__(self, meta: dict, **kwargs):
        super().__init__(meta=meta, **kwargs)

        self.download_btn = Button(
            h_expand=True,
            style_classes=["pack-card-btn", "pack-card-download-btn"],
            child=Box(
                h_align="center",
                orientation="h",
                spacing=6,
                children=[
                    Icon(icon_name="download-simple", icon_size=16),
                    Label(label="Download"),
                ],
            ),
        )
        self.download_btn.connect("clicked", self._on_download_clicked)
        self.btn_row.add(self.download_btn)

    def _on_download_clicked(self, *_):
        self.download_btn.set_sensitive(False)
        for child in self.download_btn.get_children():
            self.download_btn.remove(child)
        self.download_btn.add(Label(label="Downloading..."))
        self.download_btn.show_all()
        self._plugins.download_plugin(self.meta.get("name"))


class ManagePluginCard(BasePluginCard):
    def __init__(self, meta: dict, **kwargs):
        super().__init__(meta=meta, **kwargs)
        is_enabled = meta.get("enabled", False)

        self.remove_btn = Button(
            h_expand=True,
            style_classes=["pack-card-btn", "pack-card-remove-btn"],
            child=Box(
                h_align="center",
                orientation="h",
                spacing=6,
                children=[
                    Icon(icon_name="trash", icon_size=16),
                    Label(label="Remove"),
                ],
            ),
        )
        self.remove_btn.connect("clicked", self._on_remove_clicked)

        self.toggle_btn = Button(
            h_expand=True,
            style_classes=["pack-card-btn", "pack-card-apply-btn"],
            child=Box(
                h_align="center",
                orientation="h",
                spacing=6,
                children=[
                    Icon(icon_name="x" if is_enabled else "check", icon_size=16),
                    Label(label="Disable" if is_enabled else "Enable"),
                ],
            ),
        )
        self.toggle_btn.connect("clicked", self._on_toggle_clicked)

        self.btn_row.add(self.remove_btn)
        self.btn_row.add(self.toggle_btn)

        plugins.connect("plugin-enabled", self._on_plugin_enabled)
        plugins.connect("plugin-disabled", self._on_plugin_disabled)

    def _on_remove_clicked(self, *_):
        self._plugins.uninstall_plugin(self.meta.get("name"))

    def _on_toggle_clicked(self, *_):
        name = self.meta.get("name")
        if self._plugins.is_enabled(name):
            self._plugins.disable_plugin(name)
        else:
            self._plugins.enable_plugin(name)

    def _set_toggle_label(self, enabled: bool):
        child_box = self.toggle_btn.get_child()
        if child_box and len(child_box.children) >= 2:
            child_box.children[0].icon_name = "x" if enabled else "check"
            child_box.children[1].set_label("Disable" if enabled else "Enable")

    def _on_plugin_enabled(self, _, name: str):
        if name == self.meta.get("name"):
            self._set_toggle_label(True)

    def _on_plugin_disabled(self, _, name: str):
        if name == self.meta.get("name"):
            self._set_toggle_label(False)

class BasePluginBrowser(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", spacing=12, **kwargs)

        self._plugins_meta: dict[str, dict] = {}

        self.status_label = Label(label="Checking for plugins…")
        self.add(self.status_label)

        self.notice_label = Label(h_align="start", h_expand=True, line_wrap="word-char")
        self.retry_button = Button(
            label="Try Again",
            style_classes=["pack-notice-btn"],
            on_clicked=lambda *_: self.reload_from_github(),
        )
        self.notice = Box(
            orientation="h",
            spacing=8,
            style_classes=["pack-notice"],
            children=[
                Icon(icon_name="warning", icon_size=16),
                self.notice_label,
                self.retry_button,
            ],
        )
        self.notice.show_all()
        self.notice.set_no_show_all(True)
        self.notice.hide()
        self.add(self.notice)

        self.scroll = ClippingScrolledWindow()
        self.grid = Gtk.FlowBox()
        self.grid.set_max_children_per_line(4)
        self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.grid.set_column_spacing(12)
        self.grid.set_row_spacing(12)
        self.scroll.add(self.grid)
        self.add(self.scroll)

        plugins.connect("plugins-loaded", self._on_plugins_loaded)
        plugins.connect("plugin-downloaded", self._on_plugin_downloaded)
        plugins.connect("plugin-uninstalled", self._on_plugin_uninstalled)
        plugins.connect("error", self._on_error)

        plugins.fetch_available_plugins()

    def _on_plugins_loaded(self, _, plugin_list: list):
        self._plugins_meta = {meta.get("name"): meta for meta in plugin_list}
        self.notice.hide()
        self.refresh()

    def _on_plugin_downloaded(self, _, name: str):
        if name in self._plugins_meta:
            self._plugins_meta[name]["downloaded"] = True
        self.refresh()

    def _on_plugin_uninstalled(self, _, name: str):
        if name in self._plugins_meta:
            self._plugins_meta[name]["downloaded"] = False
            self._plugins_meta[name]["enabled"] = False
        self.refresh()

    def _on_error(self, _, message: str):
        if self._plugins_meta:
            self.notice_label.set_label(f"Showing saved plugins. {message}")
        else:
            self.notice_label.set_label(message)
            self.status_label.set_label("Nothing to show yet")
        self.notice.show()

    def reload_from_github(self):
        """Re-check GitHub, ignoring the cached copy of the plugin list."""
        self.notice.hide()
        self.status_label.set_label("Checking for plugins…")
        plugins.fetch_available_plugins(force=True)

    def refresh(self):
        raise NotImplementedError


class DownloadBrowser(BasePluginBrowser):
    def refresh(self):
        for child in self.grid.get_children():
            child.destroy()

        available = [meta for meta in self._plugins_meta.values() if not meta.get("downloaded", False)]
        self.status_label.set_label(f"{len(available)} available for download")

        for meta in available:
            card = DownloadPluginCard(meta=meta)
            self.grid.add(card)

        self.grid.show_all()


class ManageBrowser(BasePluginBrowser):
    def refresh(self):
        for child in self.grid.get_children():
            child.destroy()

        downloaded = [meta for meta in self._plugins_meta.values() if meta.get("downloaded", False)]
        self.status_label.set_label(f"{len(downloaded)} plugin(s) installed")

        for meta in downloaded:
            card = ManagePluginCard(meta=meta)
            self.grid.add(card)

        self.grid.show_all()


class PluginManagePage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
            name="Manage",
            title="Manage",
            items=[
                PageSection(
                    title="Installed",
                    items=[ManageBrowser()],
                ),

            ],
            **kwargs,
        )
class PluginDownloadPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Download",
        title="Download",
        items=[
            PageSection(
                title="Download",
                items=[DownloadBrowser()],
            ),
        ],
        **kwargs,
    )