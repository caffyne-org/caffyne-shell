"""
Shared HTTP layer for the pack services.

Every pack browser lists a GitHub repo and then pulls a `meta.json` for each
pack it finds, so opening the settings app is a dozen-plus API calls and it is
easy to burn through GitHub's 60-per-hour unauthenticated allowance. This module
puts a disk cache in front of those requests:

  * inside the TTL nothing touches the network at all;
  * past it, a conditional request carrying the stored ETag usually comes back
    304, which GitHub does not count against the rate limit;
  * once we know we are rate limited we stop asking until the window resets;
  * and if a request fails anyway, the cached copy is served instead of an
    error, so the pack browsers keep working offline.

It also turns transport exceptions into sentences worth showing a user.
"""

import asyncio
import hashlib
import json
import socket
import time

from pathlib import Path

import aiohttp
from loguru import logger

API_CACHE_DIR = Path.home() / ".cache" / "caffyne-shell" / "pack_api"

# Long enough that browsing the settings app costs nothing after the first
# visit, short enough that a newly published pack shows up the same day.
DEFAULT_TTL = 30 * 60

REQUEST_TIMEOUT = 20

# Unix timestamp of the moment GitHub said our quota resets. While this is in
# the future every request is served from cache instead of spending a call to
# be told "no" again.
_rate_limited_until: float = 0.0


class PackFetchError(Exception):
    """A fetch failure carrying a message that is safe to show to the user."""


def _describe(exc: BaseException) -> str:
    """
    Log-safe rendering of an exception. Some aiohttp errors raise from their own
    __str__, and losing the cached response to a broken log line would be a poor
    trade, so fall back to the class name.
    """
    try:
        return f"{type(exc).__name__}: {exc}"
    except Exception:
        return type(exc).__name__


def make_session() -> aiohttp.ClientSession:
    """A session with a timeout, so a stalled connection surfaces as an error."""
    return aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    )


# ── Cache ─────────────────────────────────────────────────────────────────

def _entry_path(url: str) -> Path:
    return API_CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()}.json"


def _read_entry(url: str) -> dict | None:
    try:
        with open(_entry_path(url)) as f:
            entry = json.load(f)
        if "body" in entry:
            return entry
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning(f"[pack_fetch] unreadable cache entry for {url}: {_describe(e)}")
    return None


def _write_entry(url: str, entry: dict) -> None:
    try:
        API_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _entry_path(url)
        tmp  = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(entry, f)
        tmp.replace(path)
    except Exception as e:
        logger.warning(f"[pack_fetch] could not cache {url}: {e}")


def _miss_path(url: str) -> Path:
    return API_CACHE_DIR / f"{hashlib.sha256(url.encode()).hexdigest()}.miss"


def _recent_miss(url: str, ttl: int) -> bool:
    """True if this URL 404'd recently enough that asking again is wasted."""
    try:
        return time.time() - _miss_path(url).stat().st_mtime < ttl
    except OSError:
        return False


def _record_miss(url: str) -> None:
    try:
        API_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _miss_path(url).touch()
    except Exception as e:
        logger.warning(f"[pack_fetch] could not record miss for {url}: {_describe(e)}")


def _clear_miss(url: str) -> None:
    try:
        _miss_path(url).unlink()
    except OSError:
        pass


def clear_cache() -> None:
    """Drop every cached response. Used by the browsers' refresh action."""
    global _rate_limited_until
    _rate_limited_until = 0.0
    try:
        for entry in API_CACHE_DIR.glob("*.json"):
            entry.unlink()
        for entry in API_CACHE_DIR.glob("*.miss"):
            entry.unlink()
    except Exception as e:
        logger.warning(f"[pack_fetch] could not clear cache: {e}")


# ── Rate limiting ─────────────────────────────────────────────────────────

def _is_rate_limited(resp: aiohttp.ClientResponse) -> bool:
    if resp.status == 429:
        return True
    return (
        resp.status == 403
        and resp.headers.get("x-ratelimit-remaining") == "0"
    )


def _note_rate_limit(resp: aiohttp.ClientResponse) -> None:
    global _rate_limited_until
    if not _is_rate_limited(resp):
        return
    reset = resp.headers.get("x-ratelimit-reset") or resp.headers.get("retry-after")
    try:
        # x-ratelimit-reset is an absolute timestamp, retry-after a delay.
        value = float(reset)
        _rate_limited_until = value if value > 1e6 else time.time() + value
    except (TypeError, ValueError):
        _rate_limited_until = time.time() + 15 * 60
    logger.warning(
        f"[pack_fetch] rate limited by GitHub until "
        f"{time.strftime('%H:%M', time.localtime(_rate_limited_until))}"
    )


