"""Listing from outlets' sitemaps, and reading the archive copy nearest to the published
date. Every sitemap and page below is SYNTHETIC; no real site or archive is contacted."""

import gzip
import json
from datetime import date
from urllib.parse import urlsplit

from carcux_data.j24 import news, sitemaps
from carcux_data.j24.__main__ import main
from carcux_data.j24.fetch import Fetcher, Response

ROBOTS = "User-agent: *\nAllow: /\nSitemap: https://paper.example/sitemap-index.xml\n"
INDEX = """<?xml version="1.0"?><sitemapindex>
<sitemap><loc>https://paper.example/sitemap/2024-07-18.xml</loc></sitemap>
<sitemap><loc>https://paper.example/sitemap/2024-06-01.xml</loc></sitemap>
<sitemap><loc>https://paper.example/sitemap/2024-08.xml.gz</loc></sitemap>
<sitemap><loc>https://paper.example/post-sitemap9.xml</loc><lastmod>2023-01-01</lastmod></sitemap>
</sitemapindex>"""
DAY = """<urlset xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>https://paper.example/national/101</loc>
 <news:news><news:publication_date>2024-07-18T14:00:00+06:00</news:publication_date>
 <news:title><![CDATA[SYNTHETIC: কোটা আন্দোলন &amp; সংঘর্ষ]]></news:title></news:news></url>
<url><loc>https://paper.example/sports/102</loc><lastmod>2024-07-18</lastmod>
 <news:news><news:title>SYNTHETIC: cricket</news:title></news:news></url>
<url><loc>https://paper.example/national/103</loc></url>
<url><loc>https://elsewhere.example/national/104</loc><lastmod>2024-07-18</lastmod></url>
</urlset>"""
MONTH = """<urlset><url><loc>https://paper.example/national/201</loc>
<lastmod>2024-08-02T10:00:00Z</lastmod></url>
<url><loc>https://paper.example/national/202</loc><lastmod>2024-08-30</lastmod></url></urlset>"""
PAGE = (
    '<html lang="bn"><head><meta property="og:title" content="SYNTHETIC page"></head>'
    "<body><p>কোটা protest student</p></body></html>"
).encode()


class Web:
    """A synthetic outlet with sitemaps, and an archive that redirects to its nearest copy."""

    def __init__(self, capture_for=None):
        self.calls: list[str] = []
        self.capture_for = capture_for or {}

    def __call__(self, url, headers):
        self.calls.append(url)
        parts = urlsplit(url)
        if parts.path == "/robots.txt":
            body = ROBOTS if parts.netloc == "paper.example" else "User-agent: *\nAllow: /\n"
            return Response(200, {}, body.encode())
        if url == "https://paper.example/sitemap-index.xml":
            return Response(200, {}, INDEX.encode())
        if url == "https://paper.example/sitemap/2024-07-18.xml":
            return Response(200, {}, DAY.encode())
        if url == "https://paper.example/sitemap/2024-08.xml.gz":
            return Response(200, {}, gzip.compress(MONTH.encode()))
        if parts.netloc == "web.archive.org":
            article = url.split("id_/", 1)[1]
            ts = self.capture_for.get(article)
            if ts is None:
                return Response(404, {}, b"")
            return Response(200, {}, PAGE, f"https://web.archive.org/web/{ts}id_/{article}")
        return Response(404, {}, b"")


def fetcher(tmp_path, web):
    return Fetcher(tmp_path / "cache", opener=web, sleep=lambda s: None, log=lambda m: None)


def test_parse_reads_blocks_without_an_xml_parser():
    children, urls = sitemaps.parse(INDEX)
    assert len(children) == 4 and urls == []
    _, urls = sitemaps.parse(DAY)
    first = urls[0]
    assert first["published"].startswith("2024-07-18") and "কোটা আন্দোলন & সংঘর্ষ" in first["title"]


def test_dates_in_addresses():
    assert sitemaps.dates_in_address("https://x/sitemap/2024-07-18.xml") == (
        date(2024, 7, 18), date(2024, 7, 18))  # fmt: skip
    assert sitemaps.dates_in_address("https://x/sitemap-2024-08.xml")[1] == date(2024, 8, 31)
    assert sitemaps.dates_in_address("https://x/news/2024/07/20/story") == (
        date(2024, 7, 20), date(2024, 7, 20))  # fmt: skip
    assert sitemaps.dates_in_address("https://x/national/837123") is None


def test_listing_follows_dated_sitemaps_only_and_keeps_the_window(tmp_path):
    web = Web()
    window = date(2024, 7, 1), date(2024, 8, 15)
    got = sitemaps.list_from_sitemaps(fetcher(tmp_path, web), ["paper.example"], *window,
                                      log=lambda m: None)  # fmt: skip
    urls = {r["url"] for r in got.rows}
    # 101 and 102 (dated 18 July), 201 (2 August); not 202 (30 August), not 103 (undated),
    # not 104 (another site).
    assert urls == {"https://paper.example/national/101", "https://paper.example/sports/102",
                    "https://paper.example/national/201"}  # fmt: skip
    assert got.undated == 1
    assert not any("2024-06-01" in c for c in web.calls)  # outside the window: not read
    assert not any("post-sitemap9" in c for c in web.calls)  # last changed before the window


