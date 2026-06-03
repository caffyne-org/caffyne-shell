import os
from gi.repository import Gdk
from services.singletons import wm

def get_connector_from_monitor_id(monitor_id: int) -> str | None:
    display = Gdk.Display.get_default()
    monitor = display.get_monitor(monitor_id)
    if monitor is None:
        return None
    geo = monitor.get_geometry()

    if os.getenv("NIRI_SOCKET"):
        try:
            outputs = wm.send_command("Outputs").get("Ok", {}).get("Outputs", {})
            for connector, output in outputs.items():
                logical = output.get("logical")
                if logical is None:
                    continue
                if logical["x"] == geo.x and logical["y"] == geo.y:
                    return connector
        except Exception:
            pass

    elif os.getenv("HYPRLAND_INSTANCE_SIGNATURE"):
        try:
            import json
            monitors = json.loads(wm._send_raw("j/monitors").decode())
            for m in monitors:
                if m.get("x") == geo.x and m.get("y") == geo.y:
                    return m.get("name")
        except Exception:
            pass

    elif os.getenv("MANGO_INSTANCE_SIGNATURE"):
        try:
            reply = wm.send_command("get all-monitors")
            for m in reply.get("monitors", []):
                if m.get("x") == geo.x and m.get("y") == geo.y:
                    return m.get("name")
        except Exception:
            pass
        
    return None