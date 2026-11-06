"""Finding a working feed for a news outlet, and reading Google News sitemaps."""

from datetime import UTC, datetime

from defusedxml import ElementTree

from app.ingest import outlets, rss
from app.ingest.base import FetchError, Request
from app.models.signal import Source

NOW = datetime(2026, 11, 6, 12, tzinfo=UTC)

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Flood: Sylhet embankment breaks, villages under water</title>
<link>https://news.example.com/a1</link><pubDate>Thu, 05 Nov 2026 08:00:00 +0600</pubDate>
<description>Water entered villages in Sylhet after the embankment broke.</description></item>
</channel></rss>"""

OLD_RSS = RSS.replace(b"2026", b"2019")

NEWS_SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url><loc>https://news.example.com/b1</loc><news:news>
  <news:publication><news:name>Example</news:name><news:language>bn</news:language></news:publication>
  <news:publication_date>2026-11-05T09:00:00+06:00</news:publication_date>
  <news:title>Flood in Sylhet: embankment breaks, villages under water</news:title>
</news:news></url>
<url><loc>https://news.example.com/b2</loc><news:news>
  <news:publication_date>2026-11-05T10:00:00+06:00</news:publication_date>
  <news:title>Cricket: Bangladesh win the series</news:title>
</news:news></url>
</urlset>"""


def site(pages: dict[str, bytes]):
    asked = []

    def fetch(req: Request) -> bytes:
        asked.append(req.url)
        if req.url not in pages:
            raise FetchError("The source answered HTTP 404")
        return pages[req.url]

    return fetch, asked


def test_news_sitemap_reads_like_a_feed():
    rows = rss.entries(ElementTree.fromstring(NEWS_SITEMAP))
    assert [r[1] for r in rows] == [
        "Flood in Sylhet: embankment breaks, villages under water",
        "Cricket: Bangladesh win the series",
    ]
    source = Source(key="x", name="x", language="bn")
    parsed = rss.parse(NEWS_SITEMAP, source, now=NOW)
    assert parsed.fetched == 2
    assert [i.url for i in parsed.items] == ["https://news.example.com/b1"]  # cricket skipped


def test_listed_feed_is_used_when_it_works():
    o = outlets.Outlet("x", "X", "https://news.example.com", "bn",
                       ("https://news.example.com/rss.xml",))  # fmt: skip
    fetch, asked = site({"https://news.example.com/rss.xml": RSS})
    found = outlets.find_feed(o, fetch, NOW)
    assert found and found.url == "https://news.example.com/rss.xml" and found.items == 1


def test_stale_feed_is_rejected_and_the_announced_one_found():
    home = b'<html><head><link rel="alternate" type="application/rss+xml" href="/live.xml">'
    o = outlets.Outlet("x", "X", "https://news.example.com", "bn",
                       ("https://news.example.com/old.xml",))  # fmt: skip
    fetch, _ = site({"https://news.example.com/old.xml": OLD_RSS,
                     "https://news.example.com": home,
                     "https://news.example.com/live.xml": RSS})  # fmt: skip
    found = outlets.find_feed(o, fetch, NOW)
    assert found and found.url == "https://news.example.com/live.xml"


def test_news_sitemap_from_robots_is_the_last_resort():
    robots = (b"User-agent: *\nSitemap: https://news.example.com/sitemap.xml\n"
              b"Sitemap: https://news.example.com/news-sitemap.xml\n")  # fmt: skip
    o = outlets.Outlet("x", "X", "https://news.example.com", "bn")
    fetch, _ = site({"https://news.example.com/robots.txt": robots,
                     "https://news.example.com/news-sitemap.xml": NEWS_SITEMAP})  # fmt: skip
    found = outlets.find_feed(o, fetch, NOW)
    assert found and found.url == "https://news.example.com/news-sitemap.xml"


def test_other_sites_announced_on_the_home_page_are_not_followed():
    home = b'<link rel="alternate" type="application/rss+xml" href="https://evil.example.net/f">'
    o = outlets.Outlet("x", "X", "https://news.example.com", "bn")
    fetch, asked = site({"https://news.example.com": home,
                         "https://evil.example.net/f": RSS})  # fmt: skip
    assert outlets.find_feed(o, fetch, NOW) is None
    assert "https://evil.example.net/f" not in asked


def test_outlet_keys_are_unique_and_short():
    keys = [o.key for o in outlets.OUTLETS]
    assert len(keys) == len(set(keys)) and all(len(k) <= 40 for k in keys)


def test_an_english_outlet_does_not_take_the_bangla_edition_feed():
    o = outlets.Outlet("x", "X", "https://news.example.com", "en")
    bangla = NEWS_SITEMAP
    fetch, asked = site({"https://news.example.com/bangla/googlenews.xml": bangla,
                         "https://news.example.com/robots.txt":
                             b"Sitemap: https://news.example.com/bangla/googlenews.xml\n",
                         "https://news.example.com/googlenews.xml": NEWS_SITEMAP})  # fmt: skip
    found = outlets.find_feed(o, fetch, NOW)
    assert found and found.url == "https://news.example.com/googlenews.xml"
    assert "https://news.example.com/bangla/googlenews.xml" not in asked


def test_common_news_sitemap_names_are_tried():
    o = outlets.Outlet("x", "X", "https://news.example.com", "bn")
    fetch, _ = site({"https://news.example.com/news_sitemap.xml": NEWS_SITEMAP})
    found = outlets.find_feed(o, fetch, NOW)
    assert found and found.url == "https://news.example.com/news_sitemap.xml"
