import os
import gi
import pam
import fabric
import cairo
import datetime
import getpass

gi.require_version("GtkSessionLock", "0.1")
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gtk, Gdk, GtkSessionLock, GLib, GdkPixbuf, GtkLayerShell
from fabric.widgets.window import Window
from fabric.widgets.wayland import WaylandWindow
from fabric.widgets.entry import Entry
from fabric.widgets.box import Box
from fabric.widgets.overlay import Overlay
from fabric.widgets.circularscale import CircularProgressBar
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.widgets.image import Image
from fabric import Application
from fabric.utils import get_relative_path
from snippets import Icon, Animator, DashReveal

WALLPAPER_PATH  = os.path.expanduser("~/.cache/caffyne-shell/wallpaper_blurred")
IDLE_TIMEOUT_MS = 5_000

DUR_WAKE  = 0.42
DUR_SLEEP = 0.30

DUR_REVEAL  = 0.30
DUR_CONCEAL = 0.30


class CoverWindow(WaylandWindow):
    def __init__(self, monitor: Gdk.Monitor, monitor_id):
        self._monitor = monitor
        geo = monitor.get_geometry()
        self._w = geo.width
        self._h = geo.height

        self._wallpaper = self._load_wallpaper()

        self._reveal = DashReveal(
            child=Image(pixbuf=self._wallpaper, h_align="fill", v_align="fill", h_expand=True, v_expand=True),
            h_expand="fill",
            v_align="fill",
            open_bezier=(0.22, 0.6, 0.36, 1.0),
            close_bezier=(0.4, 0.0, 0.2, 1.0),
            open_duration=DUR_REVEAL,
            close_duration=DUR_CONCEAL,
        )

        super().__init__(
            layer="overlay",
            anchor="top left right bottom",
            monitor=monitor_id,
            visible=True,
            all_visible=True,
            child=self._reveal,
        )
        GtkLayerShell.set_exclusive_zone(self, -1)
    def _load_wallpaper(self):
        try:
            if os.path.exists(WALLPAPER_PATH):
                return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    WALLPAPER_PATH, self._w, self._h, False
                )
        except Exception as e:
            print(f"[CoverWindow] wallpaper load error: {e}")
        return None

    def play_unlock(self, on_done=None):
        # self.show_all()
        self._reveal.close(on_done=lambda: self._finish(on_done))

    def _finish(self, on_done):
        self.hide()
        if on_done:
            on_done()

