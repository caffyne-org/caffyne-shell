import datetime
import zoneinfo
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.stack import Stack
from snippets import Icon, Applet, AppletPage, TimeoutAdjuster, AnimatedScroll, ClippingScrolledWindow
from services.singletons import timer
from gi.repository import GLib, Gdk, Gtk

from user_options import user_options

AVAILABLE_TIMEZONES = sorted(zoneinfo.available_timezones())

from fabric.widgets.entry import Entry

class TimezoneSearchPage(AppletPage):
    def __init__(self, parent, stack, on_select: callable, slot_index: int):
        self._on_select = on_select
        self._all_zones = AVAILABLE_TIMEZONES
        
        self._entry = Entry(
            h_expand=True,
            placeholder="Type to search...",
        )

        self._entry_box = Box(
            style_classes=["launcher-search"],
            spacing=8,
            children=[
                Icon(icon_name="magnifying-glass-duotone", icon_size=16),
                self._entry,
            ],
        )
        self._entry.connect("focus-in-event", lambda *_: self._entry_box.add_style_class("focused"))
        self._entry.connect("focus-out-event", lambda *_: self._entry_box.remove_style_class("focused"))
        self._list_box = Box(
            orientation="v",
            spacing=6,
        )
        
        self._scroll = ClippingScrolledWindow(
            child=self._list_box,
            style_classes=["scrollable"],
            max_content_size=(324, 228),
            style="min-width: 324px; min-height: 228px;",
            kinetic_scroll=True,
            overlay_scroll=True
        )
        
        super().__init__(
            stack=stack,
            title=f"Select Timezone",
            child=Box(
                orientation="v",
                spacing=8,
                children=[self._entry_box, self._scroll],
            ),
        )
        
        self._entry.connect("changed", lambda e: self._filter(e.get_text()))
        self._populate(self._all_zones)
        self.connect("realize", lambda *_: parent.connect("key-press-event", self._on_key_press))
    def reset(self, slot_index: int, on_select: callable):
        """Reuse this page for a different slot — clears search and updates callback."""
        self._on_select = on_select
        self._entry.set_text("")
        self._populate(self._all_zones)
    def _on_key_press(self, _, event):

        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False
        if event.keyval in (
            Gdk.KEY_Escape, Gdk.KEY_Return, Gdk.KEY_Tab,
            Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right,
        ):
            return False

        if not self._entry.is_focus():
            self._entry.grab_focus()
            self._entry.set_position(-1)
        return False
    
    def _populate(self, zones):
        for child in self._list_box.get_children():
            child.destroy()
        for tz in zones:
            city = tz.split("/")[-1].replace("_", " ")
            region = tz.split("/")[0] if "/" in tz else ""
            btn = Button(
                style_classes=["menu-device-item"],
                on_clicked=lambda _, t=tz: self._on_select(t),
                child=Box(
                    spacing=8,
                    children=[
                        Label(label=city, h_align="start", h_expand=True),
                        Label(label=region, h_align="end", style_classes=["dim-label"]),
                    ],
                ),
            )
            self._list_box.add(btn)
        self._list_box.show_all()

    def _filter(self, query: str):
        q = query.lower()
        filtered = [z for z in self._all_zones if q in z.lower().replace("_", " ")]
        self._populate(filtered)

