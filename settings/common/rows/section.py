from fabric.widgets.box import Box
from fabric.widgets.label import Label
from snippets import ClippingBox

class PageSection(Box):
    def __init__(self, title, items, **kwargs):
            super().__init__(
            style_classes=["app-page-section"],
            spacing=8,
            orientation="v",
            h_expand=True,
            # h_align="center",
            # v_expand=,
            # v_align="center",
            children=[
                Label(h_align="start", style_classes=["app-page-section-title"], label=title),
                ClippingBox(
                    orientation="v",
                    spacing=1,
                    style_classes=["app-row-container"],
                    children=items
                )
            ],
            **kwargs
        )
    def add_item(self, item):
        self.children[1].add(item)

