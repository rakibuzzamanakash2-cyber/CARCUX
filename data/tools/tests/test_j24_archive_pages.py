"""Listing from the archive's index page by page. The index below is SYNTHETIC."""

import json
from urllib.parse import parse_qs, urlsplit

from carcux_data.j24 import news
from carcux_data.j24.fetch import Fetcher, Response

ROWS = {
    0: [["timestamp", "original", "statuscode", "mimetype"],
        ["20240718100000", "https://paper.example/national/101", "200", "text/html"],
        ["20240718110000", "https://paper.example/national/101?ref=x", "200", "text/html"],
        ["20240719100000", "https://paper.example/national/102", "301", "text/html"]],
    1: [["20240802100000", "https://paper.example/national/103", "200", "text/html"],
        ["20240802100000", "https://paper.example/national/pic.jpg", "200", "image/jpeg"]],
}  # fmt: skip


class Index:
    def __init__(self, fail_page=None):
        self.calls = []
        self.fail_page = fail_page

    def __call__(self, url, headers):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return Response(200, {}, b"User-agent: *\nAllow: /\n")
        q = parse_qs(urlsplit(url).query)
        if "showNumPages" in q:
            return Response(200, {}, b"2\n")
        page = int(q["page"][0])
        assert q["from"] == ["20240701000000"] and q["to"] == ["20240815235959"]
        if page == self.fail_page:
            return Response(504, {}, b"")
        return Response(200, {}, json.dumps(ROWS[page]).encode())


OUTLET = news.NewsOutlet("paper", "A Paper", "BD", "bn", ("paper.example/national/",), None)


def fetcher(tmp_path, web):
    return Fetcher(tmp_path / "c", opener=web, sleep=lambda s: None, log=lambda m: None)


def test_pages_are_read_and_filtered_here(tmp_path):
    got = news.list_outlet_pages(fetcher(tmp_path, Index()), OUTLET, "2024-07-01", "2024-08-15",
                                 log=lambda m: None)  # fmt: skip
    # 101 once (first capture), not 102 (a redirect), 103, not the image.
    assert got == {"https://paper.example/national/101": "20240718100000",
                   "https://paper.example/national/103": "20240802100000"}  # fmt: skip


def test_an_unanswered_page_is_reported_and_filled_by_a_rerun(tmp_path):
    messages = []
    web = Index(fail_page=1)
    f = fetcher(tmp_path, web)
    got = news.list_outlet_pages(f, OUTLET, "2024-07-01", "2024-08-15", log=messages.append)
    assert set(got) == {"https://paper.example/national/101"}
    assert any("1 of 2 pages" in m for m in messages)
    web.fail_page = None
    got = news.list_outlet_pages(f, OUTLET, "2024-07-01", "2024-08-15", log=lambda m: None)
    assert len(got) == 2
    assert sum("page=0" in c for c in web.calls) == 1  # answered page came from the cache


BANGLADESH = "%E0%A6%AC%E0%A6%BE%E0%A6%82%E0%A6%B2%E0%A6%BE%E0%A6%A6%E0%A7%87%E0%A6%B6"


def test_bangla_addresses_are_matched_after_decoding(tmp_path):
    # SYNTHETIC: a percent-encoded Bangla address (the word for Bangladesh) and an unrelated one.
    bn = f"https://www.dw.com/bn/{BANGLADESH}/a-1"
    rows = [
        ["timestamp", "original", "statuscode", "mimetype"],
        ["20240720100000", bn, "200", "text/html"],
        ["20240720100000", "https://www.dw.com/en/football/a-2", "200", "text/html"],
    ]

    def web(url, headers):
        if url.endswith("/robots.txt"):
            return Response(200, {}, b"User-agent: *\nAllow: /\n")
        if "showNumPages" in url:
            return Response(200, {}, b"1\n")
        return Response(200, {}, json.dumps(rows).encode())

    outlet = news.NewsOutlet("dw", "DW", "DE", "en", ("dw.com/",), "bangladesh|বাংলাদেশ")
    got = news.list_outlet_pages(fetcher(tmp_path, web), outlet, "2024-07-01", "2024-08-15",
                                 log=lambda m: None)  # fmt: skip
    assert len(got) == 1 and "/bn/" in next(iter(got))