class WorldClockRow(Box):
    def __init__(self, timezone: str, on_click=None):
        self._timezone = timezone
        self._tz = zoneinfo.ZoneInfo(timezone)
        self._on_click = on_click

        city = timezone.split("/")[-1].replace("_", " ")
        self._time_label = Label(
            style_classes=["world-clock-time"],
            h_align="center",
            h_expand=True,
            v_expand=True,
            v_align="center",
        )
        self._city_label = Label(
            label=city,
            style_classes=["dim-label"],
            h_align="center",
            v_align="center",
        )

        inner = Box(
            style_classes=["world-clock-entry"],
            orientation="v",
            spacing=8,
            h_expand=True,
            children=[self._city_label, self._time_label],
        )

        super().__init__(h_expand=True)

        if on_click:
            btn = Button(
                child=inner,
                h_expand=True,
                on_clicked=lambda *_: on_click(),
                style_classes=["world-clock-button"],
            )
            self.add(btn)
        else:
            self.add(inner)

        self._update()
    def _update(self):
        now = datetime.datetime.now(self._tz)
        self._time_label.set_label(now.strftime("%H:%M"))

    def set_timezone(self, timezone: str):
        self._timezone = timezone
        self._tz = zoneinfo.ZoneInfo(timezone)
        city = timezone.split("/")[-1].replace("_", " ")
        self._city_label.set_label(city)
        self._update()

    @property
    def timezone(self):
        return self._timezone

