
from __future__ import annotations

import threading

from gi.repository import GLib

from ....common.components import AppPage
from ....common.rows import InfoRow, WebsiteRow, PageSection
from snippets import Icon

from .contributions import fetch_contributors, ContributorRow

REPO = "caffyne-org/caffyne-shell"
TOP_N = 10


class ShellInfoPage(AppPage):
    def __init__(self, **kwargs):
        self._credits_section = PageSection(
            title="Credits",
            items=[]
        )

        super().__init__(
            name="Shell",
            title="caffyne",
            items=[
                Icon(icon_name="caffyne-standard", icon_size=128),
                PageSection(
                    title="Welcome",
                    items=[
                        InfoRow(name="Version", info="Coffee 1.0.0"),
                        WebsiteRow(name="Website", website="caffyne.org")
                    ]
                ),
                self._credits_section,
            ],
            **kwargs,
        )

        threading.Thread(target=self._load_contributors, daemon=True).start()
    def _load_contributors(self) -> None:
        contributors = fetch_contributors(REPO, top_n=TOP_N)
        GLib.idle_add(self._populate_contributors, contributors)

    def _populate_contributors(self, contributors: list[dict]) -> bool:
        for contributor in contributors:
            row = ContributorRow(
                username=contributor["login"],
                commits=contributor["commits"],
                avatar_path=contributor["avatar_path"],
            )
            self._credits_section.add_item(row)

        return False