def test_reading_takes_the_copy_nearest_the_published_date_and_flags_late_ones(tmp_path):
    outlet = news.NewsOutlet("paper", "A Paper", "BD", "bn", ("paper.example/",), None)
    web = Web(capture_for={
        "https://paper.example/national/101": "20240718150000",
        "https://paper.example/national/201": "20251001000000",  # captured a year later
    })  # fmt: skip
    f = fetcher(tmp_path, web)
    got = sitemaps.list_from_sitemaps(f, ["paper.example"], date(2024, 7, 1), date(2024, 8, 15),
                                      log=lambda m: None)  # fmt: skip
    news.write_urls(tmp_path, outlet, got.rows, "sitemap")
    r = news.fetch_articles(f, tmp_path, {"paper": outlet}, keys=["paper"], log=lambda m: None)[0]
    assert (r.listed, r.fetched, r.not_archived, r.late) == (3, 2, 1, 1)
    # The likely article (its title names the movement) was read first.
    archive_calls = [c for c in web.calls if "web.archive.org/web/" in c]
    assert archive_calls[0].endswith("/national/101")
    assert "/web/20240718120000id_/" in archive_calls[0]  # asked for the published day
    rows = {x["url"]: x for x in map(json.loads, (tmp_path / "news" / "articles.jsonl")
                                     .read_text("utf-8").splitlines())}  # fmt: skip
    assert rows["https://paper.example/national/101"]["capture"] == "20240718150000"
    assert rows["https://paper.example/national/201"]["capture_late"] is True


def test_only_likely_skips_titles_that_are_not_about_the_uprising(tmp_path):
    outlet = news.NewsOutlet("paper", "A Paper", "BD", "bn", ("paper.example/",), None)
    web = Web(capture_for={"https://paper.example/national/101": "20240718150000"})
    f = fetcher(tmp_path, web)
    got = sitemaps.list_from_sitemaps(f, ["paper.example"], date(2024, 7, 1), date(2024, 8, 15),
                                      log=lambda m: None)  # fmt: skip
    news.write_urls(tmp_path, outlet, got.rows, "sitemap")
    r = news.fetch_articles(f, tmp_path, {"paper": outlet}, keys=["paper"], only_likely=True,
                            log=lambda m: None)[0]  # fmt: skip
    assert r.skipped == 1  # the cricket story
    assert not any("/sports/102" in c for c in web.calls)


def test_archive_and_sitemap_listings_merge(tmp_path):
    outlet = news.NewsOutlet("paper", "A Paper", "BD", "bn", ("paper.example/",), None)
    news.write_urls(tmp_path, outlet, {"https://paper.example/national/101": "20240718150000"})
    row = {"url": "https://paper.example/national/101/", "published": "2024-07-18", "title": "T"}
    news.write_urls(tmp_path, outlet, [row], "sitemap")
    rows = news.load_urls(tmp_path)
    assert len(rows) == 1
    assert rows[0]["capture"] == "20240718150000" and rows[0]["title"] == "T"
    # Re-listing from sitemaps replaces only the sitemap rows.
    news.write_urls(tmp_path, outlet, [], "sitemap")
    assert news.load_urls(tmp_path)[0]["title"] is None


def test_cli_lists_from_sitemaps_by_default(tmp_path, monkeypatch, capsys):
    web = Web()
    outlets = {"paper": news.NewsOutlet("paper", "A Paper", "BD", "bn", ("paper.example/",), None)}
    monkeypatch.setattr(news, "load_news_outlets", lambda: outlets)
    monkeypatch.setattr("time.sleep", lambda s: None)

    import carcux_data.j24.fetch as fetch_module

    original = fetch_module.Fetcher.__init__

    def init(self, *a, **kw):
        kw["opener"] = web
        kw["sleep"] = lambda s: None
        original(self, *a, **kw)

    monkeypatch.setattr(fetch_module.Fetcher, "__init__", init)
    assert main(["news-list", "--out", str(tmp_path), "--outlets", "paper"]) == 0
    out = capsys.readouterr().out
    assert "paper: 3 articles in the window" in out and "1 undated left out" in out


def test_undated_sitemaps_are_given_up_when_they_hold_nothing_from_the_window(tmp_path):
    # SYNTHETIC: one dated sitemap for the window, then 60 undated ones holding only 2023.
    index = (
        "<sitemapindex>"
        + "".join(
            f"<sitemap><loc>https://big.example/posts-{i}.xml</loc></sitemap>" for i in range(60)
        )
        + "<sitemap><loc>https://big.example/sitemap/2024-07-20.xml</loc></sitemap></sitemapindex>"
    )
    old = "<urlset><url><loc>https://big.example/a/1</loc><lastmod>2023-05-01</lastmod></url></urlset>"
    day = "<urlset><url><loc>https://big.example/a/2</loc><lastmod>2024-07-20</lastmod></url></urlset>"

    class Big(Web):
        def __call__(self, url, headers):
            self.calls.append(url)
            if url.endswith("/robots.txt"):
                return Response(200, {}, b"Sitemap: https://big.example/index.xml\n")
            if url.endswith("/index.xml"):
                return Response(200, {}, index.encode())
            if "2024-07-20" in url:
                return Response(200, {}, day.encode())
            return Response(200, {}, old.encode())

    web, messages = Big(), []
    window = date(2024, 7, 1), date(2024, 8, 15)
    got = sitemaps.list_from_sitemaps(fetcher(tmp_path, web), ["big.example"], *window,
                                      log=messages.append)  # fmt: skip
    assert [r["url"] for r in got.rows] == ["https://big.example/a/2"]
    # The dated sitemap was read first; then 25 undated ones before giving up.
    reads = [c for c in web.calls if c.endswith(".xml") and "index" not in c]
    assert "2024-07-20" in reads[0] and len(reads) == 1 + sitemaps.GIVE_UP_AFTER
    assert got.sitemaps_skipped == 60 - sitemaps.GIVE_UP_AFTER
    assert any("held nothing from the window" in m for m in messages)
