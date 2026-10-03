"""What every adapter produces, and safe fetching of feeds.

An adapter turns a source's response into `Item`s: normalised, placed (where
possible) and classified. Fetching is shared and cautious, because admins can
point a source at any URL: http(s) only, no private or local addresses, a few
redirects at most (each one checked), a size cap and a timeout.
"""

import html
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app import __version__
from app.models.signal import EXCERPT_MAX, ContentPolicy, Severity

USER_AGENT = f"CARCUX/{__version__} (disaster situational awareness, Bangladesh)"
MAX_REDIRECTS = 3


class FetchError(Exception):
    """The source could not be read. The message is shown to admins."""


@dataclass
class Request:
    url: str
    method: str = "GET"
    json: dict[str, Any] | None = None
    params: dict[str, str] | None = None


@dataclass
class Item:
    external_id: str
    title: str
    published_at: datetime
    text: str | None = None
    url: str | None = None
    content_policy: ContentPolicy = ContentPolicy.EXCERPT
    language: str = "en"
    event_type: str | None = None
    severity: Severity | None = None
    place_name: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    precision_m: float | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    extraction: dict[str, Any] = field(default_factory=dict)


@dataclass
class Parsed:
    items: list[Item]
    fetched: int  # entries in the response
    skipped: int  # entries left out (not relevant, not in Bangladesh, not placeable)


# --- Text helpers --------------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def plain(text: str | None) -> str:
    """Markup removed, entities decoded, whitespace collapsed."""
    if not text:
        return ""
    return _SPACE.sub(" ", html.unescape(_TAG.sub(" ", html.unescape(text)))).strip()


def excerpt(text: str | None, limit: int = EXCERPT_MAX) -> str | None:
    """At most `limit` characters, cut at a word boundary, with an ellipsis if cut."""
    text = plain(text)
    if not text:
        return None
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…"


def parse_date(value: str | None) -> datetime | None:
    """RFC 822 (RSS) or ISO 8601 (Atom, JSON) to an aware datetime; None if unreadable."""
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# --- Fetching ------------------------------------------------------------------------


def _check_url(url: str, allow_private: bool) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Only http and https addresses can be read")
    if allow_private:
        return
    try:
        infos = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise FetchError(f"Cannot find {parts.hostname}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise FetchError(f"{parts.hostname} points to a private or local address")


def fetch(request: Request, *, timeout: float, max_bytes: int, allow_private: bool) -> bytes:
    """The response body, or FetchError with a short reason."""
    url = request.url
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    with httpx.Client(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _check_url(url, allow_private)
            try:
                with client.stream(
                    request.method, url, json=request.json, params=request.params
                ) as resp:
                    if resp.is_redirect and "location" in resp.headers:
                        url = urljoin(url, resp.headers["location"])
                        continue
                    if resp.status_code >= 400:
                        raise FetchError(f"The source answered HTTP {resp.status_code}")
                    body = bytearray()
                    for chunk in resp.iter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise FetchError(f"Response larger than {max_bytes // 1_000_000} MB")
                    return bytes(body)
            except httpx.TimeoutException:
                raise FetchError(f"No answer within {timeout:.0f} seconds") from None
            except httpx.HTTPError as exc:
                raise FetchError(f"Could not connect: {type(exc).__name__}") from None
    raise FetchError("Too many redirects")
