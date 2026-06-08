from loguru import logger
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.system_tray.service import SystemTrayItem
from snippets import Icon
from services.singletons import edit_mode, watcher
from user_options import user_options
from utils.helpers import popup_with_blur
from gi.repository import GLib


class TrayItem(EventBox):
    def __init__(self, item: SystemTrayItem, **kwargs):
        self._item = item
        super().__init__(
            style_classes=["tray-item"],
            tooltip_text=self._get_tooltip(),
            child=self._build_icon(),
            **kwargs,
        )
        self._item.changed.connect(self._on_item_changed)
        self.connect("button-release-event", self._on_button_press)

    def _get_tooltip(self) -> str:
        tooltip = self._item.tooltip
        return (
            tooltip.description
            or tooltip.title
            or (self._item.title.title() if self._item.title else None)
            or ""
        )
    
    def _build_icon(self) -> Image:
        if self._item.icon_name:
            return Image(icon_name=self._item.icon_name, icon_size=20)
        pixbuf = self._item.get_preferred_icon_pixbuf(20)
        if pixbuf is not None:
            return Image(pixbuf=pixbuf)
        return Image(icon_name="image-missing", icon_size=20)
    
    def _on_item_changed(self, *_):
        # rebuild icon and tooltip on change
        child = self._build_icon()
        self.get_child().destroy() if self.get_child() else None
        self.add(child)
        child.show()
        self.set_tooltip_text(self._get_tooltip())

    def _on_button_press(self, _, event):
        if edit_mode.edit_mode:
            return False
        match event.button:
            case 1:
                try:
                    self._item.activate_for_event(event)
                except Exception as e:
                    logger.warning(f"[TrayItem] can't activate {self._item.identifier} ({e})")
            case 3:
                menu = self._item.get_menu()
                if menu:
                    if user_options.theme.blur:
                        popup_with_blur(menu, event)
                    else:
                        menu.popup_at_pointer(event)
                else:
                    self._item.invoke_menu_for_event(event)


class SystemTray(Box):
    def __init__(self, monitor_id=None, vertical=False, variant="", **kwargs):
        self._items: dict[str, TrayItem] = {}

        self.edit_overlay = Box(
            spacing=4,
            visible=False,
            style_classes=["bar-button", "edit-overlay"],
            h_align="center",
            h_expand=True,
            children=[
                Icon(icon_name="dots-three-circle-duotone"),
                Label(label="Tray"),
            ],
        )

        self.tray = Box(
            style_classes=["bar-button", "system-tray"],
            spacing=8,
        )

        super().__init__(
            spacing=0,
            children=[self.edit_overlay, self.tray],
            **kwargs,
        )

        self.tray.set_visible(False)
        self.connect("realize", self._on_realize)

    def _on_realize(self, *_):
        watcher.connect("item-added", self._on_item_added)
        watcher.connect("item-removed", self._on_item_removed)
        edit_mode.connect("notify::edit-mode", lambda *_: self._update_visibility())
        GLib.idle_add(self._update_visibility)

    def _on_item_added(self, _, identifier: str):
        if identifier in self._items:
            return
        item = watcher.items.get(identifier)
        if not item:
            return
        tray_item = TrayItem(item)
        self._items[identifier] = tray_item
        self.tray.add(tray_item)
        tray_item.show()
        self._update_visibility()

    def _on_item_removed(self, _, identifier: str):
        if identifier in self._items:
            widget = self._items.pop(identifier)
            self.tray.remove(widget)
            self._update_visibility()

    def _update_visibility(self):
        has_items = bool(self._items)
        is_editing = edit_mode.edit_mode
        self.tray.set_visible(has_items)
        self.edit_overlay.set_visible(is_editing and not has_items)
        self.get_parent().get_parent().set_visible(has_items or is_editing)
