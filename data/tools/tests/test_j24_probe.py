"""The archive probe. Every site below is SYNTHETIC; nothing real is contacted."""

import json

from carcux_data.j24.fetch import Fetcher, Response
from carcux_data.j24.probe import DAYS, article_links, fill, probe_outlet, report


def page(day: str, n: int = 12) -> bytes:
    links = "".join(f'<a href="/national/{day}-story-{i}-about-something">x</a>' for i in range(n))
    return f"<html><body>{links}<a href='/about'>a</a></body></html>".encode()


class Site:
    """dated.example honours /archive/{date}; frontpage.example ignores the date; wp.example
    answers the WordPress API."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return Response(200, {}, b"User-agent: *\nAllow: /\n")
        if url.startswith("https://dated.example/archive/2024-"):
            return Response(200, {}, page(url.rsplit("/", 1)[1]))
        if url.startswith("https://frontpage.example/archive"):
            return Response(200, {}, page("same"), "https://frontpage.example/")
        if url.startswith("https://wp.example/wp-json/"):
            day = url.split("after=", 1)[1][:10]
            rows = [{"link": f"https://wp.example/{day}/{i}0000"} for i in range(8)]
            return Response(200, {}, json.dumps(rows).encode())
        return Response(404, {}, b"")


def fetcher(tmp_path, web):
    return Fetcher(tmp_path / "c", opener=web, sleep=lambda s: None, log=lambda m: None)


def test_fill_gives_the_day_in_every_form():
    d = DAYS[0]
    assert fill("/archive/{d}", d) == "/archive/2024-07-20"
    assert fill("/{y}/{mon}/{dd}/all", d) == "/2024/jul/20/all"
    ms0 = int(fill("{ms0}", d))
    assert ms0 % 1000 == 0 and int(fill("{ms1}", d)) - ms0 == 24 * 3600_000


def test_article_links_keep_the_outlets_own_articles():
    body = (
        '<a href="/news/2024/kotbari-clash-leaves-many-injured-today">a</a>'
        '<a href="https://other.example/x/123456">b</a><a href="/contact">c</a>'
        '<a href="/news/987654">d</a>'
    )
    assert article_links(body, "https://www.site.example/", "site.example") == {
        "https://www.site.example/news/2024/kotbari-clash-leaves-many-injured-today",
        "https://www.site.example/news/987654",
    }


def test_a_pattern_counts_only_when_the_day_changes_the_links(tmp_path):
    web = Site()
    f = fetcher(tmp_path, web)
    got = {
        h: probe_outlet(f, h.split(".")[0], h, log=lambda m: None)
        for h in ("dated.example", "frontpage.example", "wp.example")
    }
    assert [w[0] for w in got["dated.example"].works] == ["archive-date"]
    assert got["frontpage.example"].works == []
    assert [w[0] for w in got["wp.example"].works] == ["wordpress-api"]
    text = report(list(got.values()))
    assert "2 of 3 outlets" in text and "NONE" in text
