import os
import sys
import math
import subprocess
import threading
import gi
import pam
import fabric
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
from snippets import Icon, Animator

WALLPAPER_PATH  = os.path.expanduser("~/.cache/caffyne-shell/wallpaper_blurred")
IDLE_TIMEOUT_MS = 5_000

DUR_WAKE  = 0.38
DUR_SLEEP = 0.24


class CoverWindow(WaylandWindow):
    def __init__(self, monitor: Gdk.Monitor, monitor_id: int):
        self._monitor = monitor
        geo = monitor.get_geometry()
        self._w = geo.width
        self._h = geo.height

        self._wallpaper_pixbuf = self._load_wallpaper()
        self._image = Image(
            pixbuf=self._wallpaper_pixbuf,
            h_align="fill",
            v_align="fill",
            h_expand=True,
            v_expand=True
        )

        super().__init__(
            layer="overlay",
            anchor="top left right bottom",
            monitor=monitor_id,
            visible=True,
            all_visible=True,
            child=self._image,
        )
        GtkLayerShell.set_exclusive_zone(self, -1)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"window { background-color: #000000; }")
        self.get_style_context().add_provider(
            css_provider, 
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.set_opacity(0.0)
        self._anim_source = None

    def _load_wallpaper(self):
        try:
            if os.path.exists(WALLPAPER_PATH):
                return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    WALLPAPER_PATH, 
                    self._w, 
                    self._h, 
                    False
                )
        except Exception as e:
            print(f"[CoverWindow] Wallpaper load error: {e}")
        return None

    def fade_in(self, duration=0.28, on_done=None):
        self._animate_opacity(start=0.0, target=1.0, duration=duration, on_done=on_done)

    def fade_out(self, duration=0.22, on_done=None):
        self._animate_opacity(start=1.0, target=0.0, duration=duration, on_done=lambda: self._finish(on_done))

    def _animate_opacity(self, start: float, target: float, duration: float, on_done=None):
        if self._anim_source:
            GLib.source_remove(self._anim_source)

        start_time = GLib.get_monotonic_time() / 1_000_000.0

        def _step():
            now = GLib.get_monotonic_time() / 1_000_000.0
            elapsed = now - start_time
            t = min(1.0, elapsed / duration)

            ease = 1.0 - math.pow(1.0 - t, 3)
            current_opacity = start + (target - start) * ease

            self.set_opacity(current_opacity)

            if t >= 1.0:
                self._anim_source = None
                if on_done:
                    on_done()
                return False
            return True

        self._anim_source = GLib.timeout_add(16, _step)

    def _finish(self, on_done):
        if on_done:
            on_done()
        GLib.timeout_add(40, self._destroy_cover)

    def _destroy_cover(self):
        self.hide()
        return False


