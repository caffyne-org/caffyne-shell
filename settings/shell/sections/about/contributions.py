from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib
from snippets import ClippingBox


CACHE_DIR = Path.home() / ".cache" / "caffyne-shell" / "avatars"
GITHUB_API = "https://api.github.com"
_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "caffyne-shell",
    **(
        {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"}
        if "GITHUB_TOKEN" in os.environ
        else {}
    ),
}



def fetch_contributors(repo: str, top_n: int = 10) -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    raw = _get_contributors(repo, top_n)
    result: list[dict] = []

    for entry in raw:
        login = entry.get("login", "ghost")
        commits = entry.get("contributions", 0)
        avatar_url = entry.get("avatar_url", "")

        avatar_path = _ensure_avatar(login, avatar_url)
        result.append(
            {
                "login": login,
                "commits": commits,
                "avatar_path": avatar_path,
                "avatar_url": avatar_url,
            }
        )

    return result


def _get_contributors(repo: str, top_n: int) -> list[dict]:
    url = f"{GITHUB_API}/repos/{repo}/contributors?per_page={top_n}&anon=false"
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, json.JSONDecodeError, Exception):
        return []


def _ensure_avatar(login: str, avatar_url: str) -> str:
    dest = CACHE_DIR / f"{login}.png"
    if dest.exists():
        return str(dest)

    if not avatar_url:
        return ""

    sized_url = avatar_url.split("?")[0] + "?s=64"
    try:
        req = urllib.request.Request(sized_url, headers={"User-Agent": "caffyne-shell"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            dest.write_bytes(resp.read())
        return str(dest)
    except Exception:
        return ""


class ContributorRow(Box):
    AVATAR_SIZE = 24

    def __init__(self, username: str, commits: int, avatar_path: str | None = None, **kwargs):
        self._avatar_image = Image(
            # pixel_size=self.AVATAR_SIZE,
            style_classes=["contributor-avatar"],
        )

        self._name_label = Label(
            label=username,
            h_expand=True,
            h_align="start",
            style_classes=["contributor-name"],
        )

        self._commits_label = Label(
            label=f"{commits:,} commits",
            h_align="end",
            style_classes=["contributor-commits"],
        )

        super().__init__(
            orientation="h",
            spacing=8,
            style_classes=["app-row", "contributor-row"],
            children=[
                ClippingBox(v_expand=False, v_align="center", style="border-radius: 12px;", children=self._avatar_image),
                self._name_label,
                self._commits_label,
            ],
            **kwargs,
        )

        if avatar_path and os.path.exists(avatar_path):
            self._load_avatar(avatar_path)

    def _load_avatar(self, path: str) -> None:
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, self.AVATAR_SIZE, self.AVATAR_SIZE, True
            )
            GLib.idle_add(self._apply_pixbuf, pixbuf)
        except Exception:
            pass

    def _apply_pixbuf(self, pixbuf: GdkPixbuf.Pixbuf) -> bool:
        self._avatar_image.set_from_pixbuf(pixbuf)
        return False

    def set_avatar_from_path(self, path: str) -> None:
        threading.Thread(target=self._load_avatar, args=(path,), daemon=True).start()