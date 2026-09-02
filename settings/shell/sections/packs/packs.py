from ....common.components import AppPage
from ....common.rows import PageSection
from .components import InstalledPacksBrowser, AvailablePacksBrowser

from services.singletons import icon_pack, style_service, sound_packs
from services.templates import template_service


class SoundInstalledPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Manage",
        title="Manage",
        items=[
            PageSection(
                title="Installed",
                items=[InstalledPacksBrowser(sound_packs)],
            ),
        ],
        **kwargs,
    )

class SoundDownloadPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Download",
        title="Download",
        items=[
            PageSection(
                title="Download",
                items=[AvailablePacksBrowser(sound_packs)],
            ),
        ],
        **kwargs,
    )

class TemplateInstalledPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Manage",
        title="Manage",
        items=[
            PageSection(
                title="Installed",
                items=[InstalledPacksBrowser(template_service)],
            ),
        ],
        **kwargs,
    )

class TemplateDownloadPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Download",
        title="Download",
        items=[
            PageSection(
                title="Download",
                items=[AvailablePacksBrowser(template_service)],
            ),
        ],
        **kwargs,
    )

class StyleInstalledPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Manage",
        title="Manage",
        items=[
            PageSection(
                title="Installed",
                items=[InstalledPacksBrowser(style_service)],
            ),
        ],
        **kwargs,
    )

class StyleDownloadPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Download",
        title="Download",
        items=[
            PageSection(
                title="Download",
                items=[AvailablePacksBrowser(style_service)],
            ),
        ],
        **kwargs,
    )



class IconInstalledPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Manage",
        title="Manage",
        items=[
            PageSection(
                title="Installed",
                items=[InstalledPacksBrowser(icon_pack)],
            ),
        ],
        **kwargs,
    )

class IconDownloadPage(AppPage):
    def __init__(self, **kwargs):
        super().__init__(
        name="Download",
        title="Download",
        items=[
            PageSection(
                title="Download",
                items=[AvailablePacksBrowser(icon_pack)],
            ),
        ],
        **kwargs,
    )