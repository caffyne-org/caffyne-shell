from .hacktk.hacktk import HackedStack
from .shader_stack import ShaderStack

TRANSITION = "stack_transition"


class HackedAppletStack(HackedStack):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        from services.animation import animation_service

        self._anim_service = animation_service
        self._anim_handler = animation_service.connect(
            "transition-changed", self._on_transition_changed
        )
        self._on_transition_changed(None, TRANSITION)
        self.connect("destroy", self._on_destroy)

    def _on_transition_changed(self, _, transition: str):
        if transition != TRANSITION:
            return
        s = self._anim_service.get_transition_settings(TRANSITION)
        self.bezier_curve = tuple(s.get("bezier", self.bezier_curve))
        self.animator.duration = s.get("duration", self.animator.duration)

    def _on_destroy(self, *_):
        if self._anim_handler:
            self._anim_service.disconnect(self._anim_handler)
            self._anim_handler = 0


def AppletStack(*args, **kwargs) -> ShaderStack | HackedAppletStack:
    from services.animation import shaders_enabled

    variant = ShaderStack if shaders_enabled() else HackedAppletStack
    return variant(*args, **kwargs)