class LockScreen(Window):
    def __init__(self, lock: GtkSessionLock.Lock, monitor: Gdk.Monitor, manager: "LockManager"):
        self._manager = manager
        self.lock      = lock
        self._awake    = False
        self._idle_src = None
        self._authenticating = False

        self._entry_field = Entry(
            password=True,
            on_activate=self._on_activate,
        )
        self._entry_box = Box(
            spacing=6,
            style_classes=["lockscreen-entry-box"],
            children=[Icon(icon_name="key", icon_size=16), self._entry_field],
        )
        self._entry_row = Box(
            spacing=6,
            children=[
                self._entry_box,
                Button(
                    style_classes=["lockscreen-submit-button"],
                    child=Icon(icon_name="caret-double-right", icon_size=16),
                    on_pressed=lambda _: self._on_activate(self._entry_field),
                ),
            ],
        )
        self._entry_group = Box(
            orientation="v",
            spacing=18,
            h_align="center",
            children=[
                Icon(icon_size=48, icon_name="lock"),
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
        self.clock_label = Label(style_classes="lockscreen-clock-label")
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
            transition_duration=300,
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
        self.set_decorated(False)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"window { background-color: #000000; }")
        self.get_style_context().add_provider(
            css_provider, 
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._wake_anim = (
            Animator(
                bezier_curve=(0.16, 1.0, 0.3, 1.0),
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
        
        GLib.timeout_add(1000, self._update_time)
        self._update_time()

    def reveal_clock(self):
        self.clock_revealer.set_reveal_child(True)

    def hide_clock(self, on_done=None):
        self.clock_revealer.set_reveal_child(False)
        if on_done:
            duration_ms = self.clock_revealer.get_transition_duration()
            GLib.timeout_add(duration_ms + 10, lambda: (on_done(), False)[1])

    def fade_out_ui(self, on_done=None):
        self.hide_clock()
        if self._awake:
            self._do_sleep()
        
        duration_ms = self.clock_revealer.get_transition_duration()
        if on_done:
            GLib.timeout_add(duration_ms + 50, lambda: (on_done(), False)[1])

    def _update_time(self):
        now = datetime.datetime.now()
        self.clock_label.set_label(now.strftime("%H\n%M"))
        self.clock_progress.value = int(now.strftime("%S"))
        return True

    def _on_key(self, widget, event):
        if not self._awake:
            self._do_wake()
        if not self._entry_field.is_focus():
            self._entry_field.grab_focus()
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
        if not self._entry_field.is_focus():
            self._entry_field.grab_focus()
            self._entry_field.set_position(-1)
        self._wake_anim.play()

    def _do_sleep(self):
        self._awake = False
        self._sleep_anim.play()

    def _on_wake_tick(self, anim, _):
        p = anim.value
        self._entry_group.set_opacity(p)
        offset = int((1.0 - p) * 20)
        self._entry_group.set_style(f"margin-top: {offset}px;")

    def _on_sleep_tick(self, anim, _):
        p = anim.value
        self._entry_group.set_opacity(1.0 - p)
        offset = int(p * 10)
        self._entry_group.set_style(f"margin-top: {offset}px;")

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
        if self._authenticating:
            return

        text = (entry.get_text() or "").strip()
        if not text:
            return

        self._authenticating = True
        user = getpass.getuser()

        def _auth_worker():
            success = pam.authenticate(user, text)
            GLib.idle_add(self._on_auth_result, success, entry)

        threading.Thread(target=_auth_worker, daemon=True).start()

    def _on_auth_result(self, success: bool, entry: Entry):
        self._authenticating = False
        if not success:
            entry.set_text("")
            self._shake_entry()
            entry.grab_focus()
            return

        self._manager.start_unlock_sequence()

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

        GLib.timeout_add(25, _step)


class LockManager:
    def __init__(self):
        self.lock = GtkSessionLock.prepare_lock()
        self._surfaces: dict[Gdk.Monitor, LockScreen] = {}
        self._covers:   dict[Gdk.Monitor, CoverWindow] = {}
        self._pending:  set[Gdk.Monitor] = set()
        self._locked = False

        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            self._add_monitor(display.get_monitor(i), i)

        display.connect(
            "monitor-added",
            lambda _, mon: GLib.timeout_add(
                500,
                lambda: self._add_monitor(mon)
            )
        )
        display.connect("monitor-removed", lambda _, mon: self._remove_monitor(mon))

    def _add_monitor(self, monitor: Gdk.Monitor, monitor_id=None):
        if monitor in self._surfaces or monitor in self._pending:
            return

        if self._locked:
            self._engage_lock(monitor, cover=None)
            return

        display = Gdk.Display.get_default()
        if monitor_id is None:
            monitor_id = 0
            for idx in range(display.get_n_monitors()):
                if display.get_monitor(idx) == monitor:
                    monitor_id = idx
                    break

        self._pending.add(monitor)
        cover = CoverWindow(monitor, monitor_id)
        self._covers[monitor] = cover
        cover.show_all()

        cover.fade_in(duration=0.28, on_done=lambda: self._on_cover_opened(monitor, cover))

    def _on_cover_opened(self, monitor: Gdk.Monitor, cover: CoverWindow) -> bool:
        if monitor in self._covers and monitor not in self._surfaces:
            self._engage_lock(monitor, cover)
        return False

    def _engage_lock(self, monitor: Gdk.Monitor, cover: CoverWindow | None):
        if monitor in self._surfaces:
            self._pending.discard(monitor)
            return

        if not self._locked:
            self.lock.lock_lock()
            self._locked = True

        surface = LockScreen(self.lock, monitor, manager=self)
        self.lock.new_surface(surface, monitor)
        surface.show_all()
        surface.queue_draw()

        display = monitor.get_display()
        if display:
            display.flush()

        self._surfaces[monitor] = surface
        self._pending.discard(monitor)

        # Seamless transition: Reveal UI directly over the wallpaper surface,
        # then silently hide the temporary setup cover window without fading out.
        surface.reveal_clock()

        if cover is not None:
            GLib.timeout_add(100, cover.hide)

    def start_unlock_sequence(self):
        surfaces = list(self._surfaces.values())
        if not surfaces:
            self.unlock()
            return

        completed = [0]
        total = len(surfaces)

        def _on_ui_faded():
            completed[0] += 1
            if completed[0] >= total:
                self.unlock_with_cover_fade()

        for surface in surfaces:
            surface.fade_out_ui(on_done=_on_ui_faded)

    def unlock_with_cover_fade(self):
        display = Gdk.Display.get_default()
        unlock_covers = []

        # Create overlay covers over all monitors BEFORE releasing the session lock
        for i in range(display.get_n_monitors()):
            mon = display.get_monitor(i)
            c = CoverWindow(mon, i)
            c.set_opacity(1.0)
            c.show_all()
            c.queue_draw()
            unlock_covers.append(c)

        display.flush()

        # Brief delay to force compositor to present cover front-buffers
        GLib.timeout_add(50, lambda: self._complete_unlock_fade(unlock_covers))

    def _complete_unlock_fade(self, unlock_covers):
        self._locked = False
        Gdk.Display.get_default().sync()
        self.lock.unlock_and_destroy()

        for surface in list(self._surfaces.values()):
            GtkSessionLock.unmap_lock_window(surface)
            surface.destroy()

        self._surfaces.clear()

        finished_covers = [0]
        total_covers = len(unlock_covers)

        def _on_cover_done():
            finished_covers[0] += 1
            if finished_covers[0] >= total_covers:
                self._covers.clear()
                self._pending.clear()
                GLib.idle_add(fabric.Application.get_default().quit)

        # Smoothly fade out covers to reveal unlocked desktop
        for cover in unlock_covers:
            cover.fade_out(duration=0.32, on_done=_on_cover_done)

        return False

    def unlock(self):
        self._locked = False
        Gdk.Display.get_default().sync()
        self.lock.unlock_and_destroy()

        for surface in list(self._surfaces.values()):
            GtkSessionLock.unmap_lock_window(surface)
            surface.destroy()

        self._surfaces.clear()
        self._covers.clear()
        self._pending.clear()

        GLib.idle_add(fabric.Application.get_default().quit)

    def _remove_monitor(self, monitor: Gdk.Monitor):
        self._pending.discard(monitor)

        surface = self._surfaces.pop(monitor, None)
        if surface:
            surface.destroy()

        cover = self._covers.pop(monitor, None)
        if cover:
            cover.destroy()


def lock():
    if __name__ != "__main__":
        subprocess.Popen(
            [sys.executable, __file__],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return None

    app = Application("lock")
    app.set_stylesheet_from_file(os.path.expanduser("~/.config/caffyne-shell/style/style.css"))
    manager = LockManager()
    app.run()


if __name__ == "__main__":
    lock()