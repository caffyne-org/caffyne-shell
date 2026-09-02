import json
import threading
import time
import urllib.request
import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
from loguru import logger
from gi.repository import GLib
from fabric.core.service import Service, Property, Signal

CACHE_DURATION = 600
STALE_CACHE_MAX = 1800
UPDATE_INTERVAL = 600
TEMP_DIR = Path.home() / ".cache" / "caffyne-shell" / "weather"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

IP_LOCATION_API = "http://ip-api.com/json/"
WEATHER_API_BASE = "https://api.open-meteo.com/v1/forecast"

WEATHER_DATA: Dict[int, Tuple[str, str, str]] = {
    0:  ("☀️",  "sun",           "Clear sky"),
    1:  ("🌤️", "cloud-sun",      "Mainly clear"),
    2:  ("⛅",  "cloud-sun",      "Partly cloudy"),
    3:  ("☁️",  "cloud",          "Overcast"),
    45: ("🌫️", "cloud-fog",      "Fog"),
    48: ("🌫️", "cloud-fog",      "Depositing rime fog"),
    51: ("🌦️", "cloud-rain",     "Light drizzle"),
    53: ("🌦️", "cloud-rain",     "Moderate drizzle"),
    55: ("🌧️", "cloud-rain",     "Dense drizzle"),
    56: ("🌨️", "cloud-rain",     "Light freezing drizzle"),
    57: ("🌨️", "cloud-rain",     "Dense freezing drizzle"),
    61: ("🌦️", "cloud-rain",     "Slight rain"),
    63: ("🌧️", "cloud-rain",     "Moderate rain"),
    65: ("🌧️", "cloud-rain",     "Heavy rain"),
    66: ("🌨️", "cloud-rain",     "Light freezing rain"),
    67: ("🌨️", "cloud-rain",     "Heavy freezing rain"),
    71: ("❄️",  "cloud-snow",     "Slight snow"),
    73: ("🌨️", "cloud-snow",     "Moderate snow"),
    75: ("❄️",  "cloud-snow",     "Heavy snow"),
    77: ("❄️",  "cloud-snow",     "Snow grains"),
    80: ("🌦️", "cloud-rain",     "Slight rain showers"),
    81: ("🌧️", "cloud-rain",     "Moderate rain showers"),
    82: ("⛈️",  "cloud-lightning","Violent rain showers"),
    85: ("🌨️", "cloud-snow",     "Slight snow showers"),
    86: ("❄️",  "cloud-snow",     "Heavy snow showers"),
    95: ("⛈️",  "cloud-lightning","Thunderstorm"),
    96: ("⛈️",  "cloud-lightning","Thunderstorm with hail"),
    99: ("⛈️",  "cloud-lightning","Thunderstorm with heavy hail"),
}

class Cache:
    def __init__(self, cache_file: Path, max_age: int):
        self._cache_file = cache_file
        self._max_age = max_age
        self._data = None
        self._time = 0
        self._lock = threading.Lock()
        self._load_cache()

    def _load_cache(self):
        try:
            if self._cache_file.exists():
                with self._lock:
                    self._time = self._cache_file.stat().st_mtime
                    self._data = json.loads(self._cache_file.read_text())
        except Exception:
            pass

    def is_fresh(self) -> bool:
        with self._lock:
            return bool(self._data and time.time() - self._time < CACHE_DURATION)

    def is_usable(self) -> bool:
        with self._lock:
            return bool(self._data and time.time() - self._time < self._max_age)

    def get(self, allow_stale=False) -> Optional[dict]:
        if self.is_fresh() or (allow_stale and self.is_usable()):
            with self._lock:
                return self._data.copy() if self._data else None
        return None

    def set(self, data: dict):
        try:
            tmp = self._cache_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, separators=(",", ":")))
            tmp.rename(self._cache_file)
            with self._lock:
                self._data = data
                self._time = time.time()
        except Exception:
            pass

def fetch_api(url: str, timeout: int = 10) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode()) if response.status == 200 else None
    except Exception:
        return None

def get_weather_info(code: int) -> Tuple[str, str, str]:
    return WEATHER_DATA.get(code, ("🌡️", "weather-clear", "Unknown"))

def get_wind_direction(degrees: float) -> str:
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    return dirs[round(degrees / 22.5) % 16]

