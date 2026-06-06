import psutil
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.overlay import Overlay
from snippets import Applet, AppletPage, Icon, ClippingBox, ClippingScrolledWindow
from gi.repository import GLib, Gdk
from services.singletons import process_monitor
from snippets import Graph

class SystemMonitorGraph(Graph):
    def __init__(self, dynamic: bool, overlayed: bool = False):
        super().__init__(
            style_classes=["graph", "overlayed"] if overlayed else ["graph"],
            data=[0] * 20,
            min_value=0,
            max_value=100,
            fill=True,
            smooth=True,
            dynamic=dynamic,
        )

class GraphOverlay(Overlay):
    def __init__(self, metric1_name: str, metric2_name: str, dynamic: bool = False):
        self.graph1 = SystemMonitorGraph(dynamic=dynamic)
        self.graph2 = SystemMonitorGraph(dynamic=dynamic, overlayed=True)

        self.metric1_label = Label(style_classes=["graph-label"])
        self.metric2_label = Label(style_classes=["graph-label"])
        self.metric1_extra_label = Label(style_classes=["graph-label", "secondary"])
        self.metric2_extra_label = Label(style_classes=["graph-label", "secondary"])

        super().__init__(
            child=Box(
                orientation="v",
                style_classes=["graph-box"],
                children=[
                    Box(
                        spacing=4,
                        children=[
                            Box(style_classes=["graph-dot"], v_expand=False, v_align="center"),
                            Label(style_classes=["graph-label"], label=metric1_name),
                            Box(
                                h_expand=True,
                                h_align="end",
                                spacing=4,
                                children=[self.metric1_extra_label, self.metric1_label],
                            ),
                        ],
                    ),
                    Box(
                        spacing=4,
                        children=[
                            Box(style_classes=["graph-dot", "overlayed"], v_expand=False, v_align="center"),
                            Label(style_classes=["graph-label"], label=metric2_name),
                            Box(
                                h_expand=True,
                                h_align="end",
                                spacing=4,
                                children=[self.metric2_extra_label, self.metric2_label],
                            ),
                        ],
                    ),
                ],
            ),
            overlays=[self.graph2, self.graph1],
        )

class ProcessMonitorPage(AppletPage):
    def __init__(self, stack):
        self.cpu_temp_overlay = GraphOverlay("CPU", "Temperature")
        self.ram_disk_overlay = GraphOverlay("Memory", "Hard Drive")
        self.network_overlay = GraphOverlay("Download", "Upload", dynamic=True)

        self.prev_net_io = psutil.net_io_counters()
        self.prev_time = GLib.get_monotonic_time()

        self._update_id = None
        self._window_visible = False
        self._page_active = False

        super().__init__(
            title="System Monitor",
            first=True,
            child=Box(
                orientation="v",
                spacing=6,
                children=[
                    ClippingBox(style_classes=["graph-container"], children=[self.cpu_temp_overlay]),
                    ClippingBox(style_classes=["graph-container"], children=[self.ram_disk_overlay]),
                    ClippingBox(style_classes=["graph-container"], children=[self.network_overlay]),
                ],
            ),
            header_right_children=Button(
                style_classes=["applet-misc-button"],
                child=Icon(icon_name="list-magnifying-glass-duotone"),
                on_clicked=lambda *_: stack.set_visible_child_name("processes"),
            ),
        )

    def set_window_visible(self, visible: bool):
        self._window_visible = visible
        self._sync_update()

    def set_page_active(self, active: bool):
        self._page_active = active
        self._sync_update()

    def _sync_update(self):
        should_run = self._window_visible and self._page_active
        if should_run and self._update_id is None:
            self._update_id = GLib.timeout_add(1000, self._update)
        elif not should_run and self._update_id is not None:
            GLib.source_remove(self._update_id)
            self._update_id = None

    def _update(self):

        cpu_percent = psutil.cpu_percent()
        self.cpu_temp_overlay.graph1.push(cpu_percent)
        self.cpu_temp_overlay.metric1_label.set_label(f"{cpu_percent}%")

        temps = psutil.sensors_temperatures()
        if "coretemp" in temps:
            temp = temps["coretemp"][0].current
            self.cpu_temp_overlay.graph2.push(temp)
            self.cpu_temp_overlay.metric2_label.set_label(f"{temp}°C")

        ram = psutil.virtual_memory()
        ram_used_gb = ram.used / (1024 ** 3)
        ram_total_gb = ram.total / (1024 ** 3)
        self.ram_disk_overlay.graph1.push(ram.percent)
        self.ram_disk_overlay.metric1_extra_label.set_label(f"{ram_used_gb:.1f}/{ram_total_gb:.0f}GB")
        self.ram_disk_overlay.metric1_label.set_label(f"{ram.percent}%")

        disk = psutil.disk_usage('/')
        disk_used_gb = disk.used / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)
        self.ram_disk_overlay.graph2.push(disk.percent)
        self.ram_disk_overlay.metric2_extra_label.set_label(f"{disk_used_gb:.0f}/{disk_total_gb:.0f}GB")
        self.ram_disk_overlay.metric2_label.set_label(f"{disk.percent}%")

        current_time = GLib.get_monotonic_time()
        current_net_io = psutil.net_io_counters()
        time_delta = (current_time - self.prev_time) / 1_000_000

        if time_delta > 0:
            download_speed = (current_net_io.bytes_recv - self.prev_net_io.bytes_recv) / time_delta
            upload_speed = (current_net_io.bytes_sent - self.prev_net_io.bytes_sent) / time_delta

            def format_speed(bps):
                if bps < 1024: return f"{bps:.0f} B/s"
                elif bps < 1024 ** 2: return f"{bps / 1024:.1f} KB/s"
                elif bps < 1024 ** 3: return f"{bps / (1024 ** 2):.1f} MB/s"
                else: return f"{bps / (1024 ** 3):.2f} GB/s"

            max_speed_mbps = 100
            self.network_overlay.graph1.push(min((download_speed / (1024 ** 2)) / max_speed_mbps * 100, 100))
            self.network_overlay.graph2.push(min((upload_speed / (1024 ** 2)) / max_speed_mbps * 100, 100))
            self.network_overlay.metric1_label.set_label(format_speed(download_speed))
            self.network_overlay.metric2_label.set_label(format_speed(upload_speed))

        self.prev_net_io = current_net_io
        self.prev_time = current_time
        return True

