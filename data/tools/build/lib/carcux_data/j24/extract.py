"""Reading a fact-check article: the links it cites, by kind, and the verdict words it uses.

Everything here is a hint for the person filling the claim sheet. The verdict is the
fact-checker's own and is confirmed by a person from the article; the scope hint only
puts likely uprising-related fact-checks first.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from importlib import resources
from urllib.parse import unquote, urlsplit

from carcux_data.j24.sites import FACT_CHECKER_DOMAINS

SOCIAL = {
    "facebook.com": "facebook", "fb.com": "facebook", "fb.watch": "facebook",
    "x.com": "x", "twitter.com": "x", "t.co": "x",
    "youtube.com": "youtube", "youtu.be": "youtube",
    "tiktok.com": "tiktok", "instagram.com": "instagram", "threads.net": "threads",
    "t.me": "telegram", "whatsapp.com": "whatsapp", "linkedin.com": "linkedin",
}  # fmt: skip
ARCHIVES = {"perma.cc", "archive.ph", "archive.today", "archive.is", "archive.org",
            "web.archive.org", "ghostarchive.org"}  # fmt: skip
TOOLS = {"google.com", "bing.com", "yandex.com", "tineye.com", "invid-project.eu",
         "maps.google.com", "goo.gl", "bit.ly", "infogram.com", "wikipedia.org"}  # fmt: skip


@dataclass(frozen=True)
class Outlet:
    domain: str
    name: str
    source_type: str
    country: str


def load_outlets() -> dict[str, Outlet]:
    text = resources.files("carcux_data.j24").joinpath("outlets.csv").read_text("utf-8")
    return {r["domain"]: Outlet(**r) for r in csv.DictReader(text.splitlines())}


def domain_of(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    for prefix in ("www.", "m.", "mobile.", "amp.", "web.", "en.", "bangla."):
        if host.startswith(prefix) and host.count(".") >= 2 and host != "web.archive.org":
            host = host[len(prefix) :]
    return host


def _registered(domain: str, table) -> str | None:
    """The table key the domain belongs to, matching subdomains (news.example.com)."""
    parts = domain.split(".")
    for i in range(len(parts) - 1):
        candidate = ".".join(parts[i:])
        if candidate in table:
            return candidate
    return None


def wayback_original(url: str) -> str | None:
    """web.archive.org/web/<timestamp>/<original> -> original."""
    m = re.match(r"https?://web\.archive\.org/web/[^/]+/(.+)$", url)
    return unquote(m.group(1)) if m else None


@dataclass(frozen=True)
class Link:
    kind: str  # news, public_record, video_platform, social, archive, fact_checker, tool, other
    domain: str
    url: str
    outlet: Outlet | None = None
    platform: str | None = None


def classify(url: str, outlets: dict[str, Outlet], own: tuple[str, ...] = ()) -> Link | None:
    if not url.startswith(("http://", "https://")):
        return None
    original = wayback_original(url)
    if original:
        inner = classify(original, outlets, own)
        if inner is not None and inner.kind not in ("archive", "tool"):
            return inner  # an archived copy of a news page counts as that outlet
    domain = domain_of(url)
    if not domain:
        return None
    if key := _registered(domain, SOCIAL):
        return Link("social", key, url, platform=SOCIAL[key])
    if _registered(domain, set(own) | FACT_CHECKER_DOMAINS):
        return Link("fact_checker", domain, url)
    if _registered(domain, ARCHIVES):
        return Link("archive", domain, url)
    if key := _registered(domain, outlets):
        o = outlets[key]
        return Link(o.source_type, key, url, outlet=o)
    if _registered(domain, TOOLS):
        return Link("tool", domain, url)
    if domain.endswith(".gov.bd"):
        return Link("public_record", domain, url)
    return Link("other", domain, url)


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href.strip())

    def handle_data(self, data):
        self.text.append(data)


def read_html(html: str) -> tuple[list[str], str]:
    page = _Page()
    page.feed(html or "")
    return page.links, re.sub(r"\s+", " ", "".join(page.text)).strip()


# Verdict words as fact-checkers write them. Longer phrases first, so "partly false"
# wins over "false". A hint only: a person confirms the verdict from the article.
VERDICTS = (
    ("partly_false", ("আংশিক মিথ্যা", "partly false", "partially false", "mostly false")),
    ("partly_true", ("আংশিক সত্য", "partly true", "partially true", "half true")),
    ("misleading", ("বিভ্রান্তিকর", "misleading", "missing context", "out of context")),
    ("altered", ("বিকৃত", "এডিটেড", "সম্পাদিত", "altered", "edited", "manipulated",
                 "doctored", "deepfake", "ডিপফেক")),
    ("satire", ("ব্যঙ্গাত্মক", "স্যাটায়ার", "satire")),
    ("false", ("মিথ্যা", "অসত্য", "ভুয়া", "ভুয়া", "গুজব", "false", "fake", "fabricated",
               "hoax", "baseless")),
    ("true", ("দাবিটি সত্য", "তথ্যটি সত্য", "rated true", "verdict: true", "is true")),
    ("unproven", ("প্রমাণ পাওয়া যায়নি", "unverified", "unproven", "no evidence")),
)  # fmt: skip


def verdict_words(title: str, text: str, categories: list[str]) -> tuple[str | None, list[str]]:
    """The first verdict found in the categories, the title, then the article's end."""
    found: list[str] = []
    for place in (" ".join(categories), title, text[-800:]):
        low = place.lower()
        for label, words in VERDICTS:
            if any(w.lower() in low for w in words) and label not in found:
                found.append(label)
        if found:
            break
    return (found[0] if found else None), found


# Topic words that make a fact-check likely to be about the uprising. A sorting hint;
# whether a claim is in scope is decided by a person.
SCOPE_TERMS = (
    "কোটা", "আন্দোলন", "শিক্ষার্থী", "ছাত্র", "বৈষম্যবিরোধী", "সমন্বয়ক", "কারফিউ",
    "ইন্টারনেট", "গুলি", "নিহত", "পুলিশ", "সংখ্যালঘু", "মন্দির", "পদত্যাগ", "সেনাবাহিনী",
    "হেলিকপ্টার", "ইউনূস", "অন্তর্বর্তী", "quota", "protest", "student", "curfew", "internet",
    "shot", "killed", "police", "minorit", "temple", "resign", "army", "uprising",
    "interim", "hindu", "হিন্দু",
)  # fmt: skip


def scope_terms(title: str, text: str) -> list[str]:
    low = f"{title} {text}".lower()
    return sorted({t for t in SCOPE_TERMS if t.lower() in low})


def url_ref(salt: str, url: str) -> str:
    """Salted SHA-256 of a link: the same post is recognisable across files without the
    public files holding the link."""
    return hashlib.sha256(f"{salt}|{url}".encode()).hexdigest()


def clean_title(rendered: str) -> str:
    _, text = read_html(unescape(rendered or ""))
    return text[:300]
