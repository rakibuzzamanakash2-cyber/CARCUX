"""Polite HTTP for the indexer: one request at a time with a pause between them, robots.txt
respected, every response cached on disk so a second run sends no requests at all."""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

USER_AGENT = "CARCUX-J24-research-indexer/0.1 (academic dataset; fact-check index only)"


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


Opener = Callable[[str, dict[str, str]], Response]


def urllib_opener(url: str, headers: dict[str, str]) -> Response:
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 (http(s) only, below)
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError(f"not an http(s) address: {url}")
    try:
        with urllib.request.urlopen(request, timeout=30) as r:  # noqa: S310
            return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read())


class Disallowed(Exception):
    """robots.txt asks robots not to fetch this address."""


class Fetcher:
    def __init__(
        self,
        cache_dir: Path,
        *,
        delay: float = 2.0,
        contact: str | None = None,
        opener: Opener = urllib_opener,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] = print,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.agent = USER_AGENT if not contact else f"{USER_AGENT[:-1]}; contact {contact})"
        self.opener = opener
        self.sleep = sleep
        self.log = log
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.requests = 0

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def _request(self, url: str) -> Response:
        if self.requests:
            self.sleep(self.delay)
        self.requests += 1
        return self.opener(url, {"User-Agent": self.agent, "Accept": "application/json"})

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self.robots:
            parser = urllib.robotparser.RobotFileParser()
            r = self._request(f"{host}/robots.txt")
            if r.status >= 400:
                parser.parse([])  # no robots.txt: nothing is disallowed
            else:
                parser.parse(r.body.decode("utf-8", "replace").splitlines())
            self.robots[host] = parser
        return self.robots[host].can_fetch(self.agent, url)

    def get_json(self, url: str) -> tuple[int, dict[str, str], object]:
        """(status, headers, parsed JSON or None). Cached responses are reused."""
        cached = self._cache_path(url)
        if cached.exists():
            data = json.loads(cached.read_text(encoding="utf-8"))
            return data["status"], data["headers"], data["json"]
        if not self.allowed(url):
            raise Disallowed(url)
        r = self._request(url)
        try:
            parsed = json.loads(r.body.decode("utf-8")) if r.status < 400 else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
        keep = {k: v for k, v in r.headers.items() if k in ("x-wp-total", "x-wp-totalpages")}
        if r.status < 500:  # do not cache server errors: they may pass
            cached.write_text(
                json.dumps({"url": url, "status": r.status, "headers": keep, "json": parsed},
                           ensure_ascii=False),
                encoding="utf-8",
            )  # fmt: skip
        return r.status, keep, parsed
