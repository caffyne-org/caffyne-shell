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
from snippets import enable_blur, disable_blur, free_blur
from snippets.blur.region_trace import Rect
from snippets.blur.blur import set_blur_regions
from user_options import user_options
import cairo
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
                Image(icon_name=notification.app_icon, icon_size=16) if notification.app_icon else Icon(icon_name="bell-simple-duotone"),
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
            def on_map(label, *_):
                layout = label.get_layout()
                line_count = layout.get_line_count()
                
                if line_count <= 1:
                    _, line_height = layout.get_pixel_size()
                    label.set_size_request(-1, line_height)
                else:
                    self.desc_label.set_size_request(-1, layout.get_pixel_size()[1])
                label.disconnect_by_func(on_map)

            self.desc_label.connect("map", on_map)

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
                children=[self.header, self.content, actions_box],
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
        self._blur_ctx = None
        self._container = None
        
        container = NotificationContainer(window=self, monitor=monitor)
        self._container = container
        
        super().__init__(
            anchor="top right",
            monitor=monitor,
            title="caffyne-shell-notifications",
            layer="overlay",
            child=Box(
                style_classes=["notification-window"],
                children=[container],
            ),
            exclusive=False,
        )

    def notify_added(self):
        GLib.timeout_add(50, self._refresh_blur)

    def notify_removed(self):
        GLib.timeout_add(350, self._refresh_blur)

    def _apply_blur(self):
        if not self._blur_ctx and user_options.theme.blur:
            self._blur_ctx = enable_blur(self)
        self._refresh_blur()
    def set_visible(self, visible: bool):
        if visible:
            super().set_visible(visible)
            GLib.timeout_add(50, self._apply_blur)
        else:
            if self._blur_ctx:
                disable_blur(self._blur_ctx)
                free_blur(self._blur_ctx)
                self._blur_ctx = None
                GLib.timeout_add(50, lambda: super().set_visible(visible))

    def _trace_notifications(self, erode=4):
        if not self._container:
            print("no container")
            return []

        results = []
        try:
            for child in self._container.get_children():
                widget = child.get_children()[0].get_children()[0]
                if not widget:
                    continue
                alloc = widget.get_allocation()
                w, h = alloc.width, alloc.height
                if w <= 0 or h <= 0:
                    continue

                try:
                    cx, cy = widget.translate_coordinates(self, 0, 0)
                except Exception:
                    continue

                surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
                cr = cairo.Context(surface)
                cr.set_operator(cairo.OPERATOR_CLEAR)
                cr.paint()
                cr.set_operator(cairo.OPERATOR_OVER)

                style_ctx = widget.get_style_context()
                Gtk.render_background(style_ctx, cr, erode, erode, w - erode * 2, h - erode * 2)

                data   = surface.get_data()
                stride = surface.get_stride()

                raw = []
                for y in range(0, h, 1):
                    x = 0
                    while x < w:
                        if data[y * stride + x * 4 + 3] > 20:
                            start_x = x
                            while x < w and data[y * stride + x * 4 + 3] > 20:
                                x += 1
                            raw.append(Rect(start_x, y, x - start_x, 1))
                        else:
                            x += 1

                merged = []
                for rect in raw:
                    found = False
                    for m in reversed(merged):
                        if m.x == rect.x and m.width == rect.width and m.y + m.height == rect.y:
                            m.height += rect.height
                            found = True
                            break
                    if not found:
                        merged.append(Rect(rect.x, rect.y, rect.width, rect.height))

                for r in merged:
                    results.append((cx + r.x, cy + r.y - 2, r.width, r.height))
        except Exception:
            pass
        return results

    def _refresh_blur(self):
        if self._blur_ctx and user_options.theme.blur:
            regions = self._trace_notifications(erode=12)
            if regions:
                set_blur_regions(self._blur_ctx, regions)
        return False
    def destroy(self):
        if self._blur_ctx:
            disable_blur(self._blur_ctx)
            free_blur(self._blur_ctx)
        super().destroy()