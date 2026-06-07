from ..base.window import WMWindow


class HyprlandWindow(WMWindow):

    def __init__(self, service, **kwargs):
        self.__service = service
        super().__init__(**kwargs)

    def sort_key(self) -> tuple:
        return (self.workspace_id, 0, 0)

    @property
    def data(self) -> dict:
        # Include both "id" and "address" so sync works whether called
        # with raw Hyprland data or with another window's .data dict
        return {
            **super().data,
            "address": hex(self._property_helper_id) if self._property_helper_id > 0 else "0x0",
        }

    def sync(self, data: dict) -> None:
        mapped = {}

        # Accept "id" directly (from .data roundtrip)
        if "id" in data:
            mapped["id"] = data["id"]

        # Accept "address" from raw Hyprland JSON
        if "address" in data and "id" not in mapped:
            try:
                mapped["id"] = int(data["address"], 16)
            except (ValueError, TypeError):
                mapped["id"] = hash(data["address"])

        if "title" in data:
            mapped["title"] = data["title"]

        if "class" in data:
            mapped["app_id"] = data["class"]

        if "pid" in data:
            mapped["pid"] = data["pid"]

        if "workspace" in data and isinstance(data["workspace"], dict):
            mapped["workspace_id"] = data["workspace"].get("id", -1)
        elif "workspace_id" in data:
            mapped["workspace_id"] = data["workspace_id"]

        if "is_focused" in data:
            mapped["is_focused"] = data["is_focused"]

        if "floating" in data:
            mapped["is_floating"] = data["floating"]
        elif "is_floating" in data:
            mapped["is_floating"] = data["is_floating"]

        super().sync(mapped)

    def close(self) -> None:
        self.__service.send_command(f'hl.dsp.closewindow({{window = "address:{hex(self.id)}"}})')

    def focus(self) -> None:
        self.__service.send_command(f'hl.dsp.focus({{window = "address:{hex(self.id)}"}})')

    def toggle_fullscreen(self) -> None:
        self.__service.send_command(
            f'hl.dsp.window.fullscreen({{action = "toggle", window = "address:{hex(self.id)}"}})'
        )

    def toggle_floating(self) -> None:
        self.__service.send_command(
            f'hl.dsp.window.float({{action = "toggle", window = "address:{hex(self.id)}"}})'
        )