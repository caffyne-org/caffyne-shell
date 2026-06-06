from fabric.widgets.wayland import WaylandWindow
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.eventbox import EventBox
from fabric.widgets.button import Button
from icons import VolumeIcon
from snippets import Icon, AnimatedScale, DashReveal, enable_blur, disable_blur, free_blur, trace_widget_regions
from services.singletons import audio, brightness, wm, timer, battery
from gi.repository import GLib, Gdk
from user_options import user_options
from utils.monitors import get_connector_from_monitor_id
REVEAL_DURATION = 300
import math
from snippets.blur.region_trace import trace_widget_regions
from snippets.blur.blur import set_blur_regions
from snippets.dashreveal import _ease_out_expo
from utils.update_checker import check_for_updates, do_pull, restart_shell
from utils.sounds import play_sound

# POWER_PROFILE_ICONS = {
#     "power-saver": "leaf-duotone",
#     "balanced": "scales-duotone",
#     "performance": "speedometer-duotone",
# }

# POWER_PROFILE_LABELS = {
#     "power-saver": "Power Saver",
#     "balanced": "Balanced",
#     "performance": "Performance",
# }

import bar


class OSDUpdate(Box):
    def __init__(self, on_dismiss=None, **kwargs):
        self._commits_behind = 0
        self._on_dismiss_cb = on_dismiss
        self._icon = Icon(icon_name="shooting-star-duotone", icon_size=32)
 
        self._title = Label(
            label="Update Available",
            v_expand=True,
            v_align="center",
            style_classes=["osd-updater-title"],
        )
        self._subtitle = Label(
            label="",
            v_expand=True,
            v_align="center",
            style="padding-left: 8px; font-size: 11px; opacity: 0.6;",
        )

        self._btn_primary = Button(
            h_expand=True,
            child=Label(label="Update"),
            on_clicked=lambda *_: self._on_primary(),
            style_classes=["osd-updater-button"],
        )
        self._btn_secondary = Button(
            h_expand=True,
            child=Label(label="Later"),
            on_clicked=lambda *_: self._on_secondary(),
            style_classes=["osd-updater-button"],
        )
 
        self._actions = Box(
            orientation="h",
            homogeneous=True,
            spacing=8,
            children=[self._btn_primary, self._btn_secondary],
        )
 
        super().__init__(
            orientation="v",
            spacing=12,
            h_expand=True,
            h_align="fill",
            v_align="center",
            style_classes=["osd-row"],
            children=[
                Box(
                    orientation="h",
                    spacing=0,
                    v_expand=True,
                    v_align="center",
                    h_expand=True,
                    children=[self._icon, self._title, self._subtitle],
                ),
                self._actions,
            ],
            **kwargs,
        )

    def set_update_available(self, commits_behind: int):
        self._commits_behind = commits_behind
        self._set_state_available()
 
    def _set_state_available(self):
        n = self._commits_behind
        self._icon.set_property("icon-name", "shooting-star-duotone")
        self._title.set_label("Update Available")
        self._subtitle.set_label(f"· {n} new commit{'s' if n != 1 else ''}")
        self._set_buttons("Update", "Later")
        self._actions.set_visible(True)
 
    def _set_state_updating(self):
        self._icon.set_property("icon-name", "arrows-clockwise-duotone")
        self._title.set_label("Updating…")
        self._subtitle.set_label("Pulling from origin")
        self._actions.set_visible(False)
 
    def _set_state_restart(self):
        self._icon.set_property("icon-name", "check-circle-duotone")
        self._title.set_label("Shell Updated!")
        self._subtitle.set_label("Restart to apply changes")
        self._set_buttons("Restart", "Later")
        self._actions.set_visible(True)
 
    def _set_state_failed(self, error: str):
        self._icon.set_property("icon-name", "warning-circle-duotone")
        self._title.set_label("Update Failed")
        self._subtitle.set_label(error[:60] + "…" if len(error) > 60 else error)
        self._set_buttons("Retry", "Dismiss")
        self._actions.set_visible(True)
    def _set_buttons(self, primary: str, secondary: str):
        self._btn_primary.get_child().set_label(primary)
        self._btn_secondary.get_child().set_label(secondary)
 
    def _on_primary(self):
        title = self._title.get_label()
        if title == "Update Available":
            self._set_state_updating()
            do_pull(
                on_success=self._set_state_restart,
                on_failure=self._set_state_failed,
            )
        elif title == "Shell Updated!":
            restart_shell()
        elif title == "Update Failed":
            self._set_state_updating()
            do_pull(
                on_success=self._set_state_restart,
                on_failure=self._set_state_failed,
            )
 
    def _on_secondary(self):
        if self._on_dismiss_cb:
            self._on_dismiss_cb()


