"""Published dates in the outlets' formats, and the page layouts found in the July 2024
samples (compressed captures, Nuxt state, escaped JSON-LD, section pages). SYNTHETIC pages."""

import gzip
import json

import pytest

from carcux_data.j24.news import parse_date, read_article

SENTENCE = "SYNTHETIC: students protested in District X as police fired tear gas near the bridge "


@pytest.mark.parametrize("raw, want", [
    ("2024-07-18T10:05:00+06:00", "2024-07-18T10:05:00+06:00"),
    ("2024-07-18 10:05:45", "2024-07-18T10:05"),
    ("09:16 AM, 29 June 2024, Saturday", "2024-06-29T09:16"),
    ("11 Jul 2016, 04:32 PM", "2016-07-11T16:32"),
    ("সোমবার, ০১ জুলাই, ২০২৪ ১৩:৩৮", "2024-07-01T13:38"),
    ("০৫:৪২ পিএম, ০১ জুলাই ২০২৪", "2024-07-01T17:42"),
    ("১৮ জুলাই ২০২৪", "2024-07-18"),
])  # fmt: skip
def test_dates_in_outlet_formats(raw, want):
    assert parse_date(raw) == want


@pytest.mark.parametrize("raw", ["1970-01-01T00:00:00.000Z", "01:38 PM, July 2024, Monday",
                                 "31 June 2024", "", None])  # fmt: skip
def test_placeholders_and_dates_without_a_day_are_rejected(raw):
    assert parse_date(raw) is None


def page(head: str = "", body: str = "") -> bytes:
    return f"<html><head>{head}</head><body>{body}</body></html>".encode()


def test_date_from_the_address_when_the_field_has_no_day():
    head = (
        '<meta property="article:published_time" content="01:38 PM, July 2024, Monday">'
        '<meta property="og:url" content="https://paper.example/online/x/2024/07/18/12345">'
    )
    art = read_article(page(head, f"<p>{SENTENCE * 5}</p>"))
    assert (art["published_at"], art["published_source"]) == ("2024-07-18", "address")


def test_date_printed_after_the_label_and_not_the_publisher_line():
    body = (
        "<p>প্রকাশক : SYNTHETIC publisher line</p><span>প্রকাশিত: ০৫:৪২ পিএম, ১৮ জুলাই ২০২৪"
        f"</span><p>{SENTENCE * 5}</p>"
    )
    art = read_article(page(body=body))
    assert (art["published_at"], art["published_source"]) == ("2024-07-18T17:42", "page_text")


def test_image_stamp_is_the_last_resort():
    head = (
        '<meta property="og:url" content="https://paper.example/national/822151/a-b-c-d">'
        '<meta property="og:image" content="https://paper.example/img/image-822151-1721300000.jpg">'
    )
    art = read_article(page(head, f"<p>{SENTENCE * 5}</p>"))
    assert art["published_at"] == "2024-07-18T16:53" and art["published_source"] == "image_stamp"


def test_compressed_capture_is_read():
    html = page(
        '<meta property="article:published_time" content="2024-07-18T10:00:00+06:00">',
        f"<p>{SENTENCE * 5}</p>",
    )
    art = read_article(gzip.compress(html))
    assert art["text_source"] == "paragraphs" and art["text_chars"] >= 300
    assert art["published_at"].startswith("2024-07-18")


def test_nuxt_state_text_and_time():
    content = json.dumps("<p>" + SENTENCE * 5 + "</p>").replace("<", "\\u003C")
    script = ("window.__NUXT__=(function(a){return {data:[{news:{content:" + content +
              ',publishedAt:"1721300000000"}}]}}(1));')  # fmt: skip
    art = read_article(page(body=f"<p>short</p><script>{script}</script>"))
    assert art["text_source"] == "nuxt_state"
    assert art["text_chars"] >= 300 and art["published_source"] == "script_data"


def test_escaped_json_ld_body_is_cleaned():
    body = "&amp;lt;p&amp;gt;" + SENTENCE * 5 + "&amp;lt;/p&amp;gt;"
    ld = json.dumps({"@type": "NewsArticle", "articleBody": body})
    art = read_article(page(f'<script type="application/ld+json">{ld}</script>'))
    assert art["text_source"] == "json_ld" and art["text_chars"] >= 300
    assert art["about_uprising"]  # the scope words are found once the markup is gone


def test_section_pages_are_not_articles():
    head = '<meta property="og:url" content="https://paper.example/country-news">'
    assert read_article(page(head, f"<p>{SENTENCE * 5}</p>"))["is_article"] is False
    head = '<link rel="canonical" href="https://paper.example/national/822151/slug">'
    assert read_article(page(head, f"<p>{SENTENCE * 5}</p>"))["is_article"] is True