class ProcessMenuItem(Box):
    def __init__(self, process_dict):
        self.process_dict = process_dict
        self._update_id = None

        self.name_label = Label(
            label=process_dict['name'],
            h_align="start",
            ellipsization="end",
            max_chars_width=20,
            style="font-size: 11px;",
        )
        self.cpu_label = Label(
            label=f"{process_dict['cpu_percent']}%",
            h_align="end",
            style="min-width: 60px; font-size: 11px;",
        )
        self.mem_label = Label(
            label=self._format_memory(process_dict['memory_mb']),
            h_align="end",
            style="min-width: 80px; font-size: 11px;",
        )

        super().__init__(
            style_classes=["menu-device-item"],
            spacing=12,
            children=[
                Box(
                    spacing=8,
                    h_expand=True,
                    children=[
                        self.name_label,
                    ],
                ),
                self.cpu_label,
                self.mem_label,
                Button(
                    style_classes=["process-menu-button"],
                    child=Icon(icon_name="x"),
                    on_clicked=lambda *_: process_monitor.kill_process(self.process_dict['pid']),
                ),
            ],
        )

        self._update_id = GLib.timeout_add(1000, self._update_values)

    def _update_values(self):
        try:
            self.cpu_label.set_label(f"{self.process_dict['cpu_percent']}%")
            self.mem_label.set_label(self._format_memory(self.process_dict['memory_mb']))
            return True
        except:
            return False

    def cleanup(self):
        if self._update_id:
            GLib.source_remove(self._update_id)
            self._update_id = None

    def _format_memory(self, mb):
        if mb >= 1024: return f"{mb / 1024:.1f}GB"
        elif mb >= 1: return f"{int(mb)}MB"
        else: return f"{int(mb * 1024)}KB"

