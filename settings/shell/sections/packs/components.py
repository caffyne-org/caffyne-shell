import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.image import Image
from snippets import Icon,ClippingBox


class BasePackBrowser(Box):
    def __init__(self, service, show_downloaded: bool, section_title: str, **kwargs):
        super().__init__(orientation="v", spacing=12, **kwargs)
        self.service = service
        self.show_downloaded = show_downloaded
        self._all_packs = []

        self.title_label = Label(
            label=section_title, h_align="start", style_classes=["pack-section-title"]
        )
        self.status_label = Label(label="Checking for packs…", h_align="start", ellipsization="end")

        header_box = Box(
            orientation="h",
            spacing=12,
            children=[self.title_label, self.status_label],
        )
        self.add(header_box)

        self.notice_label = Label(h_align="start", h_expand=True, line_wrap="word-char")
        self.retry_button = Button(
            label="Try Again",
            style_classes=["pack-notice-btn"],
            on_clicked=lambda *_: self.refresh(),
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


        self.grid = Gtk.FlowBox()
        self.grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self.grid.set_column_spacing(12)
        self.grid.set_row_spacing(12)

        self.add(self.grid)

        service.connect("packs-loaded", self._on_packs_loaded)
        service.connect("pack-downloaded", self._on_pack_state_changed)
        service.connect("pack-uninstalled", self._on_pack_state_changed)
        service.connect("error", self._on_error)

        service.fetch_available_packs()

    def _render_grid(self):
        for child in self.grid.get_children():
            child.destroy()

        allow_disable = getattr(self.service, "allow_disable", False)

        count = 0
        for meta in self._all_packs:
            is_downloaded = meta.get("downloaded", False)
            if is_downloaded == self.show_downloaded:
                card = PackCard(meta=meta, service=self.service)
                self.grid.add(card)
                count += 1

        self.status_label.set_label(f"({count} pack{'s' if count != 1 else ''})")
        self.grid.show_all()

    def _on_packs_loaded(self, _, packs: list):
        self._all_packs = packs
        self.notice.hide()
        self._render_grid()

    def _on_pack_state_changed(self, _, pack_name: str):
        local_packs = self.service._scan_local_packs()
        for meta in self._all_packs:
            if meta.get("name") == pack_name:
                meta["downloaded"] = pack_name in local_packs
                if pack_name in local_packs:
                    meta.update(local_packs[pack_name])
                break
        self._render_grid()

    def refresh(self):
        self.notice.hide()
        self.status_label.set_label("Checking for packs…")
        self.service.fetch_available_packs(force=True)

    def _on_error(self, _, message: str):
        if self._all_packs:
            self.notice_label.set_label(f"Showing saved packs. {message}")
        else:
            self.notice_label.set_label(message)
            self.status_label.set_label("(nothing to show yet)")
        self.notice.show()


class InstalledPacksBrowser(BasePackBrowser):
    def __init__(self, service, **kwargs):
        super().__init__(
            service=service,
            show_downloaded=True,
            section_title="Installed Packs",
            **kwargs,
        )


class AvailablePacksBrowser(BasePackBrowser):
    def __init__(self, service, **kwargs):
        super().__init__(
            service=service,
            show_downloaded=False,
            section_title="Available to Download",
            **kwargs,
        )


class PackCard(ClippingBox):
    def __init__(self, meta: dict, service, **kwargs):
        super().__init__(
            orientation="v",
            spacing=0,
            style_classes=["pack-card"],
            h_align="center",
            v_align="center",
            **kwargs,
        )
        self.meta = meta
        self.service = service
        self.allow_disable = getattr(service, "allow_disable", False)
        self.allow_deactivate = getattr(service, "allow_deactivate", False)
        is_protected = getattr(service, "is_protected", None)
        self.is_protected = bool(is_protected and is_protected(meta.get("name")))

        preview_path = meta.get("preview_path")
        if preview_path and os.path.exists(preview_path):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(preview_path, 280, 153, False)
                preview = Image(pixbuf=pixbuf, style_classes=["pack-card-preview"])
            except Exception as e:
                print(f"[PackCard] Failed loading preview: {e}")
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
            ellipsization="end",
            max_chars_width=10
        )
        name_box = Box(orientation="v", spacing=2, h_expand=False, children=[name_label, author_label])

        description = meta.get("description", "")
        info_btn = Button(
            style_classes=["pack-card-info"],
            tooltip_markup=description or "No description available",
            child=Icon(icon_name="info", icon_size=16),
            h_expand=True,
            h_align="end"
        )
        info_btn.set_relief(Gtk.ReliefStyle.NONE)

        info_row = Box(
            orientation="h",
            spacing=8,
            style_classes=["pack-card-info-row"],
            children=[name_box, info_btn],
        )

        self.btn_row = Box(orientation="h", spacing=1, style_classes=["pack-card-btn-row"])

        self.download_btn = self._make_btn(
            "download-simple", "Download", ["pack-card-btn", "pack-card-download-btn"]
        )
        self.download_btn.connect("clicked", self._on_download_clicked)

        self.remove_btn = self._make_btn(
            "trash", "Remove", ["pack-card-btn", "pack-card-remove-btn"]
        )
        self.remove_btn.connect("clicked", self._on_remove_clicked)

        # action_btn serves as Apply / Enable / Disable / Applied depending on state
        self.action_btn = self._make_btn(
            "check", "Apply", ["pack-card-btn", "pack-card-apply-btn"]
        )
        self.action_btn.connect("clicked", self._on_action_clicked)

        self.add(preview)
        self.add(info_row)
        self.add(self.btn_row)

        service.connect("pack-changed", self._on_pack_changed)

        self._update_ui()

    def _make_btn(self, icon_name: str, label: str, style_classes: list) -> Button:
        return Button(
            h_expand=True,
            style_classes=style_classes,
            child=Box(
                orientation="h",
                spacing=6,
                h_align="center",
                children=[
                    Icon(icon_name=icon_name, icon_size=16),
                    Label(label=label),
                ],
            ),
        )

    def _get_icon_and_label(self, btn: Button):
        box = btn.get_child()
        children = box.get_children()
        return children[0], children[1]

    def _set_action_btn_state(self, icon_name: str, label: str, style_class: str):
        ctx = self.action_btn.get_style_context()
        for cls in ["pack-card-apply-btn", "pack-card-active-btn"]:
            ctx.remove_class(cls)
        ctx.add_class(style_class)

        icon, lbl = self._get_icon_and_label(self.action_btn)
        icon.set_property("icon-name", icon_name)
        lbl.set_label(label)

    def _add_remove_btn(self):
        if not self.is_protected:
            self.btn_row.add(self.remove_btn)

    def _is_active(self) -> bool:
        if self.allow_disable:
            return self.service.is_enabled(self.meta.get("name"))
        return self.service.get_active_pack() == self.meta.get("name")

    def _update_ui(self):
        is_downloaded = self.meta.get("downloaded", False)
        is_active = self._is_active()

        ctx = self.get_style_context()
        if is_active and not self.allow_disable:
            ctx.add_class("pack-card-active")
        else:
            ctx.remove_class("pack-card-active")

        for child in self.btn_row.get_children():
            self.btn_row.remove(child)

        if not is_downloaded:
            self.btn_row.add(self.download_btn)

        elif self.allow_disable:
            if is_active:
                self._set_action_btn_state("x", "Disable", "pack-card-active-btn")
            else:
                self._set_action_btn_state("check", "Enable", "pack-card-apply-btn")
            self._add_remove_btn()
            self.btn_row.add(self.action_btn)

        elif is_active and self.allow_deactivate:
            self._set_action_btn_state("x", "Disable", "pack-card-active-btn")
            self._add_remove_btn()
            self.btn_row.add(self.action_btn)

        else:
            if is_active:
                self._set_action_btn_state("check-circle", "Applied", "pack-card-active-btn")
                self.btn_row.add(self.action_btn)
            else:
                self._set_action_btn_state("check", "Apply", "pack-card-apply-btn")
                self._add_remove_btn()
                self.btn_row.add(self.action_btn)

        self.btn_row.show_all()

    def _on_download_clicked(self, *_):
        self.download_btn.set_sensitive(False)
        icon, lbl = self._get_icon_and_label(self.download_btn)
        icon.set_property("icon-name", "spinner")
        lbl.set_label("Downloading...")
        self.service.download_pack(self.meta.get("name"))

    def _on_remove_clicked(self, *_):
        if self.is_protected:
            return
        self.service.uninstall_pack(self.meta.get("name"))

    def _on_action_clicked(self, *_):
        name = self.meta.get("name")
        is_active = self._is_active()

        if self.allow_disable:
            if is_active:
                self.service.disable_pack(name)
            else:
                self.service.enable_pack(name)
        else:
            if is_active:
                if not self.allow_deactivate:
                    return
                self.service.set_pack(None)
            else:
                self.service.set_pack(name)

    def _on_pack_changed(self, _, pack_name: str):
        if pack_name == self.meta.get("name"):
            if self.allow_disable:
                self.meta["enabled"] = self.service.is_enabled(pack_name)
        self._update_ui()