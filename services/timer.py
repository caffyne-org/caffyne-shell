import time
from datetime import datetime, timedelta
from threading import Thread
from dataclasses import dataclass
from typing import Callable
from gi.repository import GLib
from fabric.core.service import Service, Signal, Property
from loguru import logger

@dataclass
class Lap:
    number: int
    time: float
    lap_time: float

class TimerService(Service):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._stopwatch_running = False
        self._stopwatch_start_time = 0.0
        self._stopwatch_elapsed = 0.0
        self._stopwatch_laps: list[Lap] = []
        self._stopwatch_stop_requested = False

        self._alarm_set = False
        self._alarm_time: datetime | None = None
        self._alarm_triggered = False
        self._alarm_trigger_time: datetime | None = None
        self._alarm_callback: Callable[[], None] | None = None
        self._alarm_stop_requested = False
        self._do_not_disturb = False
        
    @Signal
    def stopwatch_started(self) -> None: ...

    @Signal
    def stopwatch_paused(self) -> None: ...

    @Signal
    def stopwatch_resumed(self) -> None: ...

    @Signal
    def stopwatch_reset(self) -> None: ...

    @Signal
    def alarm_set_signal(self) -> None: ...

    @Signal
    def alarm_triggered_signal(self) -> None: ...

    @Signal
    def alarm_cancelled(self) -> None: ...

    @Property(bool, "readable", default_value=False)
    def stopwatch_running(self) -> bool:
        return self._stopwatch_running

    @Property(float, "readable", default_value=0.0)
    def stopwatch_time(self) -> float:
        if self._stopwatch_running:
            return self._stopwatch_elapsed + (time.time() - self._stopwatch_start_time)
        return self._stopwatch_elapsed

    @Property(str, "readable", default_value="")
    def stopwatch_display(self) -> str:
        return self._format_time(self.stopwatch_time)

    @Property(object, "readable")
    def stopwatch_laps(self) -> list[Lap]:
        return self._stopwatch_laps.copy()

    @Property(bool, "readable", default_value=False)
    def alarm_set(self) -> bool:
        return self._alarm_set

    @Property(bool, "readable", default_value=False)
    def alarm_triggered(self) -> bool:
        return self._alarm_triggered

    @Property(float, "readable", default_value=0.0)
    def alarm_time_remaining(self) -> float:
        if not self._alarm_set or not self._alarm_time:
            return 0.0
        if self._alarm_triggered and self._alarm_trigger_time:
            return -(datetime.now() - self._alarm_trigger_time).total_seconds()
        return (self._alarm_time - datetime.now()).total_seconds()
    
    @Property(bool, "read-write", default_value=False)
    def do_not_disturb(self) -> bool:
        return self._do_not_disturb

    @do_not_disturb.setter
    def do_not_disturb(self, value: bool):
        self._do_not_disturb = value
        self.notify("do-not-disturb")

    @Property(str, "readable", default_value="")
    def alarm_display(self) -> str:
        remaining = self.alarm_time_remaining
        if remaining == 0:
            return "No alarm set"
        prefix = "-" if remaining < 0 else ""
        return prefix + self._format_alarm_time(abs(remaining))

    def _notify_stopwatch(self):
        self.notify("stopwatch-time")
        self.notify("stopwatch-display")
        self.notify("stopwatch-running")

    def _notify_alarm(self):
        self.notify("alarm-set")
        self.notify("alarm-triggered")
        self.notify("alarm-time-remaining")
        self.notify("alarm-display")

    def start_stopwatch(self):
        if self._stopwatch_running:
            return
        self._stopwatch_elapsed = 0.0
        self._stopwatch_start_time = time.time()
        self._stopwatch_running = True
        self._stopwatch_laps.clear()
        self._stopwatch_stop_requested = False
        Thread(target=self._update_stopwatch, daemon=True).start()
        self.emit("stopwatch-started")

    def pause_stopwatch(self):
        if not self._stopwatch_running:
            return
        self._stopwatch_elapsed += time.time() - self._stopwatch_start_time
        self._stopwatch_running = False
        self._stopwatch_stop_requested = True
        self._notify_stopwatch()
        self.emit("stopwatch-paused")

    def resume_stopwatch(self):
        if self._stopwatch_running:
            return
        if self._stopwatch_elapsed == 0:
            self.start_stopwatch()
            return
        self._stopwatch_start_time = time.time()
        self._stopwatch_running = True
        self._stopwatch_stop_requested = False
        Thread(target=self._update_stopwatch, daemon=True).start()
        self.emit("stopwatch-resumed")

    def reset_stopwatch(self):
        self._stopwatch_running = False
        self._stopwatch_stop_requested = True
        self._stopwatch_elapsed = 0.0
        self._stopwatch_start_time = 0.0
        self._stopwatch_laps = []
        self.notify("stopwatch-laps")
        self._notify_stopwatch()
        self.emit("stopwatch-reset")

    def add_lap(self) -> Lap | None:
        if not self._stopwatch_running and self._stopwatch_elapsed == 0:
            return None
        current_time = self.stopwatch_time
        lap_number = len(self._stopwatch_laps) + 1
        previous_lap_time = self._stopwatch_laps[-1].time if self._stopwatch_laps else 0.0
        lap = Lap(number=lap_number, time=current_time, lap_time=current_time - previous_lap_time)
        self._stopwatch_laps.append(lap)
        self.notify("stopwatch-laps")
        return lap

    def _update_stopwatch(self):
        while not self._stopwatch_stop_requested:
            GLib.idle_add(self.notify, "stopwatch-time")
            GLib.idle_add(self.notify, "stopwatch-display")
            time.sleep(0.01)

    def set_alarm(self, hours: int = 0, minutes: int = 0, seconds: int = 0, callback: Callable | None = None):
        if self._alarm_set:
            self.cancel_alarm()
        total_seconds = hours * 3600 + minutes * 60 + seconds
        if total_seconds <= 0:
            return
        self._alarm_time = datetime.now() + timedelta(seconds=total_seconds)
        self._alarm_set = True
        self._alarm_triggered = False
        self._alarm_trigger_time = None
        self._alarm_callback = callback
        self._alarm_stop_requested = False
        Thread(target=self._run_alarm, daemon=True).start()
        self._notify_alarm()
        self.emit("alarm-set-signal")

    def cancel_alarm(self):
        if not self._alarm_set:
            return
        self._alarm_set = False
        self._alarm_triggered = False
        self._alarm_time = None
        self._alarm_trigger_time = None
        self._alarm_callback = None
        self._alarm_stop_requested = True
        self._do_not_disturb = False
        self.notify("do-not-disturb")
        self._notify_alarm()
        self.emit("alarm-cancelled")

    def snooze_alarm(self, minutes: int = 5):
        if not self._alarm_triggered:
            return
        callback = self._alarm_callback
        self.cancel_alarm()
        self.set_alarm(minutes=minutes, callback=callback)

    def _run_alarm(self):
        while not self._alarm_stop_requested and self._alarm_set:
            GLib.idle_add(self.notify, "alarm-time-remaining")
            GLib.idle_add(self.notify, "alarm-display")
            if datetime.now() >= self._alarm_time:
                GLib.idle_add(self._trigger_alarm_main_thread)
                break
            time.sleep(1)

    def set_do_not_disturb(self, value: bool):
        self._do_not_disturb = value
        self.notify("do-not-disturb")

    def _trigger_alarm_main_thread(self):
        self._alarm_triggered = True
        self._alarm_trigger_time = datetime.now()
        self._notify_alarm()
        if self._do_not_disturb:
            self._do_not_disturb = False
            self.notify("do-not-disturb")
        else:
            self.emit("alarm-triggered-signal")
        if self._alarm_callback:
            try:
                self._alarm_callback()
            except Exception as e:
                logger.error(f"Alarm callback error: {e}")

        Thread(target=self._tick_after_trigger, daemon=True).start()
        return False
    def _tick_after_trigger(self):
        while not self._alarm_stop_requested and self._alarm_set:
            GLib.idle_add(self.notify, "alarm-time-remaining")
            GLib.idle_add(self.notify, "alarm-display")
            time.sleep(0.1)
    def _trigger_alarm(self):
        self._alarm_triggered = True
        self._alarm_trigger_time = datetime.now()
        self._notify_alarm()
        self.emit("alarm-triggered-signal")
        if self._alarm_callback:
            try:
                self._alarm_callback()
            except Exception as e:
                logger.error(f"Alarm callback error: {e}")
        while not self._alarm_stop_requested and self._alarm_set:
            self.notify("alarm-time-remaining")
            self.notify("alarm-display")
            time.sleep(0.1)

    def _format_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int((seconds % 1) * 100)
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"
        return f"{minutes:02d}:{secs:02d}.{centiseconds:02d}"

    def _format_alarm_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours:02d}h {minutes:02d}m {secs:02d}s"
        return f"{minutes:02d}m {secs:02d}s"

    def cleanup(self):
        self._stopwatch_stop_requested = True
        self._stopwatch_running = False
        self._alarm_stop_requested = True
        self._alarm_set = False
        self._alarm_callback = None
        self._notify_stopwatch()
        self._notify_alarm()