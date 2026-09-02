from .base import BaseButton
from snippets import Icon
from services.singletons import weather
 
class WeatherButton(BaseButton):
    def __init__(self, monitor_id, vertical, variant=None, **kwargs):
        super().__init__(
            icon=Icon(icon_size=18, style_classes=["weather-icon"], icon_name="cloud"),
            label="--°C",
            variant=variant or "icon+label",
            **kwargs,
        )
        weather.connect("notify::weather-icon", lambda obj, _: self._update_icon(obj.weather_icon))
        weather.connect("notify::temperature", lambda obj, _: self._update_label(
            f"{round(obj.temperature)}°C" if obj.temperature is not None else "--°C"
        ))
        if weather.weather_icon:
            self._update_icon(weather.weather_icon)
        if weather.temperature is not None:
            self._update_label(f"{round(weather.temperature)}°C")