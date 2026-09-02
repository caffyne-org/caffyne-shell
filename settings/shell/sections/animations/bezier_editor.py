from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.entry import Entry
from gi.repository import Gtk, Gdk


class BezierEditor(Box):
    SIZE = 180

    def __init__(self, bezier: list[float], on_changed, **kwargs):
        super().__init__(orientation="v", spacing=8, **kwargs)
        self.on_changed = on_changed
        self.bx1, self.by1, self.bx2, self.by2 = bezier
        self._dragging = None  # "h1" or "h2"

        self._canvas = Gtk.DrawingArea()
        self._canvas.set_size_request(self.SIZE, self.SIZE)
        self._canvas.connect("draw", self._on_draw)
        self._canvas.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )
        self._canvas.connect("button-press-event",   self._on_press)
        self._canvas.connect("button-release-event", self._on_release)
        self._canvas.connect("motion-notify-event",  self._on_motion)
        self._entries = []
        entry_row = Box(orientation="h", spacing=4)
        for label_text, attr in [("X1", "bx1"), ("Y1", "by1"), ("X2", "bx2"), ("Y2", "by2")]:
            col = Box(orientation="v", spacing=2)
            lbl = Label(label=label_text, style_classes=["bezier-entry-label"])
            entry = Entry(
                text=f"{getattr(self, attr):.2f}",
                style_classes=["bezier-entry"],
                max_length=4,
                width_chars=4,
            )
            entry.connect("changed", self._on_entry_changed)
            self._entries.append((attr, entry))
            col.add(lbl)
            col.add(entry)
            entry_row.add(col)

        self.add(self._canvas)
        self.add(entry_row)
        self.show_all()


    def _curve_to_canvas(self, bx, by):
        pad = 20
        s = self.SIZE - pad * 2
        return pad + bx * s, self.SIZE - pad - by * s

    def _canvas_to_curve(self, cx, cy):
        pad = 20
        s = self.SIZE - pad * 2
        bx = (cx - pad) / s
        by = (self.SIZE - pad - cy) / s
        return max(0.0, min(1.0, bx)), max(0.0, min(1.0, by))

    def _on_draw(self, widget, cr):
        s = self.SIZE
        pad = 20

        # Background
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.8)
        cr.rectangle(0, 0, s, s)
        cr.fill()

        # Grid lines
        cr.set_source_rgba(1, 1, 1, 0.08)
        cr.set_line_width(1)
        for i in range(1, 4):
            x = pad + (s - pad * 2) * i / 4
            y = pad + (s - pad * 2) * i / 4
            cr.move_to(x, pad); cr.line_to(x, s - pad)
            cr.move_to(pad, y); cr.line_to(s - pad, y)
        cr.stroke()

        # Diagonal baseline
        cr.set_source_rgba(1, 1, 1, 0.15)
        cr.move_to(pad, s - pad)
        cr.line_to(s - pad, pad)
        cr.stroke()

        p0x, p0y = pad, s - pad
        p3x, p3y = s - pad, pad
        h1x, h1y = self._curve_to_canvas(self.bx1, self.by1)
        h2x, h2y = self._curve_to_canvas(self.bx2, self.by2)

        # Handle lines
        cr.set_source_rgba(1, 1, 1, 0.25)
        cr.set_line_width(1)
        cr.move_to(p0x, p0y); cr.line_to(h1x, h1y)
        cr.move_to(p3x, p3y); cr.line_to(h2x, h2y)
        cr.stroke()

        # Bezier curve
        cr.set_source_rgba(0.4, 0.8, 1.0, 1.0)
        cr.set_line_width(2)
        cr.move_to(p0x, p0y)
        cr.curve_to(h1x, h1y, h2x, h2y, p3x, p3y)
        cr.stroke()

        # Handles
        for hx, hy, color in [
            (h1x, h1y, (0.4, 0.8, 1.0, 1.0)),
            (h2x, h2y, (1.0, 0.6, 0.2, 1.0)),
        ]:
            cr.set_source_rgba(*color)
            cr.arc(hx, hy, 6, 0, 6.283)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.8)
            cr.arc(hx, hy, 6, 0, 6.283)
            cr.set_line_width(1.5)
            cr.stroke()

        # Anchor dots
        cr.set_source_rgba(1, 1, 1, 0.6)
        for ax, ay in [(p0x, p0y), (p3x, p3y)]:
            cr.arc(ax, ay, 4, 0, 6.283)
            cr.fill()

        return False

    def _hit_test(self, x, y, radius=10) -> str | None:
        h1x, h1y = self._curve_to_canvas(self.bx1, self.by1)
        h2x, h2y = self._curve_to_canvas(self.bx2, self.by2)
        if (x - h1x) ** 2 + (y - h1y) ** 2 <= radius ** 2:
            return "h1"
        if (x - h2x) ** 2 + (y - h2y) ** 2 <= radius ** 2:
            return "h2"
        return None

    def _on_press(self, widget, event):
        self._dragging = self._hit_test(event.x, event.y)

    def _on_release(self, widget, event):
        self._dragging = None

    def _on_motion(self, widget, event):
        if not self._dragging:
            return
        bx, by = self._canvas_to_curve(event.x, event.y)
        if self._dragging == "h1":
            self.bx1, self.by1 = bx, by
        else:
            self.bx2, self.by2 = bx, by
        self._sync_entries()
        self._canvas.queue_draw()
        self.on_changed(self.bx1, self.by1, self.bx2, self.by2)

    def _on_entry_changed(self, entry):
        try:
            vals = {attr: float(e.get_text()) for attr, e in self._entries}
            self.bx1 = max(0.0, min(1.0, vals["bx1"]))
            self.by1 = max(0.0, min(1.0, vals["by1"]))
            self.bx2 = max(0.0, min(1.0, vals["bx2"]))
            self.by2 = max(0.0, min(1.0, vals["by2"]))
            self._canvas.queue_draw()
            self.on_changed(self.bx1, self.by1, self.bx2, self.by2)
        except ValueError:
            pass  # user still typing

    def _sync_entries(self):
        for attr, entry in self._entries:
            entry.set_text(f"{getattr(self, attr):.2f}")

    def set_bezier(self, bezier: list[float]):
        self.bx1, self.by1, self.bx2, self.by2 = bezier
        self._sync_entries()
        self._canvas.queue_draw()
