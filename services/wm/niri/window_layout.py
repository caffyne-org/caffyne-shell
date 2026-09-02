from fabric.core.service import Service, Property


class NiriWindowLayout(Service):

    @Property(object, "readable", default_value=None)
    def pos_in_scrolling_layout(self) -> list | None:
        return self._property_helper_pos_in_scrolling_layout

    @Property(object, "readable", default_value=None)
    def tile_size(self) -> list:
        return self._property_helper_tile_size or []

    @Property(object, "readable", default_value=None)
    def window_size(self) -> list:
        return self._property_helper_window_size or []

    @Property(object, "readable", default_value=None)
    def tile_pos_in_workspace_view(self) -> list | None:
        return self._property_helper_tile_pos_in_workspace_view

    @Property(object, "readable", default_value=None)
    def window_offset_in_tile(self) -> list:
        return self._property_helper_window_offset_in_tile or []

    @property
    def data(self) -> dict:
        return {
            "pos_in_scrolling_layout": self.pos_in_scrolling_layout,
            "tile_size": self.tile_size,
            "window_size": self.window_size,
            "tile_pos_in_workspace_view": self.tile_pos_in_workspace_view,
            "window_offset_in_tile": self.window_offset_in_tile,
        }

    def __init__(self, **kwargs):
        self._property_helper_pos_in_scrolling_layout = None
        self._property_helper_tile_size = []
        self._property_helper_window_size = []
        self._property_helper_tile_pos_in_workspace_view = None
        self._property_helper_window_offset_in_tile = []
        super().__init__(**kwargs)

    def sync(self, data: dict) -> None:
        mapping = {
            "pos_in_scrolling_layout": "pos-in-scrolling-layout",
            "tile_size": "tile-size",
            "window_size": "window-size",
            "tile_pos_in_workspace_view": "tile-pos-in-workspace-view",
            "window_offset_in_tile": "window-offset-in-tile",
        }
        for key, notify_name in mapping.items():
            if key in data:
                setattr(self, f"_property_helper_{key}", data[key])
                self.notify(notify_name)
