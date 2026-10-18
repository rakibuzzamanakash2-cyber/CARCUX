"""The GDELT Project's public index of news articles, as a way to list outlets' articles
when their own sitemaps and date pages do not.

GDELT 2.0 publishes, every 15 minutes, a "mentions" file listing the web articles it read
(the English stream, and a translated stream for other languages such as Bangla). Each row
names the article's site and its address. Only these address lists are read here; nothing
is taken from the articles themselves.

`sample_day` reads one day's files and counts, per outlet, the articles GDELT listed, so the
probe can say how complete GDELT is for an outlet before relying on it: for outlets whose
sitemaps were read, it also reports how many of their sitemap articles GDELT has too.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

from carcux_data.j24.fetch import Disallowed, Fetcher

BASE = "http://data.gdeltproject.org/gdeltv2/"
STREAMS = {"english": "{ts}.mentions.CSV.zip", "translated": "{ts}.translation.mentions.CSV.zip"}
WEB = "1"  # MentionType: a web article


def stamps(day: date, every: int = 15) -> list[str]:
    return [f"{day:%Y%m%d}{m // 60:02d}{m % 60:02d}00" for m in range(0, 24 * 60, every)]


def read_mentions(body: bytes) -> Iterator[tuple[str, str]]:
    """(site, address) for each web article in one zipped mentions file."""
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        for name in z.namelist():
            for line in z.read(name).decode("utf-8", "replace").splitlines():
                parts = line.split("\t")
                if len(parts) > 5 and parts[3] == WEB and parts[5].startswith("http"):
                    yield parts[4].lower(), parts[5]


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


@dataclass
class DaySample:
    day: date
    files_read: int = 0
    files_missing: int = 0
    by_outlet: dict[str, set[str]] = field(default_factory=dict)
    problem: str | None = None


def sample_day(
    fetcher: Fetcher,
    day: date,
    hosts: dict[str, str],
    *,
    every: int = 15,
    log: Callable[[str], None] = print,
) -> DaySample:
    """hosts: {host: outlet key}. Reads every file of the day (every=15) or a sample."""
    out = DaySample(day)
    total = len(stamps(day, every)) * len(STREAMS)
    for ts in stamps(day, every):
        for stream, pattern in STREAMS.items():
            url = BASE + pattern.format(ts=ts)
            try:
                status, body, _ = fetcher.get_page(url)
            except Disallowed:
                out.problem = "robots.txt disallows GDELT's files"
                return out
            except OSError as exc:
                out.files_missing += 1
                log(f"  {stream} {ts}: not reachable ({type(exc).__name__})")
                continue
            if status >= 400 or not body:
                out.files_missing += 1
                continue
            try:
                rows = list(read_mentions(body))
            except zipfile.BadZipFile:
                out.files_missing += 1
                continue
            out.files_read += 1
            for _, address in rows:
                h = host_of(address)
                key = hosts.get(h) or next(
                    (k for base, k in hosts.items() if h.endswith("." + base)), None
                )  # fmt: skip
                if key:
                    out.by_outlet.setdefault(key, set()).add(address)
        done = out.files_read + out.files_missing
        if done and done % 48 == 0:
            log(f"  GDELT {day}: {done} of {total} files read")
    return out
