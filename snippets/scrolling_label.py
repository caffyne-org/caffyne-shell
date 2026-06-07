import cairo
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib, PangoCairo
from snippets.animator import Animator
from fabric.widgets.widget import Widget


class ScrollingLabel(Gtk.DrawingArea, Widget):
    def __init__(
        self,
        label: str = "---",
        pixels_per_second: float = 50.0,
        max_width: int = 200,
        fade_width: int = 24,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes=None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align=None,
        v_align=None,
        h_expand: bool = False,
        v_expand: bool = False,
        size=None,
        **kwargs,
    ):
        Gtk.DrawingArea.__init__(self)
        Widget.__init__(
            self,
            name,
            visible,
            all_visible,
            style,
            style_classes,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            size,
            **kwargs,
        )

        self._label = label
        self.max_width_limit = max_width
        self.fade_width = fade_width
        self.set_halign(Gtk.Align.START)

        self._text_w = 0
        self._gap = 48

        self._pixels_per_second = pixels_per_second

        self._state = "idle"
        self._is_looping = False

        self._scroll_animator = (
            Animator(
                bezier_curve=(0.4, 0.0, 0.2, 1.0),
                duration=1.0,
                min_value=0.0,
                max_value=1.0,
                tick_widget=self,
                notify_value=lambda *_: self.queue_draw(),
            )
            .build()
            .unwrap()
        )
        self._scroll_animator.connect("finished", self._on_scroll_finished)

        self._reset_animator = (
            Animator(
                bezier_curve=(0.0, 0.0, 0.3, 1.0),  # ease-out feel
                duration=0.4,
                min_value=0.0,
                max_value=1.0,
                tick_widget=self,
                notify_value=lambda *_: self.queue_draw(),
            )
            .build()
            .unwrap()
        )
        self._reset_animator.connect("finished", self._on_reset_finished)

        self.set_events(
            self.get_events()
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.show_all()

    # ------------------------------------------------------------------ #
    #  Label property                                                      #
    # ------------------------------------------------------------------ #

    def get_label(self) -> str:
        return self._label

    def set_label(self, new_label: str):
        if self._label != str(new_label):
            self._label = str(new_label)
            self._hard_reset()
            self.queue_resize()

    @property
    def label(self) -> str:
        return self._label

    @label.setter
    def label(self, value: str):
        self.set_label(value)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _scroll_duration(self) -> float:
        return (self._text_w + self._gap) / max(self._pixels_per_second, 1.0)

    def _is_overflowing(self) -> bool:
        return self._text_w > self.get_allocated_width()

    def _start_scroll(self):
        self._reset_animator.pause()
        self._state = "scrolling"
        self._scroll_animator.pause()
        self._scroll_animator.min_value = 0.0
        self._scroll_animator.max_value = 1.0
        self._scroll_animator.value = 0.0
        self._scroll_animator.duration = self._scroll_duration()
        self._scroll_animator.play()

    def _start_reset(self):
        """Smoothly animate back from wherever we are to position 0."""
        current_offset = self._scroll_animator.value
        if current_offset <= 0.0:
            self._hard_reset()
            return

        self._scroll_animator.pause()
        self._state = "resetting"
        # Animate from current_offset → 0 by using reset animator 0→1
        # and mapping it in do_draw as: offset = current_offset * (1 - reset_t)
        self._reset_from = current_offset
        self._reset_animator.pause()
        self._reset_animator.min_value = 0.0
        self._reset_animator.max_value = 1.0
        self._reset_animator.value = 0.0
        self._reset_animator.play()

    def _hard_reset(self):
        self._state = "idle"
        self._is_looping = False  # Reset loop state
        self._scroll_animator.pause()
        self._scroll_animator.value = 0.0
        self._reset_animator.pause()
        self._reset_animator.value = 0.0
        self.queue_draw()
    # ------------------------------------------------------------------ #
    #  Event handlers                                                      #
    # ------------------------------------------------------------------ #

    def _on_enter(self, *_):
        if self._is_overflowing() and self._state != "scrolling":
            self._start_scroll()

    def _on_leave(self, *_):
        if self._state == "scrolling":
            self._start_reset()
        elif self._state == "idle":
            pass  # nothing to do

    def _on_scroll_finished(self, *_):
        # Loop if still hovered, otherwise reset
        if self._state == "scrolling":
            GLib.idle_add(self._loop_or_reset)

    def _loop_or_reset(self):
        if self._state == "scrolling":
            self._is_looping = True
            self._start_scroll()
        return GLib.SOURCE_REMOVE


    def _on_reset_finished(self, *_):
        self._hard_reset()

    # ------------------------------------------------------------------ #
    #  GTK size negotiation                                                #
    # ------------------------------------------------------------------ #

    def do_get_preferred_width(self):
        layout = self.create_pango_layout(self._label)
        layout.set_font_description(
            self.get_style_context().get_font(Gtk.StateFlags.NORMAL)
        )
        text_w, _ = layout.get_pixel_size()
        natural = min(text_w, self.max_width_limit)
        return natural, natural

    def do_get_preferred_height(self):
        layout = self.create_pango_layout(self._label)
        layout.set_font_description(
            self.get_style_context().get_font(Gtk.StateFlags.NORMAL)
        )
        _, text_h = layout.get_pixel_size()
        return text_h, text_h

    # ------------------------------------------------------------------ #
    #  Drawing                                                             #
    # ------------------------------------------------------------------ #

    def _current_scroll_offset(self) -> float:
        """Returns the raw pixel offset to shift text by."""
        if self._state == "scrolling":
            slot = self._text_w + self._gap
            return slot * self._scroll_animator.value
        elif self._state == "resetting":
            slot = self._text_w + self._gap
            return slot * self._reset_from * (1.0 - self._reset_animator.value)
        return 0.0

    def _draw_text_at(self, cr, layout, x, y):
        """Draw layout at (x, y) with current source."""
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

    def _draw_faded_edge(self, cr, layout, x_offset, y_pos, height, width, slot, fade, side="right"):
        """
        Overdraw a fade zone on one edge using strips of decreasing alpha.
        Each strip clips to a thin vertical band and redraws the text at
        lower and lower opacity, faking a smooth fade without any mask.
        side: "right" fades from full alpha at (width - fade) to 0 at width
              "left"  fades from 0 at 0 to full alpha at fade
        """
        steps = 12
        strip_w = fade / steps

        for i in range(steps):
            if side == "right":
                # i=0 is near full, i=steps-1 is near transparent
                t = i / (steps - 1)          # 0.0 → 1.0 left to right
                alpha_mult = 1.0 - t
                strip_x = (width - fade) + i * strip_w
            else:
                # i=0 is near transparent, i=steps-1 is near full
                t = i / (steps - 1)
                alpha_mult = t
                strip_x = i * strip_w

            cr.save()
            cr.rectangle(strip_x, 0, strip_w + 0.5, height)  # +0.5 avoids hairline gaps
            cr.clip()
            rgba = self.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha * alpha_mult)
            self._draw_text_at(cr, layout, x_offset, y_pos)
            self._draw_text_at(cr, layout, x_offset + slot, y_pos)
            cr.restore()

    def do_draw(self, cr):
            width = self.get_allocated_width()
            height = self.get_allocated_height()

            style_context = self.get_style_context()
            rgba = style_context.get_color(Gtk.StateFlags.NORMAL)
            font_desc = style_context.get_font(Gtk.StateFlags.NORMAL)

            layout = self.create_pango_layout(self._label)
            layout.set_font_description(font_desc)
            text_w, text_h = layout.get_pixel_size()
            self._text_w = text_w

            y_pos = (height - text_h) / 2

            if text_w > width:
                x_offset = -self._current_scroll_offset()
                fade = self.fade_width
                slot = text_w + self._gap
                scrolling = self._state in ("scrolling", "resetting")

                left_fade = 0.0
                if scrolling and x_offset < 0:
                    if self._is_looping:
                        left_fade = float(fade)
                    else:
                        left_fade = min(abs(x_offset), float(fade))
                    
                    if self._state == "resetting":
                        left_fade *= (1.0 - self._reset_animator.value)

                cr.save()
                cr.push_group()

                cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
                self._draw_text_at(cr, layout, x_offset, y_pos)
                self._draw_text_at(cr, layout, x_offset + slot, y_pos)

                text_pattern = cr.pop_group()
                cr.restore()

                mask_gradient = cairo.LinearGradient(0, 0, width, 0)

                if left_fade > 0:
                    mask_gradient.add_color_stop_rgba(0.0, 0, 0, 0, 0.0)
                    mask_gradient.add_color_stop_rgba(left_fade / width, 0, 0, 0, 1.0)
                else:
                    mask_gradient.add_color_stop_rgba(0.0, 0, 0, 0, 1.0)

                mask_gradient.add_color_stop_rgba((width - fade) / width, 0, 0, 0, 1.0)
                mask_gradient.add_color_stop_rgba(1.0, 0, 0, 0, 0.0)

                cr.save()
                cr.set_source(text_pattern)
                cr.mask(mask_gradient)
                cr.restore()

            else:
                cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
                cr.move_to(0.0, y_pos)
                PangoCairo.show_layout(cr, layout)