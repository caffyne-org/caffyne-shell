from fabric.widgets.box import Box
from snippets import Icon
from .button import QSButton
from services.singletons import power_profiles

class PowerModes(Box):
    def __init__(self, wide=False, **kwargs):
        self.saver_btn = QSButton(
            icon=Icon(icon_name="leaf", icon_size=16),
            on_activate=lambda _: power_profiles.set_active_profile("power-saver"),
            style_classes=["qs-power-profile-button", "wide"] if wide else ["qs-power-profile-button"],
            h_align="center",
        )
        self.balanced_btn = QSButton(
            icon=Icon(icon_name="scales", icon_size=16),
            on_activate=lambda _: power_profiles.set_active_profile("balanced"),
            style_classes=["qs-power-profile-button", "wide"] if wide else ["qs-power-profile-button"],
            h_align="center",
        )
        self.performance_btn = QSButton(
            icon=Icon(icon_name="speedometer", icon_size=16),
            on_activate=lambda _: power_profiles.set_active_profile("performance"),
            style_classes=["qs-power-profile-button", "wide"] if wide else ["qs-power-profile-button"],
            h_align="center",
        )

        super().__init__(
            style_classes=["qs-power-modes-box"],
            spacing=6,
            children=[self.saver_btn, self.balanced_btn, self.performance_btn],
            **kwargs,
        )

        power_profiles.connect("changed", lambda *_: self._update_active())
        self._update_active()

    def _update_active(self):
        profile = power_profiles.active_profile
        self.saver_btn.active = profile == "power-saver"
        self.balanced_btn.active = profile == "balanced"
        self.performance_btn.active = profile == "performance"