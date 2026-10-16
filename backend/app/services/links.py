"""Links an analyst pastes: a Facebook post, a YouTube video, a news article, any page.

CARCUX never opens the link. Everything here is read from the URL itself: which
platform, the post's id, the account where the URL names it, and a canonical form
without tracking parameters, so the same post pasted twice is one item. What the post
says is pasted by the analyst. That keeps collection within the platforms' terms (no
scraping, no logins) and avoids fetching arbitrary addresses from the server.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

# Query parameters that only track who shared a link.
TRACKING = re.compile(
    r"^(utm_.*|fbclid|gclid|igshid|igsh|si|s|t|ref|ref_src|ref_url|mibextid|"
    r"__cft__.*|__tn__|_rdr|rdid|share_url|feature|app|sfnsn|from|wtsid)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Platform:
    key: str
    label: str
    kind: str  # dataset source_type: social, video_platform or news
    video: bool = False  # the item is a video (dataset modality)


FACEBOOK = Platform("facebook", "Facebook", "social")
YOUTUBE = Platform("youtube", "YouTube", "video_platform", video=True)
X = Platform("x", "X (Twitter)", "social")
TIKTOK = Platform("tiktok", "TikTok", "video_platform", video=True)
INSTAGRAM = Platform("instagram", "Instagram", "social")
TELEGRAM = Platform("telegram", "Telegram", "social")
WEB = Platform("web", "Website", "news")
# Opinions people post on CARCUX's own public site (never parsed from a link).
CARCUX_PUBLIC = Platform("carcux", "CARCUX public site", "social")
PLATFORMS = {
    p.key: p for p in (FACEBOOK, YOUTUBE, X, TIKTOK, INSTAGRAM, TELEGRAM, WEB, CARCUX_PUBLIC)
}


@dataclass(frozen=True)
class Link:
    platform: Platform
    canonical_url: str  # identity: the same post always gives the same string
    url: str  # to open: the link as pasted, without tracking parameters
    domain: str
    post_id: str | None
    account: str | None  # handle or page name as the URL shows it
    video: bool

    @property
    def external_id(self) -> str:
        """Stable id of the item at its source."""
        if self.post_id:
            return f"{self.platform.key}:{self.post_id}"
        return self.canonical_url


class BadLinkError(ValueError):
    pass


def _host(netloc: str) -> str:
    host = netloc.lower().split("@")[-1].split(":")[0]
    for prefix in ("www.", "m.", "mbasic.", "web.", "mobile.", "touch.", "business."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def _clean_query(query: str, keep: tuple[str, ...] | None = None) -> str:
    pairs = [
        (k, v[0])
        for k, v in parse_qs(query, keep_blank_values=False).items()
        if not TRACKING.match(k) and (keep is None or k in keep)
    ]
    return urlencode(sorted(pairs))


def parse(url: str) -> Link:
    """What the URL says about the item. Raises BadLinkError for anything that is not
    an http(s) address."""
    url = url.strip()
    if not re.match(r"^https?://", url, re.IGNORECASE):
        if re.match(r"^[\w.-]+\.[a-z]{2,}/", url, re.IGNORECASE):
            url = "https://" + url
        else:
            raise BadLinkError("Paste a full link, starting with https://")
    parts = urlsplit(url)
    host = _host(parts.netloc)
    if not host or "." not in host:
        raise BadLinkError("That does not look like a web address")
    path = re.sub(r"/+$", "", parts.path) or "/"
    query = parse_qs(parts.query)
    seg = [s for s in path.split("/") if s]

    def q(name: str) -> str | None:
        return (query.get(name) or [None])[0]

    clean = urlunsplit(
        (parts.scheme.lower(), parts.netloc, parts.path, _clean_query(parts.query), "")
    )

    def made(platform: Platform, canonical: str, post_id=None, account=None, video=None):
        opened = canonical if platform is not WEB else clean
        is_video = platform.video if video is None else video
        return Link(platform, canonical, opened, host, post_id, account, is_video)

    if host in ("facebook.com", "fb.com", "fb.watch"):
        if host == "fb.watch" and seg:
            return made(FACEBOOK, f"https://fb.watch/{seg[0]}", f"watch-{seg[0]}", video=True)
        if path in ("/permalink.php", "/story.php") and q("story_fbid"):
            pid = q("story_fbid")
            return made(
                FACEBOOK,
                f"https://www.facebook.com/permalink.php?story_fbid={pid}&id={q('id')}",
                pid,
                q("id"),
            )
        if path in ("/watch", "/watch/") and q("v"):
            return made(FACEBOOK, f"https://www.facebook.com/watch?v={q('v')}", q("v"), video=True)
        if path == "/photo" or path == "/photo.php":
            pid = q("fbid")
            if pid:
                return made(FACEBOOK, f"https://www.facebook.com/photo?fbid={pid}", pid)
        if len(seg) >= 3 and seg[0] == "share" and seg[1] in ("p", "v", "r"):
            return made(
                FACEBOOK,
                f"https://www.facebook.com/share/{seg[1]}/{seg[2]}",
                f"share-{seg[2]}",
                video=seg[1] in ("v", "r"),
            )
        if len(seg) >= 2 and seg[0] == "reel":
            return made(FACEBOOK, f"https://www.facebook.com/reel/{seg[1]}", seg[1], video=True)
        if len(seg) >= 4 and seg[0] == "groups" and seg[2] in ("posts", "permalink"):
            return made(
                FACEBOOK,
                f"https://www.facebook.com/groups/{seg[1]}/posts/{seg[3]}",
                seg[3],
                f"groups/{seg[1]}",
            )
        if len(seg) >= 3 and seg[1] in ("posts", "videos", "photos"):
            pid = seg[-1]
            return made(
                FACEBOOK,
                f"https://www.facebook.com/{seg[0]}/{seg[1]}/{pid}",
                pid,
                seg[0],
                video=seg[1] == "videos",
            )
        if len(seg) == 1:  # a page, not a post
            return made(FACEBOOK, f"https://www.facebook.com/{seg[0]}", None, seg[0])
        return made(FACEBOOK, f"https://www.facebook.com{path}")

    if host in ("youtube.com", "youtu.be", "youtube-nocookie.com", "music.youtube.com"):
        vid = None
        if host == "youtu.be" and seg:
            vid = seg[0]
        elif path == "/watch":
            vid = q("v")
        elif len(seg) >= 2 and seg[0] in ("shorts", "live", "embed", "v"):
            vid = seg[1]
        if vid:
            return made(YOUTUBE, f"https://www.youtube.com/watch?v={vid}", vid)
        account = seg[0] if seg and seg[0].startswith("@") else None
        return made(YOUTUBE, f"https://www.youtube.com{path}", None, account)

    if host in ("x.com", "twitter.com", "mobile.twitter.com"):
        if len(seg) >= 3 and seg[1] == "status":
            return made(X, f"https://x.com/{seg[0]}/status/{seg[2]}", seg[2], "@" + seg[0])
        return made(X, f"https://x.com{path}", None, "@" + seg[0] if seg else None)

    if host in ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com"):
        if len(seg) >= 3 and seg[0].startswith("@") and seg[1] == "video":
            return made(TIKTOK, f"https://www.tiktok.com/{seg[0]}/video/{seg[2]}", seg[2], seg[0])
        if seg and host != "tiktok.com":
            return made(TIKTOK, f"https://{host}/{seg[0]}", f"short-{seg[0]}")
        return made(TIKTOK, f"https://www.tiktok.com{path}")

    if host == "instagram.com":
        if len(seg) >= 2 and seg[0] in ("p", "reel", "tv"):
            return made(
                INSTAGRAM,
                f"https://www.instagram.com/{seg[0]}/{seg[1]}",
                seg[1],
                video=seg[0] != "p",
            )
        return made(
            INSTAGRAM, f"https://www.instagram.com{path}", None, "@" + seg[0] if seg else None
        )

    if host in ("t.me", "telegram.me"):
        if len(seg) >= 2 and seg[1].isdigit():
            return made(TELEGRAM, f"https://t.me/{seg[0]}/{seg[1]}", f"{seg[0]}/{seg[1]}", seg[0])
        return made(TELEGRAM, f"https://t.me{path}", None, seg[0] if seg else None)

    # Any other website: keep the path and the meaningful query (an article id).
    query_kept = _clean_query(parts.query)
    canonical = urlunsplit(("https", host, path, query_kept, ""))
    return made(WEB, canonical)
