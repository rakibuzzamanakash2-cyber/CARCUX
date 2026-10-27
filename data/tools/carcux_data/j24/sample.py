"""Copy a few saved article pages per outlet out of the cache, to look at how an outlet lays
out its pages when the reader misses their text or date. Offline; public news pages only."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from carcux_data.j24.news import WAYBACK, day_key, load_urls


def sample(out: Path, outlets: list[str], n: int = 3) -> list[Path]:
    urls = {u["url"]: u for u in load_urls(out)}
    source = out / "news" / "articles_all.jsonl"
    if not source.exists():
        source = out / "news" / "articles.jsonl"
    folder = out / "samples"
    folder.mkdir(exist_ok=True)
    taken: dict[str, int] = {k: 0 for k in outlets}
    written = []
    for line in source.read_text("utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        key = r.get("outlet")
        if key not in taken or taken[key] >= n:
            continue
        u = urls.get(r["url"])
        when = (u.get("capture") or day_key(u)) if u else None
        if not when:
            continue
        digest = hashlib.sha256(f"{WAYBACK}/{when}id_/{r['url']}".encode()).hexdigest()
        page = out / "cache" / "pages" / digest[:2] / f"{digest}.html.gz"
        if not page.exists():
            continue
        taken[key] += 1
        path = folder / f"{key}_{taken[key]}.html"
        path.write_bytes(gzip.decompress(page.read_bytes()))
        written.append(path)
        if all(v >= n for v in taken.values()):
            break
    return written
