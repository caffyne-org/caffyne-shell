import gi
import cairo
from loguru import logger
from fabric.widgets.svg import Svg as FabricSvg
from fabric.core.service import Property
from utils.svg import get_svg_path
gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg
from user_options import user_options

class Svg(FabricSvg):
    def do_draw(self, cr: cairo.Context):
        if not self._handle:
            return

        context = self.get_style_context()
        state = context.get_state()
        color = context.get_color(state)

        bridge_css = f"""
            * {{ 
                color: rgba({int(color.red * 255)}, {int(color.green * 255)}, {int(color.blue * 255)}, {color.alpha})
            }}
        """

        if self._style_compiled:
            final_style = bridge_css + self._style_compiled
        else:
            final_style = bridge_css

        if not self._handle.set_stylesheet(final_style.encode()):
            logger.error(
                "[Svg] Failed to apply styles, probably invalid style property"
            )

        alloc = self.get_allocation()
        width: int = alloc.width
        height: int = alloc.height

        rect = Rsvg.Rectangle()
        rect.x = rect.y = 0
        rect.width = width
        rect.height = height

        cr.save()
        self._handle.render_document(cr, rect)
        cr.restore()
        
class Icon(Svg):
    def __init__(self, icon_name, icon_size=16, *args, **kwargs):
        self._icon_name = icon_name
        self._current_pack = None
        super().__init__(
            name="icon",
            svg_file=get_svg_path(icon_name, user_options.theme.icon_pack),
            size=icon_size,
            *args,
            **kwargs
        )
        self.connect("realize", self._on_realize)

    def _on_realize(self, _):
        from services.singletons import icon_pack
        self._current_pack = icon_pack.active_pack
        icon_pack.connect("pack-changed", self._on_pack_changed)

    def _on_pack_changed(self, _, pack):
        self._current_pack = pack
        self.set_from_file(get_svg_path(self._icon_name, pack))

    @Property(str, "read-write", default_value="")
    def icon_name(self) -> str:
        return self._icon_name

    @icon_name.setter
    def icon_name(self, value: str):
        self._icon_name = value
        self.set_from_file(get_svg_path(value, self._current_pack))

    def do_finalize_handle(self):
        if not self._handle:
            return
        del self._handle
        self._handle = None