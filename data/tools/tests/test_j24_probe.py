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


def test_failures_say_why(tmp_path):
    web = Site()
    got = probe_outlet(fetcher(tmp_path, web), "frontpage", "frontpage.example", log=lambda m: None)
    text = report([got])
    assert "front 404" in text  # the synthetic site has no front page
    assert "archive-date 200 12/12 links, 12 same" in text  # ignores the date
    assert "ymd-path 404" in text and "wordpress-api 404" in text


def _mentions_zip(rows):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.CSV", "\n".join("\t".join(r) for r in rows))
    return buf.getvalue()


def test_gdelt_day_counts_articles_per_outlet(tmp_path):
    from datetime import date

    from carcux_data.j24 import gdelt

    # SYNTHETIC mentions: two web articles from paper.example (one on a subdomain), one
    # from elsewhere, one non-web mention.
    row = ["1", "20240802", "20240802", "1", "paper.example", "https://www.paper.example/a/123456"]
    rows = [
        row + ["0"] * 10,
        ["2", "x", "x", "1", "paper.example", "https://en.paper.example/b/654321"] + ["0"] * 10,
        ["3", "x", "x", "1", "other.example", "https://other.example/c/111111"] + ["0"] * 10,
        ["4", "x", "x", "2", "paper.example", "https://paper.example/d/222222"] + ["0"] * 10,
    ]
    body = _mentions_zip(rows)

    def web(url, headers):
        if url.endswith("/robots.txt"):
            return Response(404, {}, b"")
        if url.endswith("20240802000000.mentions.CSV.zip"):
            return Response(200, {}, body)
        return Response(404, {}, b"")

    f = Fetcher(tmp_path / "c", opener=web, sleep=lambda s: None, log=lambda m: None)
    got = gdelt.sample_day(f, date(2024, 8, 2), {"paper.example": "paper"}, every=720,
                           log=lambda m: None)  # fmt: skip
    assert got.by_outlet == {"paper": {"https://www.paper.example/a/123456",
                                       "https://en.paper.example/b/654321"}}  # fmt: skip
    assert (got.files_read, got.files_missing) == (1, 3)
    assert gdelt.stamps(date(2024, 8, 2), 720) == ["20240802000000", "20240802120000"]
