from .base import BaseButton
from snippets import Icon
from services.notification_store import notification_store

class NotificationButton(BaseButton):
    VARIANTS = ["icon", "icon+label"]

    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=Icon(icon_name="bell-simple", icon_size=16),
            label="",
            variant=variant or "icon",
            **kwargs,
        )
        notification_store.connect("changed", self._on_notifications_changed)
        self._sync()

    def _on_notifications_changed(self, _):
        self._sync()

    def _sync(self):
        count = len(notification_store.items)
        if count > 0:
            self._update_icon("bell-simple-ringing")
            self._update_label(str(count))
        else:
            self._update_icon("bell-simple")
            self._update_label("0")