class WorldClocksWidget(Box):
    """Two world clock rows, switches to lap list when stopwatch is running."""
    def __init__(self):
        self._clock_rows = []
        self._lap_boxes = []
        self._open_search_callbacks = [None, None]

        self._clocks_box = Box(orientation="h", spacing=12)
        self._clocks_box.set_homogeneous(True)
        self._laps_box = Box(orientation="v", spacing=6)
        self._laps_scroll = AnimatedScroll(
            style_classes=["laps-scroll"],
            child=self._laps_box,
            max_content_size=(324, 162),
            overlay_scroll=True
        )

        self._laps_placeholder = Box(
            style_classes=["menu-list-placeholder"],
            h_align="fill",
            v_align="fill",
            h_expand=True,
            v_expand=True,
            children=[
                Label(
                    v_expand=True,
                    v_align="center",
                    h_expand=True,
                    h_align="center",
                    label="No laps recorded",
                    style_classes=["menu-list-placeholder-label"],
                )
            ],
        )

        self._laps_stack = Stack(
            transition_duration=200,
            transition_type="crossfade",
            children=[self._laps_scroll, self._laps_placeholder],
        )

        self._inner_stack = Stack(transition_type="crossfade")
        self._inner_stack.add_named(self._clocks_box, "clocks")
        self._inner_stack.add_named(self._laps_stack, "laps")

        super().__init__(
            orientation="v",
            spacing=4,
            h_expand=True,
            style_classes=["world-clocks-widget"],
            children=[self._inner_stack],
        )

        self._build_clock_rows()
        GLib.timeout_add(10000, self._tick)

        from services.singletons import timer
        self._timer = timer
        timer.connect("stopwatch-started", lambda *_: self._show_laps())
        timer.connect("stopwatch-reset",   lambda *_: self._show_clocks())
        timer.connect("notify::stopwatch-laps", lambda *_: self._refresh_laps())

    def set_click_callbacks(self, callbacks: list):
        self._open_search_callbacks = callbacks
        self._build_clock_rows()

    def _build_clock_rows(self):
        for child in self._clocks_box.get_children():
            self._clocks_box.remove(child)
        self._clock_rows.clear()

        for i, tz in enumerate(user_options.world_clocks.clocks[:2]):
            row = WorldClockRow(
                tz,
                on_click=self._open_search_callbacks[i] if self._open_search_callbacks else None,
            )
            self._clock_rows.append(row)
            self._clocks_box.add(row)
        self._clocks_box.show_all()

    def _tick(self):
        for row in self._clock_rows:
            row._update()
        return True

    def _show_laps(self):
        self._inner_stack.set_visible_child_name("laps")
        self._refresh_laps()

    def _show_clocks(self):
        self._inner_stack.set_visible_child_name("clocks")
        for child in self._laps_box.get_children():
            self._laps_box.remove(child)
        self._lap_boxes.clear()
        self._update_laps_placeholder()

    def _update_laps_placeholder(self):
        if self._lap_boxes:
            self._laps_stack.set_visible_child(self._laps_scroll)
        else:
            self._laps_stack.set_visible_child(self._laps_placeholder)

    def _refresh_laps(self):
        for child in self._laps_box.get_children():
            self._laps_box.remove(child)
        self._lap_boxes.clear()

        for lap in reversed(self._timer.stopwatch_laps):
            row = Box(
                orientation="h",
                spacing=8,
                h_expand=True,
                style_classes=["menu-device-item"],
                children=[
                    Label(
                        label=f"Lap {lap.number}",
                        style_classes=["dim-label"],
                        h_align="start",
                    ),
                    Label(
                        label=f"+{self._fmt(lap.lap_time)}",
                        style_classes=["dim-label"],
                        h_align="end",
                    ),
                    Label(
                        label=self._fmt(lap.time),
                        style_classes=["lap-time"],
                        h_align="end",
                        h_expand=True,
                    ),
                ],
            )
            self._laps_box.add(row)
            self._lap_boxes.append(row)
        self._laps_box.show_all()
        self._update_laps_placeholder()

    def _fmt(self, seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{m:02d}:{s:02d}.{cs:02d}"

    def reload_timezones(self):
        self._build_clock_rows()

class StopwatchWidget(Box):
    def __init__(self):
        self.play_icon = Icon(icon_name="play-duotone")
        self.lap_reset_icon = Icon(icon_name="clock-clockwise-duotone")

        self.time_label = Label(
            label="00:00.00",
            style_classes=["clock-timer-label"],
        )

        super().__init__(
            style_classes=["clock-timer-widget"],
            spacing=6,
            children=[
                Button(
                    style_classes=["clock-timer-widget-button"],
                    child=self.lap_reset_icon,
                    on_clicked=lambda *_: (
                        timer.add_lap() if timer.stopwatch_running
                        else timer.reset_stopwatch()
                    ),
                ),
                self.time_label,
                Button(
                    style_classes=["clock-timer-widget-button"],
                    child=self.play_icon,
                    on_clicked=lambda *_: (
                        timer.pause_stopwatch() if timer.stopwatch_running
                        else timer.resume_stopwatch() if timer.stopwatch_time > 0
                        else timer.start_stopwatch()
                    ),
                ),
            ]
        )

        timer.connect("notify::stopwatch-display", self._on_display_change)
        for signal in ["stopwatch-started", "stopwatch-paused", "stopwatch-resumed", "stopwatch-reset"]:
            timer.connect(signal, lambda *_: self._update_icons())

    def _on_display_change(self, *_):
        self.time_label.set_label(timer.stopwatch_display)

    def _update_icons(self):
        if timer.stopwatch_running:
            self.play_icon.icon_name = "pause-duotone"
            self.lap_reset_icon.icon_name = "timer-duotone"
        elif timer.stopwatch_time > 0:
            self.play_icon.icon_name = "play-duotone"
            self.lap_reset_icon.icon_name = "arrows-clockwise-duotone"
        else:
            self.lap_reset_icon.icon_name = "clock-clockwise-duotone"

class TimerWidget(Box):
    def __init__(self):
        self.timeout_adjuster = TimeoutAdjuster(
            initial_minutes=15,
            label_visible=not timer.alarm_set,
        )

        self.alarm_label = Label(
            label=timer.alarm_display,
            style_classes=["clock-timer-label"],
            visible=timer.alarm_set,
        )

        self.play_stop_icon = Icon(
            icon_name="stop-duotone" if timer.alarm_set else "play-duotone",
            icon_size=16,
        )

        self.left_icon = Icon(icon_name="clock-countdown-duotone", icon_size=16)

        super().__init__(
            style_classes=["clock-timer-widget"],
            spacing=6,
            children=[
            Button(
                style_classes=["clock-timer-widget-button"],
                child=self.left_icon,
                on_clicked=lambda *_: (
                    timer.set_do_not_disturb(not timer.do_not_disturb) if timer.alarm_set
                    else None
                ),
            ),
            Overlay(
                child=self.timeout_adjuster,
                overlays=self.alarm_label,
            ),
            Button(
                style_classes=["clock-timer-widget-button"],
                child=self.play_stop_icon,
                on_clicked=lambda *_: (
                    timer.cancel_alarm() if timer.alarm_set
                    else timer.set_alarm(minutes=self.timeout_adjuster.minutes)
                ),
            ),
            ]
        )

        timer.connect("notify::alarm-display", self._on_alarm_display_change)
        timer.connect("notify::alarm-set", self._on_alarm_set_change)
        timer.connect("notify::do-not-disturb", self._on_dnd_change)

    def _on_alarm_display_change(self, *_):
        self.alarm_label.set_label(timer.alarm_display)

    def _on_alarm_set_change(self, *_):
        alarm_set = timer.alarm_set
        self.alarm_label.set_visible(alarm_set)
        self.timeout_adjuster.minutes_label.set_visible(not alarm_set)
        self.play_stop_icon.set_icon_name(
            "stop-duotone" if alarm_set else "play-duotone"
        )
        self._update_left_icon()

    def _on_dnd_change(self, *_):
        self._update_left_icon()

    def _update_left_icon(self):
        if timer.alarm_set and timer.do_not_disturb:
            self.left_icon.set_icon_name("bell-simple-slash-duotone")
        elif timer.alarm_set:
            self.left_icon.set_icon_name("bell-simple-z-duotone")
        else:
            self.left_icon.set_icon_name("clock-countdown-duotone")

class ClockApplet(Applet):
    def __init__(self, parent, **kwargs):
        self.clock_progress = CircularProgressBar(
            style_classes=["progress-bar"],
            start_angle=270,
            end_angle=630,
            size=(102, 102),
            line_width=6,
            min_value=0,
            max_value=60,
            value=0,
        )

        self.clock_label = Label(
            style="font-size: 20px;",
        )
        self.clock_label.set_xalign(0.5)
        self.clock_label.set_justify(Gtk.Justification.CENTER)
        self.clock_circle = Overlay(
            child=self.clock_progress,
            overlays=self.clock_label,
        )

        self.title_label = Label(
            label=datetime.datetime.now().strftime("%B %-d"),
            style_classes=["applet-header-label"],
        )

        self._world_clocks = WorldClocksWidget()

        self.main_box = Box(
            orientation="v",
            spacing=12,
            children=[
                Box(
                    spacing=12,
                    children=[
                        self.clock_circle,
                        Box(
                            spacing=18,
                            orientation="v",
                            v_expand=True,
                            v_align="center",
                            children=[
                                TimerWidget(),
                                StopwatchWidget(),
                            ],
                        ),
                    ]
                ),
                self._world_clocks,
            ]
        )

        super().__init__(
            main_menu=AppletPage(
                stack=self,
                label=self.title_label,
                child=self.main_box,
                first=True,
            ),
            **kwargs,
        )
        self.add_menu("tz-search", lambda stack: TimezoneSearchPage(
            parent=parent,
            stack=stack,
            slot_index=0,
            on_select=lambda tz: None,
        ))
        GLib.timeout_add(1000, self._update_time)
        self._update_time()
        def make_open_search(slot_index):
            def _open(tz_page=None):
                page = self.get_child_by_name("tz-search")
                if page and hasattr(page, "reset"):
                    page.reset(slot_index, lambda tz: self._on_tz_selected(slot_index, tz))
                self.set_visible_child_name("tz-search")
            return _open
        self._world_clocks.set_click_callbacks([make_open_search(0), make_open_search(1)])

    def _update_time(self):
        now = datetime.datetime.now()
        self.clock_label.set_label(now.strftime("%H\n%M"))
        self.clock_progress.value = int(now.strftime("%S"))
        self.title_label.set_label(now.strftime("%B %-d"))
        return True
    def _on_tz_selected(self, slot_index: int, tz: str):
        clocks = list(user_options.world_clocks.clocks[:2])
        while len(clocks) < 2:
            clocks.append("UTC")
        clocks[slot_index] = tz
        user_options.world_clocks.clocks = clocks
        user_options.save()
        self._world_clocks.reload_timezones()
        self.set_visible_child_name("main")