class Weather(Service):

    @Signal
    def ready(self): ...

    @Property(float, "readable", default_value=0.0)
    def temperature(self) -> float:
        return self._property_helper_temperature

    @Property(float, "readable", default_value=0.0)
    def feels_like(self) -> float:
        return self._property_helper_feels_like

    @Property(int, "readable", default_value=0)
    def humidity(self) -> int:
        return self._property_helper_humidity

    @Property(int, "readable", default_value=0)
    def pressure(self) -> int:
        return self._property_helper_pressure

    @Property(float, "readable", default_value=0.0)
    def wind_speed(self) -> float:
        return self._property_helper_wind_speed

    @Property(str, "readable", default_value="")
    def wind_direction(self) -> str:
        return self._property_helper_wind_direction

    @Property(float, "readable", default_value=0.0)
    def precipitation(self) -> float:
        return self._property_helper_precipitation

    @Property(int, "readable", default_value=0)
    def weather_code(self) -> int:
        return self._property_helper_weather_code

    @Property(str, "readable", default_value="🌡️")
    def weather_emoji(self) -> str:
        return self._property_helper_weather_emoji

    @Property(str, "readable", default_value="cloud-sun")
    def weather_icon(self) -> str:
        return self._property_helper_weather_icon

    @Property(str, "readable", default_value="Unknown")
    def weather_description(self) -> str:
        return self._property_helper_weather_description

    @Property(str, "readable", default_value="Loading...")
    def location(self) -> str:
        return self._property_helper_location

    @Property(bool, "readable", default_value=True)
    def is_loading(self) -> bool:
        return self._property_helper_is_loading

    @Property(bool, "readable", default_value=False)
    def has_error(self) -> bool:
        return self._property_helper_has_error

    @Property(str, "readable", default_value="")
    def error_message(self) -> str:
        return self._property_helper_error_message

    @Property(object, "readable", default_value=None)
    def hourly_forecast(self) -> list:
        return self._property_helper_hourly_forecast

    @Property(object, "readable", default_value=None)
    def daily_forecast(self) -> list:
        return self._property_helper_daily_forecast

    def __init__(self, **kwargs):

        self._property_helper_temperature = 0.0
        self._property_helper_feels_like = 0.0
        self._property_helper_humidity = 0
        self._property_helper_pressure = 0
        self._property_helper_wind_speed = 0.0
        self._property_helper_wind_direction = ""
        self._property_helper_precipitation = 0.0
        self._property_helper_weather_code = 0
        self._property_helper_weather_emoji = "🌡️"
        self._property_helper_weather_icon = "cloud-sun"
        self._property_helper_weather_description = "Unknown"
        self._property_helper_location = "Loading..."
        self._property_helper_is_loading = True
        self._property_helper_has_error = False
        self._property_helper_error_message = ""
        self._property_helper_hourly_forecast = []
        self._property_helper_daily_forecast = []

        self._weather_cache = Cache(TEMP_DIR / "weather_cache.json", STALE_CACHE_MAX)
        self._location_cache = Cache(TEMP_DIR / "location_cache.json", 24 * 3600)

        super().__init__(**kwargs)

        cached_weather = self._weather_cache.get(allow_stale=True)
        cached_location = self._location_cache.get(allow_stale=True)
        if cached_weather and cached_location:
            self._update_properties(cached_weather, cached_location)

        self._start_fetch_thread()

        GLib.timeout_add_seconds(UPDATE_INTERVAL, self._on_periodic_update)

        self.emit("ready")

    def _start_fetch_thread(self) -> None:
        thread = threading.Thread(target=self._fetch_weather_data, daemon=True)
        thread.start()

    def _fetch_weather_data(self) -> None:
        try:
            GLib.idle_add(self._set_loading, True)

            location_data = self._location_cache.get()
            if not location_data:
                raw = fetch_api(IP_LOCATION_API, 10)
                if not raw or raw.get("status") != "success":
                    GLib.idle_add(self._set_error, "Location unavailable")
                    return
                location_data = {
                    "lat": raw["lat"],
                    "lon": raw["lon"],
                    "city": raw.get("city", "Unknown"),
                    "country": raw.get("country", ""),
                }
                self._location_cache.set(location_data)

            weather_data = self._weather_cache.get()
            if not weather_data:
                lat, lon = location_data["lat"], location_data["lon"]
                params = "&".join([
                    f"latitude={lat}",
                    f"longitude={lon}",
                    "current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,surface_pressure,wind_speed_10m,wind_direction_10m",
                    "hourly=temperature_2m,weather_code,precipitation_probability",
                    "daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "timezone=auto",
                    "forecast_days=7",
                ])
                weather_data = fetch_api(f"{WEATHER_API_BASE}?{params}", 15)
                if not weather_data:
                    weather_data = self._weather_cache.get(allow_stale=True)
                    if not weather_data:
                        GLib.idle_add(self._set_error, "Weather unavailable")
                        return
                else:
                    self._weather_cache.set(weather_data)

            GLib.idle_add(self._update_properties, weather_data, location_data)

        except Exception as e:
            logger.error(f"[WeatherService] Fetch error: {e}")
            GLib.idle_add(self._set_error, str(e))

    def _update_properties(self, weather_data: dict, location_data: dict) -> None:
        try:
            current = weather_data["current"]

            self._property_helper_temperature = current["temperature_2m"]
            self._property_helper_feels_like = current.get("apparent_temperature", current["temperature_2m"])
            self._property_helper_humidity = round(current["relative_humidity_2m"])
            self._property_helper_pressure = round(current.get("surface_pressure", 1013))
            self._property_helper_wind_speed = current.get("wind_speed_10m", 0)
            self._property_helper_wind_direction = get_wind_direction(current.get("wind_direction_10m", 0))
            self._property_helper_precipitation = current.get("precipitation", 0)
            self._property_helper_weather_code = current["weather_code"]

            emoji, icon, description = get_weather_info(self._property_helper_weather_code)
            self._property_helper_weather_emoji = emoji
            self._property_helper_weather_icon = icon
            self._property_helper_weather_description = description

            city = location_data.get("city", "Unknown")
            country = location_data.get("country", "")
            self._property_helper_location = f"{city}, {country}" if country else city

            self._property_helper_hourly_forecast = self._process_hourly_forecast(weather_data.get("hourly", {}))
            self._property_helper_daily_forecast = self._process_daily_forecast(weather_data.get("daily", {}))

            self._property_helper_has_error = False
            self._property_helper_error_message = ""
            self._property_helper_is_loading = False

            for prop in [
                "temperature", "feels-like", "humidity", "pressure",
                "wind-speed", "wind-direction", "precipitation", "weather-code",
                "weather-emoji", "weather-icon", "weather-description",
                "location", "is-loading", "has-error", "error-message",
                "hourly-forecast", "daily-forecast",
            ]:
                self.notify(prop)

        except Exception as e:
            logger.error(f"[WeatherService] Update error: {e}")
            self._set_error(str(e))

    def _process_hourly_forecast(self, hourly: dict) -> list:
        if not hourly or not hourly.get("time"):
            return []
        forecast = []
        current_hour = datetime.datetime.now().hour
        for i in range(current_hour, min(current_hour + 24, len(hourly["time"]))):
            try:
                forecast.append({
                    "time": hourly["time"][i],
                    "temperature": hourly["temperature_2m"][i],
                    "weather_code": hourly["weather_code"][i],
                    "precipitation_probability": hourly.get(
                        "precipitation_probability", [0] * len(hourly["time"])
                    )[i],
                })
            except (IndexError, KeyError):
                continue
        return forecast

    def _process_daily_forecast(self, daily: dict) -> list:
        if not daily or not daily.get("time"):
            return []
        forecast = []
        for i in range(min(7, len(daily["time"]))):
            try:
                forecast.append({
                    "date": daily["time"][i],
                    "temperature_max": daily["temperature_2m_max"][i],
                    "temperature_min": daily["temperature_2m_min"][i],
                    "weather_code": daily["weather_code"][i],
                    "precipitation": daily.get(
                        "precipitation_sum", [0] * len(daily["time"])
                    )[i],
                })
            except (IndexError, KeyError):
                continue
        return forecast

    def _set_loading(self, value: bool) -> None:
        self._property_helper_is_loading = value
        self.notify("is-loading")

    def _set_error(self, message: str) -> None:
        self._property_helper_has_error = True
        self._property_helper_error_message = message
        self._property_helper_is_loading = False
        self.notify("has-error")
        self.notify("error-message")
        self.notify("is-loading")

    def _on_periodic_update(self) -> bool:
        self._start_fetch_thread()
        return True

    def refresh(self) -> None:
        self._start_fetch_thread()

    def get_weather_info_for_code(self, code: int) -> Tuple[str, str, str]:
        return get_weather_info(code)