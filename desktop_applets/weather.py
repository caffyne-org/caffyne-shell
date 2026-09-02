import datetime
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from gi.repository import Gtk, GLib
from windows.weather_popup import HourlyForecastItem
from services.singletons import weather
from snippets import Icon

class DesktopWeather(Box):
    def __init__(self, **kwargs):
        super().__init__(
            style_classes=["desktop-applet", "large"],
            orientation="v",
            v_align="center",
            v_expand=True,
            spacing=6,
            **kwargs
        )

        self._hourly_box = Box(spacing=28, style_classes=["hourly-forecast"], h_expand=False, h_align="center")
        self._temp_label = Label(
            label=f"{weather.temperature:.0f}°C" if weather.temperature else "---",
            style_classes=["current-temp"]
        )
        self._icon = Icon(icon_name="cloud", icon_size=36, style_classes=["current-icon"])
        self._high_label = Label(label="--°", style_classes=["high-temp"])
        self._low_label = Label(label="--°", style_classes=["low-temp"])

        self.children = [
            Box(
                orientation="v",
                spacing=30,
                children=[
                    self._create_current_weather(),
                    self._hourly_box,
                ]
            ),
        ]

        if weather.hourly_forecast:
            self._rebuild_hourly()
        if weather.daily_forecast:
            self._update_current()
            self._update_minmax()

        weather.connect("notify::hourly-forecast", lambda *_: self._rebuild_hourly())
        weather.connect("notify::temperature", lambda *_: self._update_current())
        weather.connect("notify::weather-icon", lambda *_: self._update_current())
        weather.connect("notify::daily-forecast", lambda *_: self._update_minmax())

    def _create_current_weather(self):
        return Box(
            spacing=0,
            style_classes=["current-weather"],
            children=[
                Box(
                    spacing=8,
                    children=[self._icon, self._temp_label],
                ),
                Box(
                    orientation="v",
                    spacing=4,
                    h_align="end",
                    h_expand=True,
                    style_classes=["current-minmax"],
                    children=[
                        Box(
                            h_align="end",
                            h_expand=True,
                            spacing=4,
                            children=[self._high_label, Icon(icon_name="caret-up", icon_size=18)],
                        ),
                        Box(
                            h_align="end",
                            h_expand=True,
                            spacing=4,
                            children=[self._low_label, Icon(icon_name="caret-down", icon_size=18)],
                        ),
                    ]
                ),
            ]
        )
    def _update_current(self, *_):
        self._temp_label.set_label(f"{weather.temperature:.0f}°C" if weather.temperature else "---")
        self._icon.set_property("icon-name", weather.weather_icon)

    def _update_minmax(self, *_):
        daily = weather.daily_forecast
        if not daily:
            return
        today = daily[0]
        self._high_label.set_label(f"{round(today.get('temperature_max', 0))}°")
        self._low_label.set_label(f"{round(today.get('temperature_min', 0))}°")

    def _rebuild_hourly(self, *_):
        for child in self._hourly_box.children:
            self._hourly_box.remove(child)
        for hour in (weather.hourly_forecast or [])[:5]:
            self._hourly_box.add(HourlyForecastItem(hour))
        # window = self.get_toplevel()
        # window.hide()
        # window.show_all()
