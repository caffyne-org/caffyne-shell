import psutil
from fabric.widgets.box import Box
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from gi.repository import GLib
from snippets import Icon


class SystemModule(Box):
    def __init__(self, icon_name):
        self.progress_bar = CircularProgressBar(
            style_classes=["progress-bar"],
            start_angle=90,
            end_angle=450,
            size=(48, 48),
            line_width=3,
            min_value=0,
            max_value=100,
            value=0,
        )
        self.progress_overlay = Overlay(
            child=self.progress_bar,
            overlays=Icon(icon_name=icon_name, icon_size=24, h_align="center", v_align="center"),
        )
        self.top_label = Label(style_classes=["desktop-system-module-label", "top"], v_expand=True, v_align="end", h_align="start")
        self.bottom_label = Label(style_classes=["desktop-system-module-label", "bottom"], v_expand=True, v_align="start", h_align="start")
        super().__init__(
            style_classes=["desktop-system-module"],
            spacing=6,
            children=[
                self.progress_overlay,
                Box(
                    orientation="v",
                    children=[self.top_label, self.bottom_label],
                ),
            ]
        )


class DesktopSystem(Box):
    def __init__(self):
        self.cpu_module = SystemModule(icon_name="cpu")
        self.ram_module = SystemModule(icon_name="memory")
        super().__init__(
            spacing=18,
            orientation="v",
            style_classes=["desktop-applet"],
            children=[self.cpu_module, self.ram_module]
        )
        GLib.timeout_add(1000, self._update)
        self._update()

    def _get_cpu_temp(self) -> str:
        try:
            temps = psutil.sensors_temperatures()
            for key in ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz"):
                entries = temps.get(key)
                if entries:
                    pkg = next(
                        (e for e in entries if "package" in e.label.lower()),
                        entries[0],
                    )
                    return f"{pkg.current:.0f}°C"
        except (AttributeError, Exception):
            pass
        return "N/A"

    def _update(self, *_):
        cpu_percent = psutil.cpu_percent(interval=None)
        self.cpu_module.progress_bar.value = cpu_percent
        self.cpu_module.top_label.set_label(f"{cpu_percent:.0f}%")
        self.cpu_module.bottom_label.set_label(self._get_cpu_temp())

        ram = psutil.virtual_memory()
        ram_percent = ram.percent
        self.ram_module.progress_bar.value = ram_percent
        self.ram_module.top_label.set_label(f"{ram_percent:.0f}%")
        self.ram_module.bottom_label.set_label(
            f"{ram.used / 1024**3:.1f}/{ram.total / 1024**3:.0f}GB"
        )
        return True