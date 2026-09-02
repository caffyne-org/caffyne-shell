from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from snippets import Applet, AppletPage, Icon, ClippingScrolledWindow
from windows.notifications import NotificationWidget
from user_options import user_options
from services.notification_store import notification_store

class NotificationContainer(Box):
    def __init__(self, applet):
        self._applet = applet
        super().__init__(
            orientation="v",
            spacing=6,
            v_align="start",
            style_classes=["notification-container"],
        )
        notification_store.connect("changed", lambda *_: self._rebuild())
        self._rebuild()

    def _rebuild(self):
        for child in self.get_children():
            child.destroy()
        for notification in notification_store.items:
            widget = NotificationWidget(
                timeout=5000,
                notification=notification,
                container=self,
                popup=False,
            )
            self.add(widget)
        self._update_title()

    def _update_title(self):
        count = len(notification_store.items)
        self._applet.title.set_label(f"Notifications · {count}")
        self._applet.update_main_box()

    def remove_all(self):
        notification_store.remove_all()

class NotificationHistoryApplet(Applet):
    def __init__(self, parent, **kwargs):
        self.title = Label(
            label="Notifications · 0",
            style_classes=["applet-header-label"]
        )

        self.notifications = NotificationContainer(applet=self)

        self.scroll_view = ClippingScrolledWindow(
            style_classes=["notification-history-container"],
            child=self.notifications,
            max_content_size=(324, 276)
        )

        self.placeholder = Box(
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            style_classes=["menu-list-placeholder"],
            children=[
                Label(
                    v_expand=True,
                    v_align="center",
                    label="No Notifications",
                    style_classes=["menu-list-placeholder-label"],
                )
            ]
        )

        self.main_box = Stack(
            transition_type="crossfade",
            transition_duration=200,
            children=[self.scroll_view, self.placeholder],
        )

        self.main_page = AppletPage(
            stack=self,
            child=self.main_box,
            header_right_children=Box(
                spacing=12,
                children=[
                    Button(
                        style_classes=["applet-misc-button"],
                        child=Icon(icon_name="bell-slash" if user_options.settings.dnd else "bell-simple-z"),
                        on_clicked=lambda button: self._toggle_dnd(button),
                    ),
                    Button(
                        style_classes=["applet-misc-button"],
                        child=Icon(icon_name="trash"),
                        on_clicked=lambda *_: self.notifications.remove_all(),
                    ),
                ],
            ),
            first=True,
            label=self.title,
        )

        super().__init__(main_menu=self.main_page, **kwargs)
        self.update_main_box()

    def update_main_box(self):
        if not hasattr(self, "main_box"):
            return
        if notification_store.items:
            self.main_box.set_visible_child(self.scroll_view)
        else:
            self.main_box.set_visible_child(self.placeholder)

    def _toggle_dnd(self, button):
        user_options.settings.dnd = not user_options.settings.dnd
        if user_options.settings.dnd:
            button.get_child().icon_name = "bell-slash"
        else:
            button.get_child().icon_name = "bell-simple-z"
        user_options.save()