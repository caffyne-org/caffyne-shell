from datetime import datetime
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.overlay import Overlay
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.widgets.image import Image
from fabric.widgets.circularprogressbar import CircularProgressBar
from snippets import Icon, ClippingBox, AppletReveal
from services.singletons import notifications, wm
from services.notification_store import notification_store
from bar_widgets.workspaces import get_connector_from_monitor_id
from gi.repository import GLib, Gtk, Gdk, GdkPixbuf
from snippets import BlurBox
from user_options import user_options
from utils.sounds import play_sound
NOTIFICATION_IMAGE_SIZE = 62

class NotificationContainer(Box):
    def __init__(self, window, monitor: int):
        self._window = window
        self._monitor = monitor
        super().__init__(
            orientation="v",
            v_align="start",
            style_classes=["notification-container"],
        )
        notifications.connect("notification-added", lambda _, nid: self._on_notified(nid))

    def remove_notification(self, notification_widget):
        revealer = notification_widget.get_parent()
        if revealer:
            revealer.close(on_done = lambda: revealer.destroy())

        self._window.notify_removed()
        if len(self.get_children()) == 0:
            self._window.set_visible(False)

    def _on_notified(self, nid: int):
        if user_options.settings.dnd:
            return
        notification = notifications.get_notification_from_id(nid)
        if not notification:
            return
        connector = get_connector_from_monitor_id(self._monitor)
        if wm.active_output == connector:
            widget = NotificationWidget(
                timeout=5000,
                notification=notification,
                container=self,
                popup=True,
            )
            revealer = AppletReveal(
                direction="down",
                child=widget,
            )
            self.add(revealer)
            self.reorder_child(revealer, 0)
            revealer.open()
            self._window.set_visible(True)
            self._window.notify_added()

            notification.connect(
                "closed",
                lambda *_: self.remove_notification(widget),
            )

class NotificationWidget(EventBox):
    def __init__(self, timeout, notification, container, popup: bool = False):

        super().__init__(
        )

        self.timeout = timeout
        self.elapsed = 0
        self.is_hovered = False
        self.timeout_id = None
        self._container = container
        self._notification = notification
        self._created_at = datetime.now().strftime("%H:%M")

        self.progress = CircularProgressBar(
            style_classes=["progress-bar"],
            value=0,
            start_angle=270,
            end_angle=630,
            min_value=0,
            max_value=1,
            line_width=2,
            size=[28, 28],
        ) if popup else Box()

        self.header = Box(
            h_expand=True,
            spacing=4,
            # style="padding: 4px 0px;" if not popup else "",
            children=[
                Image(icon_name=notification.app_icon, icon_size=16) if notification.app_icon else Icon(icon_name="bell-simple"),
                Label(style="opacity: 0.6; font-size: 11px;", label=notification.app_name),
                Box(
                    h_expand=True,
                    spacing=12,
                    h_align="end",
                    children=[
                        Label(
                            style="opacity: 0.6; font-size: 11px;",
                            label=self._created_at,
                        ) if not popup else Label(),
                        Overlay(
                            child=self.progress,
                            overlays=Button(
                                style_classes=["notification-dismiss-button"],
                                child=Box(h_align="center", children=Icon(icon_name="x")),
                                on_clicked=lambda *_: self._notification.close("dismissed-by-user"),
                            ),
                        ) if popup 
                            else Button(
                            style_classes=["notification-remove-button"],
                            child=Box(h_align="center", children=Icon(icon_name="x")),
                            on_clicked=lambda *_:self._remove_from_history(),
                        ),
                    ],
                ),
            ],
        )

        image_pixbuf = notification.image_pixbuf
        image_widget = Image(
            pixbuf=image_pixbuf.scale_simple(
                NOTIFICATION_IMAGE_SIZE,
                NOTIFICATION_IMAGE_SIZE,
                GdkPixbuf.InterpType.BILINEAR,
            ),
            style_classes=["notification-icon"],
            style="border-radius: 10px;",
            h_align="start",
            v_align="start",
        ) if image_pixbuf else Box()
        self.desc_label = Label(
            label=notification.body or "",
            line_wrap="word-char",
            h_align="start",
            h_expand=True,
            # v_expand=True,
            ellipsization="end",
            style_classes=["notification-body"] if popup else ["notification-body", "history"],
            visible=bool(notification.body),
        )
        
        self.desc_label.set_xalign(0)
        self.desc_label.set_lines(2)
        if popup:
            self.desc_label.set_size_request(-1, self.desc_label.get_layout().get_pixel_size()[1])


        self.content = Box(
            spacing=14,
            children=[
                ClippingBox(style_classes=["notification-image-container"], children=image_widget),
                Box(
                    orientation="v",
                    # spacing=6 if not popup else 0,
                    children=[
                        Label(
                            ellipsization="end",
                            label=notification.summary or "",
                            use_markup=True,
                            h_align="start",
                            visible=bool(notification.summary),
                            style_classes=["notification-summary"],
                        ),
                        self.desc_label
                    ],
                )
            ] if image_pixbuf else Box(
                    orientation="v",
                    children=[
                        Label(
                            ellipsization="end",
                            label=notification.summary or "",
                            use_markup=True,
                            h_align="start",
                            visible=bool(notification.summary),
                            style_classes=["notification-summary"],
                        ),
                        self.desc_label
                    ],
                ),
        )

        actions_box = Box(
            homogeneous=True,
            style="margin-top: 0.75rem;" if notification.actions else "",
            spacing=12,
            children=[
                Button(
                    h_expand=True,
                    child=Label(label=action.label),
                    on_clicked=lambda _, a=action: a.invoke(),
                    style_classes=["notification-action"] if popup else ["notification-action", "history"],
                )
                for action in notification.actions
            ],
        )

        self.add(
            Box(
                style_classes=["notification"] if popup else ["history-notification"],
                orientation="v",
                spacing=4,
                children=[self.header, self.content, actions_box] if popup else [self.header, self.content],
            )
        )

        if popup != False:
            self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
            self.connect("enter-notify-event", lambda *_: setattr(self, "is_hovered", True))
            self.connect("leave-notify-event", lambda *_: setattr(self, "is_hovered", False))
            self.timeout_id = GLib.timeout_add(16, self._tick)

    def _tick(self):
        if not self.is_hovered:
            self.elapsed += 16
        self.progress.value = max(0.0, self.elapsed / self.timeout)
        if self.elapsed >= self.timeout:
            self._close_and_expire()
            return False
        return True

    def _close_and_expire(self):
        if self.timeout_id:
            GLib.source_remove(self.timeout_id)
            self.timeout_id = None
        self._notification.close("expired")
    def _remove_from_history(self):
        notification_store.remove(self._notification)

class NotificationWindow(Window):
    def __init__(self, monitor: int):
        self._container = None

        container = NotificationContainer(window=self, monitor=monitor)
        self._container = container

        # Every notification is its own reveal, so the box tracks all of them
        # at once and unions what each one's shader is drawing.
        self.blur = BlurBox(
            child=Box(
                style_classes=["notification-window"],
                children=[container],
            ),
            enabled=user_options.theme.blur,
        )

        super().__init__(
            anchor="top right",
            monitor=monitor,
            title="caffyne-shell-notifications",
            layer="overlay",
            child=self.blur,
            exclusive=False,
        )

    def notify_added(self):
        GLib.idle_add(lambda: play_sound("notification"))
        self.blur.queue_refresh()

    def notify_removed(self):
        self.blur.queue_refresh()

    def set_visible(self, visible: bool):
        self.blur.enabled = visible and user_options.theme.blur
        super().set_visible(visible)

