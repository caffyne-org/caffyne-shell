from fabric.widgets.box import Box
from ....common.components import AppPage
from ....common.rows import PageSection, SliderRow, DropdownRow, SwitchRow, InfoRow
from ..packs.components import InstalledPacksBrowser, AvailablePacksBrowser
from services.animation import animation_service, EASING_KEYS, EASING_LABELS

from .bezier_editor import BezierEditor


EASING_OPTIONS = [EASING_LABELS[key] for key in EASING_KEYS]
LABEL_TO_EASING = {label: key for key, label in EASING_LABELS.items()}


class TransitionSection(Box):
    def __init__(self, transition: str, **kwargs):
        super().__init__(orientation="v", spacing=1, **kwargs)
        self.transition = transition
        self._syncing = False

        s = animation_service.get_transition_settings(transition)
        self._sides = ("open", "close") if "open_bezier" in s else ("both",)

        self._duration_rows: dict[str, SliderRow] = {}
        self._easing_rows: dict[str, DropdownRow] = {}

        for side in self._sides:
            prefix = "" if side == "both" else f"{side.capitalize()} "
            duration = s["duration"] if side == "both" else s[f"{side}_duration"]

            duration_row = SliderRow(
                name=f"{prefix}Duration",
                value=duration,
                min_value=0.05, max_value=1.0, step=0.05,
                on_released=lambda scale, event, side=side: self._on_duration(scale, side),
                value_formatter=lambda val: f"{val:.2f}s",
            )
            easing_row = DropdownRow(
                name=f"{prefix}Easing",
                options=EASING_OPTIONS,
                active=EASING_LABELS[animation_service.get_transition_easing(transition, side)],
                on_changed=lambda label, side=side: self._on_easing(label, side),
            )

            self._duration_rows[side] = duration_row
            self._easing_rows[side] = easing_row
            self.add(duration_row)
            self.add(easing_row)

        animation_service.connect("transition-changed", self._on_service_changed)


    def _on_duration(self, scale, side: str):
        if self._syncing:
            return
        animation_service.set_transition_duration(
            self.transition, round(scale.get_value(), 2), side
        )

    def _on_easing(self, label: str, side: str):
        if self._syncing:
            return
        animation_service.set_transition_easing(
            self.transition, LABEL_TO_EASING[label], side
        )

    def _on_service_changed(self, _, transition: str):
        if transition != self.transition:
            return

        s = animation_service.get_transition_settings(self.transition)
        self._syncing = True
        try:
            for side in self._sides:
                duration = s["duration"] if side == "both" else s[f"{side}_duration"]
                self._duration_rows[side].scale.set_value(duration)
                easing = animation_service.get_transition_easing(self.transition, side)
                self._easing_rows[side].set_value(EASING_LABELS[easing], notify=False)
        finally:
            self._syncing = False


class AnimationSettingsPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
            name="Animations",
            title="Animations",
            items=[
                PageSection(
                    title="Rendering",
                    items=[
                        SwitchRow(
                            name="Shader Animations",
                            toggled=animation_service.get_shaders_enabled(),
                            on_toggle=lambda active: animation_service.set_shaders_enabled(active),
                        ),
                        InfoRow(name="Takes effect", info="After restart"),
                    ],
                ),
                PageSection(
                    title="Applet Reveal",
                    items=[TransitionSection(transition="applet_reveal")],
                ),
                PageSection(
                    title="Dash Reveal",
                    items=[TransitionSection(transition="dash_reveal")],
                ),
                PageSection(
                    title="Stack Transition",
                    items=[TransitionSection(transition="stack_transition")],
                ),
                PageSection(
                    title="Packs",
                    items=[
                        InstalledPacksBrowser(animation_service),
                    ],
                ),
            ],
            **kwargs,
        )
        
class AnimationDownloadPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Download",
        title="Download",
        items=[
            PageSection(
                title="Download",
                items=[AvailablePacksBrowser(animation_service)],
            ),
        ],
        **kwargs,
    )