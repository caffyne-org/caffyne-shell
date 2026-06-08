from fabric.widgets.box import Box

from fabric.widgets.label import Label

from services.singletons import weather
from snippets import Applet, AppletPage, Icon
import datetime

import cairo
from gi.repository import Gtk

def format_hour(time_str: str) -> str:
    if "T" not in time_str:
        return time_str
    hour_24 = int(time_str.split("T")[1][:2])

    if hour_24 == 0:
        return "12AM"
    elif hour_24 < 12:
        return f"{hour_24}AM"
    elif hour_24 == 12:
        return "12PM"
    else:
        return f"{hour_24 - 12}PM"

def format_day(date_str: str) -> str:
    try:
        date_obj = datetime.datetime.fromisoformat(date_str)
        return date_obj.strftime("%A")[:2]
    except:
        return "??"

def get_icon_from_code(code: int) -> str:
    emoji, icon, desc = weather.get_weather_info_for_code(code)
    return icon

def HourlyForecastItem(hour_data: dict):
    time_str = hour_data.get("time", "")
    temp = hour_data.get("temperature", 0)
    code = hour_data.get("weather_code", 0)

    return Box(
        orientation="v",
        spacing=4,
        style_classes=["hourly-item"],
        children=[
            Label(
                label=format_hour(time_str),
                style_classes=["hourly-time"]
            ),
            Icon(
                icon_name=get_icon_from_code(code),
                icon_size=24,
                style_classes=["hourly-icon"]
            ),
            Label(
                label=f"{temp:.0f}°",
                style_classes=["hourly-temp"]
            ),
        ]
    )

class TemperatureBar(Gtk.DrawingArea):
    def __init__(self, min_temp: float, max_temp: float, global_min: float, global_max: float, **kwargs):
        super().__init__(**kwargs)
        self._min_temp = min_temp
        self._max_temp = max_temp
        self._global_min = global_min
        self._global_max = global_max
        self.set_hexpand(True)
        self.set_size_request(-1, 6)
        self.get_style_context().add_class("temp-bar")
        self.connect("draw", self._on_draw)

    def _on_draw(self, widget, cr: cairo.Context):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        style_ctx = widget.get_style_context()

        fg_color = style_ctx.get_color(Gtk.StateFlags.NORMAL)
        bg_color = style_ctx.get_background_color(Gtk.StateFlags.NORMAL)

        border_radius = style_ctx.get_property("border-radius", Gtk.StateFlags.NORMAL)
        radius = min(int(border_radius), height // 2) if isinstance(border_radius, (int, float)) else height // 2

        total_range = self._global_max - self._global_min or 1
        left_frac = (self._min_temp - self._global_min) / total_range
        fill_frac = (self._max_temp - self._min_temp) / total_range

        left_x = left_frac * width
        fill_w = fill_frac * width

        def rounded_rect(x, y, w, h, r):
            cr.new_sub_path()
            cr.arc(x + r, y + r, r, 3.14, 3.14 * 1.5)
            cr.arc(x + w - r, y + r, r, 3.14 * 1.5, 0)
            cr.arc(x + w - r, y + h - r, r, 0, 3.14 * 0.5)
            cr.arc(x + r, y + h - r, r, 3.14 * 0.5, 3.14)
            cr.close_path()

        cr.set_source_rgba(bg_color.red, bg_color.green, bg_color.blue, bg_color.alpha)
        rounded_rect(0, 0, width, height, radius)
        cr.fill()

        cr.set_source_rgba(fg_color.red, fg_color.green, fg_color.blue, fg_color.alpha)
        rounded_rect(left_x, 0, fill_w, height, radius)
        cr.fill()

        return False

def DailyForecastItem(day_data: dict, all_days: list):
    date = day_data.get("date", "")
    temp_max = round(day_data.get("temperature_max", 0))
    temp_min = round(day_data.get("temperature_min", 0))
    code = day_data.get("weather_code", 0)

    global_min = min(round(day.get("temperature_min", 0)) for day in all_days) if all_days else 0
    global_max = max(round(day.get("temperature_max", 0)) for day in all_days) if all_days else 30

    bar = TemperatureBar(temp_min, temp_max, global_min, global_max)
    bar_wrapper = Box(style="padding: 2px;", v_expand=True, v_align="center", h_expand=True)
    bar_wrapper.pack_start(bar, True, True, 0)
    bar.show()
    day_label = Label(label=format_day(date), style_classes=["daily-day"])
    day_label.set_xalign(0.0)

    min_label = Label(label=f"{temp_min}°", style_classes=["daily-min-temp"])
    min_label.set_xalign(0.0)

    max_label = Label(label=f"{temp_max}°", style_classes=["daily-max-temp"])
    max_label.set_xalign(1.0)
    return Box(
        spacing=12,
        style_classes=["daily-item"],
        children=[
            day_label,
            Icon(icon_name=get_icon_from_code(code), icon_size=16, style_classes=["daily-icon"]),
            min_label,
            bar_wrapper,
            max_label,
        ]
    )

class WeatherPopup(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            spacing=18,
            style_classes=["weather-popup"],
            **kwargs
        )

        self._hourly_box = Box(spacing=20, style_classes=["hourly-forecast"])
        self._daily_box = Box(orientation="v", spacing=12, style_classes=["daily-forecast"])
        self._temp_label = Label(
            label=f"{weather.temperature:.0f}°C" if weather.temperature else "---",
            style="font-size: 24px; font-weight: 600;",
            style_classes=["current-temp"]
        )
        self._icon = Icon(icon_name="cloud-duotone", icon_size=36, style_classes=["current-icon"])
        self._high_label = Label(label="--°", style_classes=["high-temp"])
        self._low_label = Label(label="--°", style_classes=["low-temp"])

        self.children = [
            Box(
                orientation="v",
                spacing=36,
                style_classes=["weather-main"],
                children=[
                    self._create_current_weather(),
                    self._hourly_box,
                ]
            ),
            self._daily_box,
        ]

        weather.connect("notify::hourly-forecast", lambda *_: self._rebuild_hourly())
        weather.connect("notify::daily-forecast", lambda *_: self._rebuild_daily())
        weather.connect("notify::temperature", lambda *_: self._update_current())
        weather.connect("notify::weather-icon", lambda *_: self._update_current())
        weather.connect("notify::daily-forecast", lambda *_: self._update_minmax())

        if weather.hourly_forecast:
            self._rebuild_hourly()
        if weather.daily_forecast:
            self._rebuild_daily()
            self._update_minmax()

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
                            children=[self._high_label, Icon(icon_name="caret-up-duotone", icon_size=18)],
                        ),
                        Box(
                            h_align="end",
                            h_expand=True,
                            spacing=4,
                            children=[self._low_label, Icon(icon_name="caret-down-duotone", icon_size=18)],
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

    def _rebuild_daily(self, *_):
        for child in self._daily_box.children:
            self._daily_box.remove(child)
        daily = weather.daily_forecast or []
        for day in daily[:3]:
            self._daily_box.add(DailyForecastItem(day, daily[:3]))

class WeatherApplet(Applet):
    def __init__(self, parent, *kwargs):
        self.title = Label(label=weather.location, style_classes=["applet-header-label"])
        self.main_page = AppletPage(
            stack=self,
            child=WeatherPopup(),
            first=True,
            label=self.title
        )
        super().__init__(
            main_menu=self.main_page
        )
        weather.connect("notify::location", lambda obj, _: self.title.set_label(obj.location))
