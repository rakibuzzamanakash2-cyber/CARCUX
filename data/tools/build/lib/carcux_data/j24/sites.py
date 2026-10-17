"""The fact-checkers indexed, and how.

All publish through WordPress, whose public REST API lists posts by date
(`/wp-json/wp/v2/posts?after=…&before=…`). `checked` says whether that was confirmed on
17 October 2026; an unconfirmed site is tried, and if it does not answer as WordPress
the run says so and moves on (index it by hand, or add an adapter).

AFP Fact Check Bangla and BOOM Bangladesh do not use WordPress; they are listed in the
protocol for manual indexing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    api: str  # base of the WordPress REST API, without the trailing /posts
    language: str  # bn or en
    domains: tuple[str, ...]  # the fact-checker's own domains (its links are not sources)
    checked: bool


SITES = (
    Site("rumorscanner-bn", "Rumor Scanner", "https://rumorscanner.com/wp-json/wp/v2", "bn",
         ("rumorscanner.com",), True),
    Site("rumorscanner-en", "Rumor Scanner", "https://rumorscanner.com/en/wp-json/wp/v2", "en",
         ("rumorscanner.com",), True),
    Site("dismislab-bn", "Dismislab", "https://dismislab.com/wp-json/wp/v2", "bn",
         ("dismislab.com",), False),
    Site("dismislab-en", "Dismislab", "https://en.dismislab.com/wp-json/wp/v2", "en",
         ("dismislab.com",), False),
    Site("factwatch", "FactWatch", "https://www.fact-watch.org/wp-json/wp/v2", "bn",
         ("fact-watch.org",), False),
    Site("bdfactcheck", "BD FactCheck", "https://bdfactcheck.com/wp-json/wp/v2", "bn",
         ("bdfactcheck.com",), False),
)  # fmt: skip

FACT_CHECKER_DOMAINS = frozenset(
    d for s in SITES for d in s.domains
) | {"factcheckbangla.afp.com", "factcheck.afp.com", "boombd.com", "altnews.in",
     "factcrescendo.com"}  # fmt: skip


def by_key(key: str) -> Site:
    for s in SITES:
        if s.key == key:
            return s
    raise KeyError(f"unknown site '{key}'; known: {', '.join(s.key for s in SITES)}")
