from ..base.workspace import WMWorkspace


class HyprlandWorkspace(WMWorkspace):

    def __init__(self, service, **kwargs):
        self.__service = service
        super().__init__(**kwargs)

    def sync(self, data: dict) -> None:
        """
        Maps Hyprland workspace fields to the base WMWorkspace fields.
        Hyprland uses 'id', 'name', 'monitor' (instead of output).
        idx is the same as id in Hyprland (no separate concept).
        """
        mapped = {}

        if "id" in data:
            mapped["id"] = data["id"]
            # Hyprland has no separate idx; use id as a stand-in
            mapped["idx"] = data["id"]

        if "name" in data:
            mapped["name"] = data["name"]

        if "monitor" in data:
            mapped["output"] = data["monitor"]

        if "is_active" in data:
            mapped["is_active"] = data["is_active"]

        if "is_focused" in data:
            mapped["is_focused"] = data["is_focused"]

        if "lastwindow" in data:
            # Hyprland gives us the hex address of the last focused window
            try:
                mapped["active_window_id"] = int(data["lastwindow"], 16)
            except (ValueError, TypeError):
                pass

        if "active_window_id" in data:
            mapped["active_window_id"] = data["active_window_id"]

        super().sync(mapped)

    def switch_to(self) -> None:
        self.__service.send_command(f"hl.dsp.focus({{workspace={self.id}}})")