class ProcessesMenu(AppletPage):
    def __init__(self, parent=None, stack=None):
        self._process_widgets = {}
        self._search_text = ""
        self.parent = parent
        self.search_entry = Entry(
            h_expand=True, h_align="fill",
            placeholder="Type to search...",
            style_classes=["process-search"],
        )
        self._entry_box = Box(
            style_classes=["launcher-search"],
            spacing=8,
            children=[
                Icon(icon_name="magnifying-glass-duotone", icon_size=16),
                self.search_entry,
            ],
        )
        self.search_entry.connect("focus-in-event", lambda *_: self._entry_box.add_style_class("focused"))
        self.search_entry.connect("focus-out-event", lambda *_: self._entry_box.remove_style_class("focused"))
        self.title_label = Label(
            label="Processes · 0",
            style_classes=["applet-header-label"],
        )

        self.process_list = Box(orientation="v", spacing=6)

        super().__init__(
            title=None,
            label=self.title_label,
            stack=stack,
            child=Box(
                orientation="v",
                spacing=6,
                children=[
                    self._entry_box,
                    Box(
                        orientation="v",
                        spacing=8,
                        children=[
                        Box(
                            style_classes=["process-header"],
                            spacing=12,
                            children=[
                                Label(label="Name", h_align="start", style="min-width: 60px; font-size: 11px; margin-left: -6px", h_expand=True),
                                Label(label="CPU", h_align="end", style="min-width: 60px; font-size: 11px;"),
                                Label(label="RAM", h_align="end", style="min-width: 80px; font-size: 11px;"),
                                Box(style="min-width: 40px;"),
                            ],
                        ),
                        ClippingScrolledWindow(
                            style_classes=["scrollable"],
                            max_content_size=(324, 330),
                            v_expand=True,
                            child=self.process_list,
                        ),
                        ]
                    )
                ],
            ),

        )

        process_monitor.connect("notify::processes", self._update_process_list)
        self.search_entry.connect("changed", self._on_search_changed)
        # process_monitor.start_monitoring()

        self.connect("realize", lambda *_: (parent.connect("notify::visible", self._on_visibility_changed), parent.connect("key-press-event", self._on_key_press)))

    def _on_key_press(self, _, event):

        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False
        if event.keyval in (
            Gdk.KEY_Escape, Gdk.KEY_Return, Gdk.KEY_Tab,
            Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right,
        ):
            return False

        if not self.search_entry.is_focus():
            self.search_entry.grab_focus()
            self.search_entry.set_position(-1)
        return False

    def _on_visibility_changed(self, *_):
        if not self.parent.get_visible():
            self.search_entry.set_text("")
            self._update_process_list()

    def _on_search_changed(self, entry, *_):
        self._search_text = entry.get_text().lower()
        self._update_process_list()

    def _update_process_list(self, *_):
        processes = process_monitor.processes

        filtered = (
            [p for p in processes if self._search_text in p['name'].lower()]
            if self._search_text else processes
        )

        self.title_label.set_label(f"Processes · {len(filtered)}")

        current_pids = {p['pid'] for p in filtered}
        for pid in [pid for pid in self._process_widgets if pid not in current_pids]:
            self._process_widgets[pid].cleanup()
            del self._process_widgets[pid]

        for proc in filtered:
            if proc['pid'] not in self._process_widgets:
                self._process_widgets[proc['pid']] = ProcessMenuItem(proc)

        self.process_list.children = [self._process_widgets[p['pid']] for p in filtered]

class ProcessMonitorApplet(Applet):
    def __init__(self, parent, **kwargs):
        self.parent = parent
        self._monitor_page = ProcessMonitorPage(self)

        super().__init__(main_menu=self._monitor_page)
        self.add_menu("processes", lambda stack: ProcessesMenu(parent, stack))

        self.connect("realize", self._on_realize)

    def _on_realize(self, *_):
        self.parent.connect("show", self._on_window_show)
        self.parent.connect("hide", self._on_window_hide)
        self._stack.connect("notify::visible-child", self._on_stack_page_changed)
        self._monitor_page.set_page_active(True)
        self._monitor_page.set_window_visible(self.parent.get_visible())

    def _on_window_show(self, *_):
        self._monitor_page.set_window_visible(True)
        # if self.get_visible_child_name() == "processes":
        #     process_monitor.start_monitoring()

    def _on_window_hide(self, *_):
        self._monitor_page.set_window_visible(False)
        process_monitor.stop_monitoring()

    def _on_stack_page_changed(self, stack, *_):
        active_page = self.get_visible_child_name()
        self._monitor_page.set_page_active(active_page == "main")
        if active_page == "processes":
            process_monitor.start_monitoring()
        else:
            process_monitor.stop_monitoring()
