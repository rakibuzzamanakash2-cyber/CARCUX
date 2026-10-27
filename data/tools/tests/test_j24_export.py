"""Fact-check text export from the cache. The fact-checker answers are SYNTHETIC."""

import json

from carcux_data.j24.__main__ import main
from carcux_data.j24.export import HEAD, TAIL, _posts, shorten
from carcux_data.j24.fetch import Fetcher, Response
from carcux_data.j24.sites import SITES

LONG = "SYNTHETIC claim text. " * 300


def test_shorten_keeps_the_opening_and_the_verdict_end():
    s = shorten(LONG + "VERDICT: false.")
    assert s.startswith("SYNTHETIC") and s.endswith("VERDICT: false.") and "[…]" in s
    assert len(s) < HEAD + TAIL + 20
    assert shorten("short") == "short"


def test_export_reads_the_cache_offline(tmp_path):
    site = SITES[0]
    post = {"id": 7, "date": "2024-07-20T10:00:00", "link": "https://fc.example/7",
            "title": {"rendered": "SYNTHETIC title"},
            "content": {"rendered": f"<p>{LONG}</p><p>Verdict: false</p>"}}  # fmt: skip

    def web(url, headers):
        if url.endswith("/robots.txt"):
            return Response(200, {}, b"User-agent: *\nAllow: /\n")
        if url.startswith(f"{site.api}/posts?"):
            return Response(200, {"x-wp-totalpages": "1"}, json.dumps([post]).encode())
        return Response(404, {}, b"")

    online = Fetcher(tmp_path / "cache", opener=web, sleep=lambda s: None, log=lambda m: None)
    assert len(_posts(online, site)) == 1  # fills the cache, as the index did
    assert main(["factcheck-export", "--out", str(tmp_path)]) == 0
    files = sorted((tmp_path / "factcheck_export").glob("batch_*.jsonl"))
    row = json.loads(files[0].read_text("utf-8").splitlines()[0])
    assert row["factcheck_id"] == f"{site.key}:7" and row["published_at"] == "2024-07-20"
    assert row["text"].endswith("Verdict: false")