class LockScreen(Window):
    def __init__(self, lock: GtkSessionLock.Lock, monitor: Gdk.Monitor, cover: CoverWindow, manager: "LockManager"):
        self._manager = manager
        self.lock      = lock
        self._cover    = cover
        self._awake    = False
        self._idle_src = None

        self._entry_field = Entry(
            password=True,
            on_activate=self._on_activate,
        )
        self._entry_box = Box(
            spacing=6,
            style_classes=["lockscreen-entry-box"],
            children=[Icon(icon_name="key-duotone", icon_size=16), self._entry_field],
        )
        self._entry_row = Box(
            spacing=6,
            children=[
                self._entry_box,
                Button(
                    style_classes=["lockscreen-submit-button"],
                    child=Icon(icon_name="caret-double-right-duotone", icon_size=16),
                    on_pressed=lambda _: self._on_activate(self._entry_field),
                ),
            ],
        )
        self._entry_group = Box(
            orientation="v",
            spacing=18,
            h_align="center",
            children=[
                Icon(icon_size=48, icon_name="lock-duotone"),
                Label(label="Locked", style="font-size: 20px; font-weight: bold;"),
                Label(label="Please enter your password.", style="opacity: 0.8; font-size: 14px;"),
                self._entry_row,
            ],
        )
        self._entry_group.set_opacity(0.0)

        self.clock_progress = CircularProgressBar(
            style_classes=["progress-bar"],
            start_angle=270,
            end_angle=630,
            size=(138, 138),
            line_width=6,
            min_value=0,
            max_value=60,
            value=0,
        )
        self.clock_label = Label(style="font-size: 32px;")
        self.clock_label.set_xalign(0.5)
        self.clock_label.set_justify(Gtk.Justification.CENTER)
        self.clock_circle = Overlay(
            child=Box(
                style_classes=["lockscreen-clock"],
                h_expand=False,
                h_align="center",
                children=self.clock_progress,
            ),
            overlays=self.clock_label,
        )

        self.clock_revealer = Revealer(
            transition_type="crossfade",
            transition_duration=400,
            reveal_child=False,
            child=self.clock_circle,
        )

        self._layout = CenterBox(
            orientation="v",
            h_expand=True,
            v_expand=True,
            style="margin: 160px 0px;",
            center_children=[self.clock_revealer],
        )
        geo = monitor.get_geometry()
        self._wallpaper = GdkPixbuf.Pixbuf.new_from_file_at_scale(WALLPAPER_PATH, geo.width, geo.height, False)

        super().__init__(
            visible=False,
            anchor="top left right bottom",
            all_visible=False,
            child=Overlay(
                child=Image(pixbuf=self._wallpaper, h_align="fill", v_align="fill", h_expand=True, v_expand=True),
                overlays=self._layout,
            ),
        )
        # self._bg_box.set_style(f"background-image: url('{WALLPAPER_PATH}');")
        self.set_decorated(False)

        self._wake_anim = (
            Animator(
                bezier_curve=(0.22, 0.6, 0.36, 1.0),
                duration=DUR_WAKE,
                min_value=0.0,
                max_value=1.0,
                tick_widget=self._entry_group,
            ).build().unwrap()
        )
        self._wake_anim.connect("notify::value", self._on_wake_tick)

        self._sleep_anim = (
            Animator(
                bezier_curve=(0.4, 0.0, 0.6, 1.0),
                duration=DUR_SLEEP,
                min_value=0.0,
                max_value=1.0,
                tick_widget=self._entry_group,
            ).build().unwrap()
        )
        self._sleep_anim.connect("notify::value",  self._on_sleep_tick)
        self._sleep_anim.connect("finished",       self._on_sleep_done)

        self.add_events(
            Gdk.EventMask.KEY_PRESS_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.BUTTON_PRESS_MASK,
        )
        self.connect("key-press-event",     self._on_key)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("button-press-event",  self._on_motion)
        GLib.timeout_add(300, self.reveal_clock)
        GLib.timeout_add(1000, self._update_time)
        self._update_time()

    def reveal_clock(self):
        self.clock_revealer.set_reveal_child(True)
        return False

    def hide_clock(self, on_done=None):
        self.clock_revealer.set_reveal_child(False)
        if on_done:
            duration_ms = self.clock_revealer.get_transition_duration()
            GLib.timeout_add(duration_ms + 16, lambda: (on_done(), False)[1])

    def _update_time(self):
        now = datetime.datetime.now()
        self.clock_label.set_label(now.strftime("%H\n%M"))
        self.clock_progress.value = int(now.strftime("%S"))
        return True

    def _on_key(self, widget, event):
        if not self._awake:
            self._do_wake()
        if not self._entry_field.is_focused():
            self._entry_field.grab_focus()
            self._entry_field.set_position(-1)
        self._reset_idle_timer()

    def _on_motion(self, *_):
        if not self._awake:
            self._do_wake()
        self._reset_idle_timer()

    def _do_wake(self):
        self._awake = True
        self._sleep_anim.pause()
        self._layout.set_start_children([self.clock_revealer])
        self._layout.set_center_children([self._entry_group])
        self._entry_group.set_opacity(0.0)
        self._entry_group.show_all()
        self._wake_anim.play()

    def _do_sleep(self):
        self._awake = False
        self._sleep_anim.play()

    def _on_wake_tick(self, anim, _):
        p = anim.value
        self._entry_group.set_opacity(p)
        self._entry_group.set_style(f"margin-top: {int((1.0 - p) * 20)}px;")

    def _on_sleep_tick(self, anim, _):
        self._entry_group.set_opacity(1.0 - anim.value)

    def _on_sleep_done(self, *_):
        self._layout.set_start_children([])
        self._layout.set_center_children([self.clock_revealer])
        self._entry_group.set_opacity(0.0)
        self._entry_group.set_style("")

    def _reset_idle_timer(self):
        if self._idle_src is not None:
            GLib.source_remove(self._idle_src)
        self._idle_src = GLib.timeout_add(IDLE_TIMEOUT_MS, self._on_idle)

    def _on_idle(self):
        self._idle_src = None
        if self._awake:
            self._do_sleep()
        return False

    def _on_activate(self, entry, *args):
        text = (entry.get_text() or "").strip()
        if not pam.authenticate(getpass.getuser(), text):
            entry.set_text("")
            self._shake_entry()
            entry.grab_focus()
            return
        self._do_sleep()
        self.hide_clock(on_done=self._do_unlock)

    def _do_unlock(self):
        self._manager.unlock()

    def _shake_entry(self):
        offsets = [10, -10, 7, -7, 4, -4, 0]
        idx = [0]

        def _step():
            if idx[0] >= len(offsets):
                self._entry_row.set_style("")
                return False
            self._entry_row.set_style(f"margin-left: {offsets[idx[0]]}px;")
            idx[0] += 1
            return True

        GLib.timeout_add(38, _step)


