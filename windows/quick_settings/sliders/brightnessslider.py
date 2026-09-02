from .slider import SliderBox
from snippets import Icon
from services.singletons import brightness

class BrightnessSlider(SliderBox):
    def __init__(self, **kwargs):
        self.saved_brightness = 0
        self.scale = None

        super().__init__(
            left_icon=Icon(icon_name="seal", icon_size=16),
            on_left_click=lambda *_: self._handle_brightness_click(),
            scale_min=1,
            scale_max=100,
            scale_value=(brightness.screen_brightness / brightness.max_screen) * 100,
            on_scale_change=lambda scale: setattr(brightness, "screen_brightness", (scale.get_value() / 100) * brightness.max_screen),
            **kwargs,
        )
        brightness.connect("screen",
            lambda _, percent: self.scale.set_value(percent) if self.scale else None,
        )

    def _handle_brightness_click(self):
        min_brightness = brightness.max_screen * 0.02
        if brightness.screen_brightness == min_brightness:
            brightness.screen_brightness = self.saved_brightness
        else:
            self.saved_brightness = brightness.screen_brightness
            brightness.screen_brightness = min_brightness