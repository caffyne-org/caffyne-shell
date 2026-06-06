from fabric.widgets.box import Box
from fabric.widgets.label import Label
from snippets import SmoothSwitch, TimeoutAdjuster
from .menu import QSAppletPage
from user_options import user_options
from services.singletons import idle, battery
from ..buttons import PowerModes


class IdleTimeoutBox(Box):
    def __init__(
        self,
        label: str,
        timeout_name: str,
        initial_ac_minutes: int = 10,
        initial_bat_minutes: int = 5,
        **kwargs,
    ):
        self.timeout_name = timeout_name

        self.enabled_switch = SmoothSwitch(
            style_classes=["smooth-switch"],
            on_user_toggle=lambda state: setattr(self, "pending_enabled", state),
        )

        self.power_adjuster = TimeoutAdjuster(
            initial_minutes=initial_ac_minutes,
            icon_name="plug-duotone",
            on_change=lambda mins: setattr(self, "pending_ac", mins),
        )

        self.bat_adjuster = TimeoutAdjuster(
            initial_minutes=initial_bat_minutes,
            icon_name="battery-vertical-full-duotone",
            on_change=lambda mins: setattr(self, "pending_bat", mins),
        ) if battery.available else None

        super().__init__(
            orientation="v",
            spacing=8,
            style_classes=["idle-timeout-box"],
            children=[
                Box(
                    spacing=12,
                    children=[
                        Label(
                            label=label,
                            style_classes=["timeout-label"],
                            h_align="start",
                            h_expand=True,
                        ),
                        self.enabled_switch,
                    ],
                ),
                Box(
                    spacing=20,
                    homogeneous=True,
                    h_expand=True,
                    h_align="end" if not battery.available else "center",
                    children=[self.power_adjuster, self.bat_adjuster] if battery.available else [self.power_adjuster],
                ),
            ],
            **kwargs,
        )

        self._load_and_snapshot(initial_ac_minutes, initial_bat_minutes)

    def _load_and_snapshot(self, fallback_ac: int, fallback_bat: int):
        saved = next(
            (t for t in user_options.timeouts.list if t["name"] == self.timeout_name),
            None,
        )
        ac  = saved["timeout_ac"]  if saved else fallback_ac
        bat = saved["timeout_bat"] if saved else fallback_bat
        ena = saved["enabled"]     if saved else True

        self._set_values(ac, bat, ena)
        self._take_snapshot()

    def _set_values(self, ac: int, bat: int, enabled: bool):
        """Update widgets without triggering dirty state via on_change."""
        self.pending_ac      = ac
        self.pending_bat     = bat
        self.pending_enabled = enabled

        self.enabled_switch.set_active(enabled)
        self.power_adjuster.set_minutes(ac)
        if self.bat_adjuster:
            self.bat_adjuster.set_minutes(bat)

    def _take_snapshot(self):
        self._snapshot = self.get_updated_rule()

    def is_dirty(self) -> bool:
        return self.get_updated_rule() != self._snapshot

    def reload(self):
        saved = next(
            (t for t in user_options.timeouts.list if t["name"] == self.timeout_name),
            None,
        )
        if saved:
            self._set_values(saved["timeout_ac"], saved["timeout_bat"], saved["enabled"])
        self._take_snapshot()

    def get_updated_rule(self) -> dict:
        return {
            "name":        self.timeout_name,
            "timeout_ac":  int(self.pending_ac),
            "timeout_bat": int(self.pending_bat),
            "enabled":     self.pending_enabled,
        }


class PowerMenu(QSAppletPage):
    def __init__(self, parent=None, stack=None, **kwargs):
        self.stack = stack
        self.parent = parent
        self.timeout_boxes = [
            IdleTimeoutBox(
                label="Dim Screen",
                timeout_name="screen-off",
                initial_ac_minutes=10,
                initial_bat_minutes=5,
            ),
            IdleTimeoutBox(
                label="Lock",
                timeout_name="lock",
                initial_ac_minutes=15,
                initial_bat_minutes=10,
            ),
            IdleTimeoutBox(
                label="Suspend",
                timeout_name="suspend",
                initial_ac_minutes=20,
                initial_bat_minutes=15,
            ),
        ]

        super().__init__(
            title="Energy",
            stack=stack,
            child=Box(
                orientation="v",
                spacing=12,
                children=[PowerModes(wide=True)] + [box for box in self.timeout_boxes],
            ),
            **kwargs,
        )

        if stack is not None:
            stack.connect("notify::visible-child", self._on_page_change)

        self.connect("realize", self._on_realize)

    def _on_realize(self, *_):
        if self.parent:
            self.parent.connect("notify::visible", self._on_window_visibility)

    def _on_window_visibility(self, window, _):
        if window.is_visible():
            self._reload()
        else:
            self._apply_if_dirty()

    def _on_page_change(self, *_):
        if self.stack.get_visible_child() is self:
            self._reload()
        else:
            self._apply_if_dirty()

    def _reload(self):
        for box in self.timeout_boxes:
            box.reload()

    def _apply_if_dirty(self):
        dirty_boxes = [box for box in self.timeout_boxes if box.is_dirty()]
        if not dirty_boxes:
            return
        updated_rules = [box.get_updated_rule() for box in self.timeout_boxes]
        user_options.timeouts.list = updated_rules
        idle.update_rules(updated_rules)
        user_options.save()
        # re-snapshot so subsequent hide/show cycles start clean
        for box in self.timeout_boxes:
            box._take_snapshot()