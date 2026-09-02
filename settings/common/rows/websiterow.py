import webbrowser
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from snippets import Icon

class WebsiteRow(Box):
    def __init__(self, name, website, **kwargs):
        super().__init__(
            style_classes=["app-row"],
            children=[
                Label(h_expand=True, h_align="start", label=name),
                Button(
                    child=Box(
                        spacing=4,
                        children=[
                            Label(style="opacity: 0.8", h_expand=True, h_align="end", label=website),
                            Icon(h_expand=False, icon_name="arrow-square-out")
                        ]
                    ),
                    on_pressed=lambda *_: self.open_website(website)
                )
            ]
        )

    def open_website(self, website):
        url = website
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        webbrowser.open(url)