def rate_limit_message() -> str:
    minutes = max(1, int((_rate_limited_until - time.time()) // 60 + 1))
    if _rate_limited_until <= time.time():
        return "GitHub is limiting how often packs can be checked. Try again shortly."
    unit = "minute" if minutes == 1 else "minutes"
    return (
        f"GitHub is limiting how often packs can be checked. "
        f"Try again in about {minutes} {unit}."
    )


# ── Errors ────────────────────────────────────────────────────────────────

def friendly_error(exc: BaseException) -> str:
    """Turn a fetch exception into something worth showing in the settings app."""
    if isinstance(exc, PackFetchError):
        return str(exc)

    if isinstance(exc, (asyncio.TimeoutError, aiohttp.ServerTimeoutError)):
        return "GitHub took too long to respond. Check your connection and try again."

    if isinstance(exc, aiohttp.ClientResponseError):
        if exc.status in (403, 429):
            return rate_limit_message()
        if exc.status == 404:
            return "The pack list isn't where it used to be on GitHub."
        if exc.status >= 500:
            return "GitHub is having problems right now. Try again in a few minutes."
        return f"GitHub turned the request down (error {exc.status})."

    if isinstance(exc, (aiohttp.ClientConnectorError, socket.gaierror)):
        return "Can't reach GitHub. Check your internet connection."

    if isinstance(exc, aiohttp.ClientError):
        return "The connection to GitHub was interrupted. Try again."

    if isinstance(exc, OSError):
        return "Can't reach GitHub. Check your internet connection."

    if isinstance(exc, (json.JSONDecodeError, ValueError)):
        return "GitHub sent back something unreadable. Try again in a moment."

    return "Something went wrong while loading packs."


# ── Fetch ─────────────────────────────────────────────────────────────────

async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict | None = None,
    ttl: int = DEFAULT_TTL,
    force: bool = False,
):
    """
    GET `url` and return the decoded JSON, going through the disk cache.

    `force=True` skips the freshness check and the rate-limit hold, but still
    sends the ETag so an unchanged response stays free. Raises PackFetchError,
    whose message is user-facing, only when there is no cached copy to fall
    back on.
    """
    entry = _read_entry(url)
    now   = time.time()

    if entry and not force and now - entry.get("fetched_at", 0) < ttl:
        return entry["body"]

    if entry and not force and _rate_limited_until > now:
        return entry["body"]

    request_headers = dict(headers or {})
    if entry and entry.get("etag"):
        request_headers["If-None-Match"] = entry["etag"]

    try:
        async with session.get(url, headers=request_headers) as resp:
            _note_rate_limit(resp)

            if resp.status == 304 and entry:
                entry["fetched_at"] = now
                _write_entry(url, entry)
                return entry["body"]

            if _is_rate_limited(resp):
                if entry:
                    return entry["body"]
                raise PackFetchError(rate_limit_message())

            resp.raise_for_status()
            body = await resp.json(content_type=None)

            _write_entry(url, {
                "url":        url,
                "etag":       resp.headers.get("ETag"),
                "fetched_at": now,
                "body":       body,
            })
            return body

    except PackFetchError:
        raise
    except Exception as e:
        if entry:
            # Stale beats broken: the browser can still show what we had.
            logger.warning(f"[pack_fetch] serving cached copy of {url}: {_describe(e)}")
            return entry["body"]
        raise PackFetchError(friendly_error(e)) from e


async def fetch_bytes(
    session: aiohttp.ClientSession,
    url: str,
    headers: dict | None = None,
    ttl: int = DEFAULT_TTL,
    force: bool = False,
) -> bytes | None:
    """
    GET `url` as raw bytes, for preview images. Returns None instead of raising
    — a missing preview is not worth failing a whole pack list over.

    A successful fetch is cached by the caller as a file on disk, but a pack
    with no preview at all leaves nothing behind, so misses are remembered here
    too. Without that, every pack lacking a preview costs a request on every
    single refresh.
    """
    if not force and _recent_miss(url, ttl):
        return None

    try:
        async with session.get(url, headers=headers or {}) as resp:
            _note_rate_limit(resp)
            if resp.status != 200:
                # Only a definitive "not there" is worth remembering; a rate
                # limit or server error should be retried.
                if resp.status in (404, 410):
                    _record_miss(url)
                return None
            data = await resp.read()
            _clear_miss(url)
            return data
    except Exception as e:
        logger.warning(f"[pack_fetch] preview fetch failed for {url}: {_describe(e)}")
        return None