class OSDIcon(Box):
    def __init__(self, icon_name: str, label_text: str = "", **kwargs):
        self._icon = Icon(icon_name=icon_name, icon_size=32)
        self._label = Label(h_expand=True, h_align="center", label=label_text)
        super().__init__(
            orientation="v",
            spacing=8,
            h_align="center",
            h_expand=True,
            v_align="center",
            v_expand=True,
            style_classes=["osd-icon"],
            children=[self._icon, self._label],
            **kwargs,
        )

    def set_icon(self, icon_name: str):
        self._icon.set_property("icon-name", icon_name)

    def set_label(self, text: str):
        self._label.set_label(text)

class OSDBar(Box):
    def __init__(self, label_text: str, icon_name: str, on_button_click=None, **kwargs):
        self.label = Label(h_expand=True, h_align="start", label=label_text, style_classes=["osd-label"])
        self.icon = Icon(icon_name=icon_name, icon_size=20)
        self.scale = AnimatedScale(
            style_classes=["scale"],
            min_value=1,
            max_value=100,
            value=0,
            h_expand=True,
            h_align="fill",
            sensitive=True,
        )
        self.button = Button(
            child=Icon(icon_name=icon_name, icon_size=16),
            on_clicked=on_button_click,
            style_classes=["applet-misc-button"],
        )

        super().__init__(
            orientation="v",
            spacing=4,
            style_classes=["osd-row"],
            h_expand=True,
            h_align="fill",
            v_expand=True,
            v_align="center",
            children=[
                self.label,
                Box(spacing=12, children=[self.button, self.scale])
            ],
            **kwargs,
        )
    def set_value(self, value: float, max_value: float = 100):
        self.scale.animate_value((value / max_value) * 100 if max_value else 0)

    def set_icon(self, icon_name: str):
        self.icon.set_property("icon-name", icon_name)