class LockManager:
    def __init__(self):
        self.lock = GtkSessionLock.prepare_lock()
        self._surfaces: dict[Gdk.Monitor, LockScreen] = {}
        self._covers:   dict[Gdk.Monitor, CoverWindow] = {}
        self._pending:  set[Gdk.Monitor] = set()   # monitors mid-animation
        self._locked = False                         # true once lock_lock() called

        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            self._add_monitor(display.get_monitor(i), i)

        display.connect(
            "monitor-added",
            lambda _, mon: GLib.timeout_add(
                1000,
                lambda _, mon: self._add_monitor(mon)
            )
        )
        display.connect("monitor-removed", lambda _, mon: self._remove_monitor(mon))

    # ------------------------------------------------------------------ #
    #  Monitor lifecycle                                                   #
    # ------------------------------------------------------------------ #

    def _add_monitor(self, monitor: Gdk.Monitor, monitor_id=None):
        # Deduplicate: ignore if already tracked or mid-animation
        if monitor in self._surfaces or monitor in self._pending:
            return

        if self._locked:
            # Screen already locked — skip cover animation, go straight to lock surface
            self._engage_lock(monitor, cover=None)
            return

        # Screen not yet locked — show cover window first
        if monitor_id is None:
            monitor_id = list(self._covers).index(monitor) if monitor in self._covers else 0

        self._pending.add(monitor)
        cover = CoverWindow(monitor, monitor_id)
        self._covers[monitor] = cover
        cover.show_all()
        cover._reveal.open()
        GLib.timeout_add(
            int(DUR_REVEAL * 1000 + 200),
            lambda: self._on_cover_ready(monitor, cover)
        )

    def _on_cover_ready(self, monitor: Gdk.Monitor, cover: CoverWindow) -> bool:
        # Guard: monitor may have been removed while we were waiting
        if monitor not in self._covers:
            self._pending.discard(monitor)
            return False

        self._engage_lock(monitor, cover)
        return False  # remove GLib timeout

    def _engage_lock(self, monitor: Gdk.Monitor, cover: CoverWindow | None):
        # Deduplicate: surface may have been created by a concurrent call
        if monitor in self._surfaces:
            self._pending.discard(monitor)
            return

        if not self._locked:
            self.lock.lock_lock()
            self._locked = True

        surface = LockScreen(self.lock, monitor, cover, manager=self)
        self.lock.new_surface(surface, monitor)
        surface.show_all()
        self._surfaces[monitor] = surface
        self._pending.discard(monitor)

        if cover is not None:
            cover._reveal.close(on_done=surface.reveal_clock)
        else:
            # No cover (hotplug while locked) — reveal clock immediately
            surface.reveal_clock()

    # ------------------------------------------------------------------ #
    #  Cleanup                                                             #
    # ------------------------------------------------------------------ #

    def _remove_monitor(self, monitor: Gdk.Monitor):
        self._pending.discard(monitor)

        surface = self._surfaces.pop(monitor, None)
        if surface:
            surface.destroy()

        cover = self._covers.pop(monitor, None)
        if cover:
            cover.destroy()

    def unlock(self):
        self._locked = False

        Gdk.Display.get_default().sync()
        self.lock.unlock_and_destroy()
        
        for surface in list(self._surfaces.values()):
            GtkSessionLock.unmap_lock_window(surface)

        for surface in list(self._surfaces.values()):
            surface.destroy()

        self._surfaces.clear()
        self._covers.clear()
        self._pending.clear()


        GLib.idle_add(fabric.Application.get_default().quit)


def lock():
    return LockManager()


if __name__ == "__main__":
    manager = LockManager()
    app = Application("lock")
    app.set_stylesheet_from_file(get_relative_path("./style/style.css"))
    app.run()