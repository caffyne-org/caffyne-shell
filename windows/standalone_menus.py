from snippets.applet import Applet
from .quick_settings.menus import AudioMenu, BluetoothMenu, PowerMenu, KeyboardMenu, LogoutMenu, WifiMenu

class AudioApplet(Applet):
    def __init__(self, *args, **kwargs):
        super().__init__(main_menu=AudioMenu(stack=None), **kwargs)

class BluetoothApplet(Applet):
    def __init__(self, *args, **kwargs):
        super().__init__(main_menu=BluetoothMenu(stack=None), **kwargs)

class PowerApplet(Applet):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(main_menu=PowerMenu(parent=parent, stack=None), **kwargs)

class KeyboardApplet(Applet):
    def __init__(self, *args, **kwargs):
        super().__init__(main_menu=KeyboardMenu(stack=None), **kwargs)

class LogoutApplet(Applet):
    def __init__(self, parent,**kwargs):
        super().__init__(main_menu=LogoutMenu(parent=parent, stack=self, qs=False))

class WifiApplet(Applet):
    def __init__(self, parent,**kwargs):
        super().__init__(main_menu= WifiMenu(parent=self, stack=self))