class OSD(WaylandWindow):
    def __init__(self, monitor, **kwargs):
        self._hide_timer = None
        self._hovered = False
        self._bound_speaker = None
        self._speaker_volume_handler = None
        self._speaker_muted_handler = None
        self._blur_ctx = None
        self._saved_brightness = 0
        self._battery_state = None
        self._monitor_connector = get_connector_from_monitor_id(monitor)
        self._volume_scale = AnimatedScale(
            style_classes=["scale"],
            min_value=0,
            max_value=100,
            value=0,
            h_expand=True,
            h_align="fill",
            sensitive=True,
        )
        self.volume_bar = Box(
            orientation="v",
            spacing=4,
            style_classes=["osd-row"],
            h_expand=True,
            h_align="fill",
            v_expand=True,
            v_align="center",
            children=[
                Label(h_expand=True, h_align="start", label="Volume", style_classes=["osd-label"]),
                Box(
                    spacing=12,
                    children=[
                        Button(
                        child=VolumeIcon(size=16),
                        on_clicked=lambda *_: audio.speaker.set_muted(not audio.speaker.muted) if audio.speaker else None,
                        style_classes=["applet-misc-button"],
                        ),
                        self._volume_scale
                    ]
                )
            ]
        )
        self.brightness_bar = OSDBar(
            label_text="Brightness",
            icon_name="seal-duotone",
            on_button_click=lambda *_: self._handle_brightness_click(),
        )

        self.layout_icon = OSDIcon(icon_name="keyboard-duotone", label_text="")
        # self.power_icon = OSDIcon(icon_name="leaf-duotone", label_text="")
        self.alarm_icon = OSDIcon(icon_name="alarm-duotone", label_text="Alarm!")
        self.update_widget = OSDUpdate(on_dismiss=self._start_hide)

        self.battery_icon = OSDIcon(icon_name="battery-charging-duotone", label_text="Charging")
        self.battery_low_icon = OSDIcon(icon_name="battery-low-duotone", label_text="Low Battery")
        self.battery_critical_icon = OSDIcon(icon_name="battery-warning-duotone", label_text="Critical!")

        self.revealer = DashReveal(
            reveal_child=False,
            style_classes=["osd-revealer"],
            child=Box(
                style_classes=["osd"],
                h_expand=True,
                h_align="fill",
                children=[
                self.volume_bar,
                self.brightness_bar,
                self.layout_icon,
                # self.power_icon,
                self.alarm_icon,
                self.update_widget,
                self.battery_icon,
                self.battery_low_icon,
                self.battery_critical_icon
            ]),
        )

        self.stack_box = EventBox(
            h_expand=True,
            h_align="fill",
            child=self.revealer,
        )

        super().__init__(
            layer="overlay",
            anchor="bottom",
            margin="0 0 48px 0",
            title="caffyne-shell-osd",
            monitor=monitor,
            child=self.stack_box,
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.stack_box.connect("enter-notify-event", self._on_hover_enter)
        self.stack_box.connect("leave-notify-event", self._on_hover_leave)

        self._volume_scale.connect("value-changed", self._on_volume_slider_changed)
        self._volume_scale.connect("scroll-event", self._on_volume_scroll)

        self.brightness_bar.scale.connect("value-changed", self._on_brightness_slider_changed)
        self.brightness_bar.scale.connect("scroll-event", self._on_brightness_scroll)

        if audio.speaker:
            self._bind_speaker(audio.speaker)
        audio.connect("speaker-changed", self._on_speaker_changed)
        brightness.connect("screen", self._on_brightness_changed)
        wm.keyboard_layouts.connect("notify::current-name", self._on_layout)
        timer.connect("alarm-triggered-signal", self._on_alarm_triggered)
        if battery.available:
            battery.connect("changed", self._on_battery_changed)
            self._last_charging = battery.charging
        # power_profiles.connect("changed", lambda *_: self._on_power_profile_changed())
        self._check_for_updates()

    def _on_hover_enter(self, _, event):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        self._hovered = True
        if self._hide_timer:
            GLib.source_remove(self._hide_timer)
            self._hide_timer = None

    def _on_hover_leave(self, _, event):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return
        self._hovered = False
        self._reset_timer()

    def _bind_speaker(self, speaker):
        if self._bound_speaker:
            try:
                if self._speaker_volume_handler:
                    self._bound_speaker.disconnect(self._speaker_volume_handler)
                if self._speaker_muted_handler:
                    self._bound_speaker.disconnect(self._speaker_muted_handler)
            except Exception:
                pass
        self._volume_scale.set_value(speaker.volume)
        self._bound_speaker = speaker
        self._speaker_volume_handler = speaker.connect("notify::volume", self._on_volume)
        self._speaker_muted_handler = speaker.connect("notify::muted", self._on_volume)

    def _on_speaker_changed(self, *_):
        if audio.speaker and audio.speaker is not self._bound_speaker:
            self._bind_speaker(audio.speaker)

    def _on_volume(self, obj, _):
        if not self._volume_scale._dragging:
            self._volume_scale.animate_value(obj.volume)
        if bar.is_applet_open("Volume"):
            return
        self._show_only(self.volume_bar)

    def _on_brightness_changed(self, _, percent: int):
        if not self.brightness_bar.scale._dragging:
            self.brightness_bar.set_value(percent)
        self._show_only(self.brightness_bar)

    def _on_volume_slider_changed(self, scale):
        if self._volume_scale._dragging and audio.speaker:
            audio.speaker.set_volume(scale.get_value())

    def _on_brightness_slider_changed(self, scale):
        if self.brightness_bar.scale._dragging:
            setattr(brightness, "screen_brightness", (scale.get_value() / 100) * brightness.max_screen)

    def _on_alarm_triggered(self, *_):
        self._show_only(self.alarm_icon)
        play_sound("alarm")
        
    def _handle_brightness_click(self):
        min_brightness = brightness.max_screen * 0.02
        if brightness.screen_brightness == min_brightness:
            brightness.screen_brightness = self._saved_brightness
        else:
            self._saved_brightness = brightness.screen_brightness
            brightness.screen_brightness = min_brightness
            
    def _on_layout(self, obj, _):
        self.layout_icon.set_label(obj.current_name)
        self._show_only(self.layout_icon)

    def _reset_timer(self):
        if self._hide_timer:
            GLib.source_remove(self._hide_timer)
        self._hide_timer = GLib.timeout_add(1500, self._hide)

    def _show_only(self, widget):
        if bar.is_applet_open("Settings"):
            return
        if self._monitor_connector == wm.active_output:
            for child in [self.volume_bar, self.brightness_bar, self.layout_icon, self.alarm_icon, self.update_widget, self.battery_icon, self.battery_low_icon, self.battery_critical_icon]:
                child.set_visible(child is widget)

            if not self.is_visible():
                self.set_visible(True)
                self.revealer.open()
                if user_options.theme.blur:
                    GLib.timeout_add(10, self._apply_blur)

            self._reset_timer()

    def _reset_timer(self):
        if self._hide_timer:
            GLib.source_remove(self._hide_timer)
        self._hide_timer = GLib.timeout_add(3000, self._start_hide)

    def _check_for_updates(self):
        if self._monitor_connector == wm.active_output:
            check_for_updates(self._on_update_available)
        return False
 
    def _on_update_available(self, commits_behind: int):
        self.update_widget.set_update_available(commits_behind)
        self._show_only(self.update_widget)

    def _on_battery_changed(self, _):
        percent = battery.percent
        charging = not battery.discharging

        if charging and not self._last_charging:
            new_state = "charging"
        elif not charging and percent <= 5:
            new_state = "critical"
        elif not charging and percent <= 20:
            new_state = "low"
        else:
            new_state = "normal"

        if new_state != self._battery_state:
            self._battery_state = new_state
            if new_state == "charging":
                self.battery_icon.set_label("Charging")
                self._show_only(self.battery_icon)
                play_sound("battery-charge")
            elif new_state == "critical":
                self.battery_critical_icon.set_label(f"{percent}% — Critically Low!")
                self._show_only(self.battery_critical_icon)
                play_sound("battery-warning")
            elif new_state == "low":
                self.battery_low_icon.set_label(f"{percent}% — Low Battery")
                self._show_only(self.battery_low_icon)
                play_sound("battery-low")

        self._last_charging = charging

    def _apply_blur(self):
        if self._blur_ctx:
            disable_blur(self._blur_ctx)
            free_blur(self._blur_ctx)
            self._blur_ctx = None
        
        self._blur_ctx = enable_blur(self)
        
        target_widget = self.revealer.children[0] 
        
        traced = trace_widget_regions(target_widget, accuracy=1, erode=2)

        def on_progress(value):
            if not self._blur_ctx:
                return
            
            coords = target_widget.translate_coordinates(self, 0, 0)
            if not coords:
                return
            cx, cy = coords
            
            alloc = target_widget.get_allocation()
            
            scale = DashReveal.SCALE_START + (1.0 - DashReveal.SCALE_START) * _ease_out_expo(value)
            
            anchor_x = cx + alloc.width / 2.0
            anchor_y = cy + alloc.height / 2.0

            clipped = []
            for r in traced:

                x1 = anchor_x + (cx + r.x - anchor_x) * scale
                y1 = anchor_y + (cy + r.y - anchor_y) * scale
                x2 = anchor_x + (cx + r.x + r.width - anchor_x) * scale
                y2 = anchor_y + (cy + r.y + r.height - anchor_y) * scale

                clipped.append((
                    math.floor(x1),
                    math.floor(y1),
                    max(1, math.ceil(x2 - x1)),
                    max(1, math.ceil(y2 - y1))
                ))

            set_blur_regions(self._blur_ctx, clipped)

        self.revealer.progress_cb = on_progress
        return False

    def _start_hide(self):
        self.revealer.progress_cb = None
        self.revealer.close(on_done=self._hide)
        if self._blur_ctx:
            disable_blur(self._blur_ctx)
            free_blur(self._blur_ctx)
            self._blur_ctx = None
        self._hide_timer = None
        return False

    def _hide(self):
        self.set_visible(False)
        return False
    
    def _on_volume_scroll(self, _, event):
        step = 1.0
        match event.direction:
            case Gdk.ScrollDirection.UP:
                new_val = min(self.volume_scale.value + step, 100)
            case Gdk.ScrollDirection.DOWN:
                new_val = max(self.volume_scale.value - step, 0)
            case Gdk.ScrollDirection.SMOOTH:
                _, dx, dy = event.get_scroll_deltas()
                new_val = max(0, min(self.volume_scale.value - (dy * step), 100))
            case _:
                return True
        self.volume_scale.set_value(new_val)
        if audio.speaker:
            audio.speaker.set_volume(new_val)
        return True

    def _on_brightness_scroll(self, _, event):
        step = (self.brightness_bar.scale.max_value - self.brightness_bar.scale.min_value) * 0.01
        match event.direction:
            case Gdk.ScrollDirection.UP:
                new_val = min(self.brightness_bar.scale.value + step, 100)
            case Gdk.ScrollDirection.DOWN:
                new_val = max(self.brightness_bar.scale.value - step, 0)
            case Gdk.ScrollDirection.SMOOTH:
                _, dx, dy = event.get_scroll_deltas()
                new_val = max(0, min(self.brightness_bar.scale.value - (dy * step), 100))
            case _:
                return True
        self.brightness_bar.set_value(new_val)
        brightness.screen_brightness = (new_val / 100) * brightness.max_screen
        return True
    
    # def _on_power_profile_changed(self):
    #     profile = power_profiles.active_profile
    #     self.power_icon.set_icon(POWER_PROFILE_ICONS.get(profile, "leaf-duotone"))
    #     self.power_icon.set_label(POWER_PROFILE_LABELS.get(profile, profile))
    #     self._show_only(self.power_icon)
