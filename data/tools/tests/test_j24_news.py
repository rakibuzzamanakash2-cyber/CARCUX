"""CARCUX-J24 news collector. Every page and index answer below is SYNTHETIC; no real site
or archive is contacted."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from carcux_data.j24 import news
from carcux_data.j24.__main__ import main
from carcux_data.j24.fetch import Fetcher, Response

OUTLET = news.NewsOutlet("paper", "A Paper", "BD", "bn", ("paper.example/national/",), None)

PAGE = """<html lang="bn"><head><title>ignored</title>
<meta property="og:title" content="SYNTHETIC: কোটা আন্দোলনে সংঘর্ষ">
<meta property="article:published_time" content="2024-07-18T14:05:00+06:00">
<script type="application/ld+json">{"datePublished": "2024-07-18T14:00:00+06:00"}</script>
<script>var tracking = "নিহত";</script></head>
<body><p>Synthetic first paragraph about শিক্ষার্থী protest.</p><p>Second.</p></body></html>"""
OFF_TOPIC = """<html lang="bn"><head><title>SYNTHETIC: cricket</title></head>
<body><p>A match report.</p></body></html>"""


class FakeArchive:
    """Answers CDX queries in two pages (with a resume key) and serves captured pages."""

    def __init__(self, robots="User-agent: *\nAllow: /\n"):
        self.robots = robots
        self.calls: list[str] = []

    def __call__(self, url, headers):
        self.calls.append(url)
        parts = urlsplit(url)
        if parts.path.endswith("robots.txt"):
            return Response(200, {}, self.robots.encode())
        if parts.path == "/cdx/search/cdx":
            q = parse_qs(parts.query)
            assert q["from"] == ["20240701000000"] and q["to"] == ["20240815235959"]
            assert "collapse" in q and q["matchType"] == ["prefix"]
            if "resumeKey" not in q:
                rows = [["timestamp", "original"],
                        ["20240718120000", "http://www.paper.example/national/101"],
                        ["20240718130000", "https://paper.example/national/101/amp"],
                        ["20240720090000", "https://paper.example/national/tag/x"],
                        [], ["KEY1"]]  # fmt: skip
            else:
                rows = [
                    ["timestamp", "original"],
                    ["20240801100000", "https://paper.example/national/202?utm=1"],
                ]
            return Response(200, {}, json.dumps(rows).encode())
        if "/web/" in parts.path:
            if parts.path.endswith("/101"):
                return Response(200, {}, PAGE.encode())
            return Response(200, {}, OFF_TOPIC.encode())
        return Response(404, {}, b"")


def fetcher(tmp_path, web, **kw):
    return Fetcher(tmp_path / "cache", opener=web, sleep=lambda s: None, log=lambda m: None, **kw)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://www.paper.example/national/101/", "https://paper.example/national/101"),
        ("https://paper.example/national/101/amp", "https://paper.example/national/101"),
        (
            "https://paper.example/national/101?utm_source=x#top",
            "https://paper.example/national/101",
        ),
        ("https://paper.example/national", None),  # a section front page
        ("https://paper.example/national/tag/quota", None),
        ("https://paper.example/national/photo/1.jpg", None),
        ("https://paper.example/2024/07/20/story", "https://paper.example/2024/07/20/story"),
    ],
)
def test_addresses_are_normalised(url, expected):
    assert news.normalise(url) == expected


def test_listing_follows_resume_keys_and_keeps_the_first_capture(tmp_path):
    web = FakeArchive()
    first = news.list_outlet(fetcher(tmp_path, web), OUTLET, "2024-07-01", "2024-08-15",
                             log=lambda m: None)  # fmt: skip
    assert first == {
        "https://paper.example/national/101": "20240718120000",
        "https://paper.example/national/202": "20240801100000",
    }


def test_article_reading():
    a = news.read_article(PAGE.encode())
    assert a["title"].startswith("SYNTHETIC: কোটা")
    assert a["published_at"] == "2024-07-18T14:05:00+06:00"
    assert a["language"] == "bn" and a["about_uprising"] is True
    assert "নিহত" not in a["scope_terms"]  # script text is not article text
    off = news.read_article(OFF_TOPIC.encode())
    assert off["about_uprising"] is False and off["published_at"] is None


def test_fetch_reads_captures_and_resumes(tmp_path):
    web = FakeArchive()
    f = fetcher(tmp_path, web)
    first = news.list_outlet(f, OUTLET, "2024-07-01", "2024-08-15", log=lambda m: None)
    news.write_urls(tmp_path, OUTLET, first)
    outlets = {"paper": OUTLET}
    r = news.fetch_articles(f, tmp_path, outlets, keys=["paper"], log=lambda m: None)[0]
    assert (r.listed, r.fetched, r.about_uprising, r.failed) == (2, 2, 1, 0)
    assert any("/web/20240718120000id_/https://paper.example/national/101" in c
               for c in web.calls)  # fmt: skip
    rows = [json.loads(x) for x in (tmp_path / "news" / "articles.jsonl").read_text("utf-8")
            .splitlines()]  # fmt: skip
    assert {x["url"] for x in rows} == set(first)
    assert all("text" not in x for x in rows)  # no article text in the working file
    # A second run reads nothing again and writes no duplicates.
    calls = len(web.calls)
    r2 = news.fetch_articles(fetcher(tmp_path, web), tmp_path, outlets, keys=["paper"],
                             log=lambda m: None)[0]  # fmt: skip
    assert len(web.calls) == calls and r2.fetched == 2
    assert len((tmp_path / "news" / "articles.jsonl").read_text("utf-8").splitlines()) == 2


def test_a_trial_can_take_one_day(tmp_path):
    f = fetcher(tmp_path, FakeArchive())
    news.write_urls(tmp_path, OUTLET, news.list_outlet(f, OUTLET, "2024-07-01", "2024-08-15",
                                                       log=lambda m: None))  # fmt: skip
    day = {"since": "2024-07-18", "until": "2024-07-18"}
    r = news.fetch_articles(f, tmp_path, {"paper": OUTLET}, keys=["paper"], log=lambda m: None,
                            **day)[0]  # fmt: skip
    assert r.listed == 1 and r.fetched == 1


def test_robots_txt_stops_an_outlet(tmp_path):
    f = fetcher(tmp_path, FakeArchive())
    news.write_urls(tmp_path, OUTLET, news.list_outlet(f, OUTLET, "2024-07-01", "2024-08-15",
                                                       log=lambda m: None))  # fmt: skip
    blocked = fetcher(tmp_path / "b", FakeArchive(robots="User-agent: *\nDisallow: /web/\n"))
    r = news.fetch_articles(blocked, tmp_path, {"paper": OUTLET}, keys=["paper"],
                            log=lambda m: None)[0]  # fmt: skip
    assert r.fetched == 0 and "robots.txt" in r.problem


def test_rewriting_one_outlet_keeps_the_others(tmp_path):
    other = news.NewsOutlet("other", "Other", "GB", "en", ("other.example/",), None)
    news.write_urls(tmp_path, OUTLET, {"https://paper.example/national/1": "20240702000000"})
    news.write_urls(tmp_path, other, {"https://other.example/a/1": "20240703000000"})
    news.write_urls(tmp_path, OUTLET, {"https://paper.example/national/2": "20240704000000"})
    urls = {u["url"] for u in news.load_urls(tmp_path)}
    assert urls == {"https://paper.example/national/2", "https://other.example/a/1"}


def test_outlet_list_is_well_formed():
    outlets = news.load_news_outlets()
    assert {"prothomalo", "thedailystar", "bbc", "aljazeera", "reuters"} <= set(outlets)
    for o in outlets.values():
        assert o.prefixes and all("/" in p and not p.startswith("http") for p in o.prefixes)
        assert o.country and o.language


def test_cli_rejects_unknown_outlets(tmp_path, capsys):
    assert main(["news-list", "--out", str(tmp_path), "--outlets", "nope"]) == 2
    assert "Unknown outlets" in capsys.readouterr().err
