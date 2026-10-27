"""Polite HTTP for the indexer: one request at a time with a pause between them, robots.txt
respected, every response cached on disk so a second run sends no requests at all."""

from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import time
import urllib.error
import urllib.request
import urllib.robotparser
import zlib
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
    url: str | None = None  # where the request ended up, after redirects


Opener = Callable[[str, dict[str, str]], Response]


TIMEOUT = 120  # seconds; the Internet Archive's index can take a minute on large queries
RETRY_WAITS = (15, 60, 180)  # seconds before each retry of a request that failed to connect


def urllib_opener(url: str, headers: dict[str, str]) -> Response:
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 (http(s) only, below)
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError(f"not an http(s) address: {url}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as r:  # noqa: S310
            return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(),
                            r.geturl())  # fmt: skip
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
        self.damaged = 0  # cache files found damaged (crash, power cut) and dropped

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")

    def _request(self, url: str, accept: str = "application/json") -> Response:
        """One request, retried after a pause when the connection fails or times out, or the
        server is busy (429, 5xx). Raises OSError when every attempt failed."""
        for attempt, wait in enumerate((*RETRY_WAITS, None)):
            if self.requests:
                self.sleep(self.delay)
            self.requests += 1
            try:
                r = self.opener(url, {"User-Agent": self.agent, "Accept": accept})
            except (OSError, http.client.HTTPException) as exc:  # timeouts, resets, cut answers
                if wait is None:
                    raise OSError(
                        f"no answer after {len(RETRY_WAITS) + 1} attempts: {exc}"
                    ) from exc
                self.log(f"  no answer ({exc.__class__.__name__}); trying again in {wait} s "
                         f"(attempt {attempt + 2})")  # fmt: skip
                self.sleep(wait)
                continue
            if (r.status == 429 or r.status >= 500) and wait is not None:
                self.log(f"  busy (HTTP {r.status}); trying again in {wait} s")
                self.sleep(wait)
                continue
            return r
        raise OSError("unreachable")  # pragma: no cover

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
            try:
                data = json.loads(cached.read_text(encoding="utf-8"))
                return data["status"], data["headers"], data["json"]
            except (ValueError, KeyError, OSError):
                self.damaged += 1  # damaged by a crash: forget it and ask again
                cached.unlink(missing_ok=True)
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

    def get_page(self, url: str) -> tuple[int, bytes, str]:
        """(status, body, final address after redirects) for a web page, cached compressed on
        disk. Pages stay in the local cache only; nothing here is published."""
        key = hashlib.sha256(url.encode()).hexdigest()
        body_path = self.cache_dir / "pages" / key[:2] / f"{key}.html.gz"
        status_path = body_path.with_suffix(".status")
        if status_path.exists():
            try:
                status_line, _, final = status_path.read_text().partition("\n")
                body = gzip.decompress(body_path.read_bytes()) if body_path.exists() else b""
                return int(status_line), body, final or url
            except (ValueError, OSError, EOFError, zlib.error):
                # Damaged by a crash or power cut: forget it and fetch the page again.
                self.damaged += 1
                status_path.unlink(missing_ok=True)
                body_path.unlink(missing_ok=True)
        if not self.allowed(url):
            raise Disallowed(url)
        r = self._request(url, accept="text/html")
        final = r.url or url
        if r.status < 500:
            body_path.parent.mkdir(parents=True, exist_ok=True)
            if r.status < 400:
                body_path.write_bytes(gzip.compress(r.body))
            status_path.write_text(f"{r.status}\n{final}")
        return r.status, r.body, final
