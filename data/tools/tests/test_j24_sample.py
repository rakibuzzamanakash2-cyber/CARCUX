"""Sampling saved pages. Everything below is SYNTHETIC."""

import json

from carcux_data.j24 import news
from carcux_data.j24.__main__ import main
from carcux_data.j24.fetch import Fetcher, Response


def test_sample_copies_saved_pages(tmp_path):
    outlet = news.NewsOutlet("paper", "A Paper", "BD", "bn", ("paper.example/",), None)
    news.write_urls(tmp_path, outlet, {"https://paper.example/a/1": "20240718120000"})

    def web(url, headers):
        if url.endswith("/robots.txt"):
            return Response(200, {}, b"User-agent: *\nAllow: /\n")
        return Response(200, {}, b"<html>SYNTHETIC page</html>", url)

    f = Fetcher(tmp_path / "cache", opener=web, sleep=lambda s: None, log=lambda m: None)
    f.get_page(f"{news.WAYBACK}/20240718120000id_/https://paper.example/a/1")
    (tmp_path / "news" / "articles.jsonl").write_text(
        json.dumps({"outlet": "paper", "url": "https://paper.example/a/1"}) + "\n",
        encoding="utf-8")  # fmt: skip
    assert main(["news-sample", "--out", str(tmp_path), "--outlets", "paper"]) == 0
    assert (tmp_path / "samples" / "paper_1.html").read_bytes() == b"<html>SYNTHETIC page</html>"
