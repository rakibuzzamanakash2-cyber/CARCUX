"""The article reader's fallbacks and the offline rebuild. Every page below is SYNTHETIC."""

import json

from carcux_data.j24 import news
from carcux_data.j24.__main__ import main
from carcux_data.j24.fetch import Fetcher, Response
from carcux_data.j24.news import read_article

SENTENCE = "SYNTHETIC: students protested in District X as police fired tear gas near the bridge "
BODY = SENTENCE * 6  # well over the 300-character threshold


def test_paragraph_pages_read_as_before():
    html = f"<html><head><title>T</title></head><body><p>{BODY}</p></body></html>"
    art = read_article(html.encode())
    assert art["text_source"] == "paragraphs" and art["text_chars"] >= 300


def test_json_ld_article_body_is_used_when_paragraphs_are_missing():
    ld = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "NewsArticle", "headline": "SYNTHETIC: কোটা আন্দোলন", "articleBody": BODY,
         "datePublished": "2024-07-18T10:00:00+06:00"}]})  # fmt: skip
    html = (
        f'<html><head><script type="application/ld+json">{ld}</script></head><body></body></html>'
    )
    art = read_article(html.encode())
    assert art["text_source"] == "json_ld" and art["title"] == "SYNTHETIC: কোটা আন্দোলন"
    assert art["published_at"].startswith("2024-07-18") and art["about_uprising"]


def test_script_data_is_used_for_script_built_pages():
    blocks = [{"type": "text", "text": f"Part {i}. " + SENTENCE * 2} for i in range(3)]
    blocks.append({"type": "link", "text": "https://x.example"})
    data = {"props": {"pageProps": {"blocks": blocks}}}
    html = ('<html><head><meta property="og:title" content="SYNTHETIC title"></head><body>'
            f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
            "</body></html>")  # fmt: skip
    art = read_article(html.encode())
    assert art["text_source"] == "script_data" and art["text_chars"] >= 300


def test_long_text_blocks_are_used_for_pages_without_paragraphs():
    html = ("<html><body><nav>" + "menu item text that is long enough to count " * 3 + "</nav>"
            f"<div class='details'>{SENTENCE}</div>" * 5 + "</body></html>")  # fmt: skip
    art = read_article(html.encode())
    assert art["text_source"] == "text_blocks" and "menu item" not in BODY
    assert art["text_chars"] >= 300


def test_rebuild_rereads_the_cache_offline_and_joins_runs(tmp_path):
    outlet = news.NewsOutlet("paper", "A Paper", "BD", "bn", ("paper.example/",), None)
    news.write_urls(tmp_path, outlet, {"https://paper.example/a/1": "20240718120000",
                                       "https://paper.example/a/2": "20240719120000"})  # fmt: skip
    page = (f"<html><body><div>{SENTENCE}</div>" * 5 + "</body></html>").encode()

    def web(url, headers):
        if url.endswith("/robots.txt"):
            return Response(200, {}, b"User-agent: *\nAllow: /\n")
        return Response(200, {}, page, url)

    f = Fetcher(tmp_path / "cache", opener=web, sleep=lambda s: None, log=lambda m: None)
    for u, ts in (("https://paper.example/a/1", "20240718120000"),
                  ("https://paper.example/a/2", "20240719120000")):  # fmt: skip
        f.get_page(f"{news.WAYBACK}/{ts}id_/{u}")
    # The first reader recorded no text; a part run read article 2 again.
    old = {
        "outlet": "paper",
        "url": "https://paper.example/a/1",
        "text_chars": 0,
        "about_uprising": False,
        "text_from": "wayback",
        "published_at": "2024-07-18",
    }
    (tmp_path / "news" / "articles.jsonl").write_text(
        json.dumps(old) + "\n" + json.dumps({**old, "url": "https://paper.example/a/2"}) + "\n"
        + "{broken line\n", encoding="utf-8")  # fmt: skip
    (tmp_path / "part2" / "news").mkdir(parents=True)
    (tmp_path / "part2" / "news" / "articles.jsonl").write_text(
        json.dumps({**old, "url": "https://paper.example/a/2"}) + "\n", encoding="utf-8"
    )
    assert main(["news-rebuild", "--out", str(tmp_path), "--parts", "part2"]) == 0
    rows = [
        json.loads(x)
        for x in (tmp_path / "news" / "articles_all.jsonl").read_text("utf-8").splitlines()
    ]
    assert len(rows) == 2  # duplicate and broken line dropped
    assert all(r["text_chars"] >= 300 and r["about_uprising"] for r in rows)
    assert all(r["published_in_window"] is True for r in rows)
    assert "TOTAL" in (tmp_path / "news" / "rebuild.txt").read_text("utf-8")


def test_a_damaged_cache_file_counts_as_missing(tmp_path):
    def web(url, headers):
        if url.endswith("/robots.txt"):
            return Response(200, {}, b"User-agent: *\nAllow: /\n")
        return Response(200, {}, b"<html>fresh</html>", url)

    f = Fetcher(tmp_path / "c", opener=web, sleep=lambda s: None, log=lambda m: None)
    url = "https://paper.example/a/1"
    f.get_page(url)
    status_file = next((tmp_path / "c" / "pages").rglob("*.status"))
    status_file.write_bytes(b"\x00" * 64)  # what a power cut left behind
    status, body, _ = f.get_page(url)
    assert status == 200 and body == b"<html>fresh</html>" and f.damaged == 1
