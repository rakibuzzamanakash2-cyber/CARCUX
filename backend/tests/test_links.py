"""Links analysts paste (Facebook, YouTube, X, news sites …): read from the URL only,
one source per account, one signal per post, exported as links and labels only."""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.signal import Source, SourceType
from app.models.user import Role
from app.services import dataset, links
from tests.test_assessment import _event
from tests.test_assessment import people as people  # noqa: F401 (fixture)

DATA_TOOLS = Path(__file__).resolve().parents[2] / "data" / "tools"
sys.path.insert(0, str(DATA_TOOLS))
from carcux_data.validate import validate_dir  # noqa: E402

URL = "/api/v1/signals/links"
POSTED = datetime(2026, 10, 15, 9, 30, tzinfo=UTC).isoformat()
POST = "https://www.facebook.com/DhakaUpdates/posts/pfbid0abc123?mibextid=xyz&fbclid=IwAR1"
RUMOUR = "Tejgaon e building dhoshe porse, onek manush atka, 5 jon mara geche"


# --- Reading links -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "platform", "post_id", "account", "video"),
    [
        (POST, "facebook", "pfbid0abc123", "DhakaUpdates", False),
        ("https://m.facebook.com/story.php?story_fbid=123&id=456", "facebook", "123", "456", False),
        ("https://www.facebook.com/share/p/1AbCdEf/", "facebook", "share-1AbCdEf", None, False),
        ("https://fb.watch/qWeRtY/?mibextid=1", "facebook", "watch-qWeRtY", None, True),
        ("https://www.facebook.com/groups/dhakaflood/permalink/555/", "facebook", "555",
         "groups/dhakaflood", False),
        ("https://youtu.be/dQw4w9WgXcQ?si=abc", "youtube", "dQw4w9WgXcQ", None, True),
        ("https://youtube.com/shorts/abc123?feature=share", "youtube", "abc123", None, True),
        ("https://x.com/somchannel/status/179?s=20", "x", "179", "@somchannel", False),
        ("https://www.tiktok.com/@user/video/730?lang=en", "tiktok", "730", "@user", True),
        ("https://www.instagram.com/reel/Cx1/", "instagram", "Cx1", None, True),
        ("t.me/somoytv/4567", "telegram", "somoytv/4567", "somoytv", False),
        ("https://www.thedailystar.net/news/x-1?utm_source=fb", "web", None, None, False),
    ],
)  # fmt: skip
def test_reading_links(url, platform, post_id, account, video):
    link = links.parse(url)
    assert (link.platform.key, link.post_id, link.account, link.video) == (
        platform, post_id, account, video,
    )  # fmt: skip
    assert "fbclid" not in link.url and "utm_" not in link.url and "si=" not in link.url


def test_the_same_post_reads_the_same_however_it_was_shared():
    a = links.parse("https://youtu.be/dQw4w9WgXcQ?si=1")
    b = links.parse("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=30s")
    assert a.external_id == b.external_id == "youtube:dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url", ["hello", "ftp://x.org/a", "javascript:alert(1)", "https://localhost/x"]
)
def test_not_links(url):
    with pytest.raises(links.BadLinkError):
        links.parse(url)


# --- Adding them -------------------------------------------------------------------------------


def _add(client, people, **body):
    payload = {"url": POST, "text": RUMOUR, "published_at": POSTED, **body}
    return client.post(URL, json=payload, headers=people["analyst_headers"])


def test_a_facebook_post_becomes_a_signal_of_its_page(client, db, people):
    r = _add(client, people, event_type="building_collapse", district="Dhaka")
    assert r.status_code == 201, r.text
    body = r.json()
    s = body["signal"]
    assert body["created"] is True
    assert s["source"]["name"] == "DhakaUpdates · Facebook"
    assert s["source"]["source_type"] == "social"
    assert s["url"] == "https://www.facebook.com/DhakaUpdates/posts/pfbid0abc123"
    assert s["language"] == "bn-Latn" and s["district"] == "Dhaka"
    assert ("casualty_count", 5) in {(d["attribute"], d["value"]) for d in s["details"]}

    # The same post again, shared with other tracking: the same signal.
    again = _add(client, people, url=POST.split("?")[0] + "?fbclid=other")
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["signal"]["id"] == s["id"]

    # Another post by the same page: the same source, so one track record.
    other = _add(client, people, url="https://www.facebook.com/DhakaUpdates/posts/pfbid0zzz")
    assert other.json()["signal"]["source"]["id"] == s["source"]["id"]


def test_the_page_name_is_needed_when_the_link_does_not_show_it(client, people):
    share = "https://www.facebook.com/share/p/1AbCdEf/"
    r = _add(client, people, url=share)
    assert r.status_code == 422 and "page or account" in r.json()["detail"]
    r = _add(client, people, url=share, account="Amar Shohor")
    assert r.status_code == 201
    assert r.json()["signal"]["source"]["name"] == "Amar Shohor · Facebook"


def test_youtube_and_news_sites(client, db, people):
    r = _add(client, people, url="https://youtu.be/dQw4w9WgXcQ", account="Somoy TV")
    assert r.json()["signal"]["source"]["source_type"] == "video_platform"
    # A known newspaper: filed under its feed's source, not a new one.
    r = _add(
        client, people, url="https://www.thedailystar.net/news/bangladesh/flood-123?utm_source=fb"
    )
    assert r.json()["signal"]["source"]["key"] == "dailystar"
    # An unknown website: a new publisher, of the kind the analyst says.
    r = _add(client, people, url="https://dncc.gov.bd/notice/77", kind="public_record")
    assert r.json()["signal"]["source"]["source_type"] == "public_record"


def test_preview_says_what_the_link_is_and_whether_it_is_known(client, people):
    h = people["analyst_headers"]
    p = client.get(f"{URL}/preview", params={"url": POST}, headers=h).json()
    assert (p["platform"], p["account"], p["existing_signal_id"], p["known_source"]) == (
        "facebook", "DhakaUpdates", None, None,
    )  # fmt: skip
    created = _add(client, people).json()["signal"]
    p = client.get(f"{URL}/preview", params={"url": POST}, headers=h).json()
    assert p["existing_signal_id"] == created["id"]
    assert p["known_source"] == "DhakaUpdates · Facebook"
    bad = client.get(f"{URL}/preview", params={"url": "nonsense"}, headers=h)
    assert bad.status_code == 422


def test_adding_straight_to_an_event(client, db, people):
    e = _event(db, people["analyst"])
    db.commit()
    r = _add(client, people, event_id=str(e.id), relation="supports")
    assert r.status_code == 201 and r.json()["evidence_id"]
    again = _add(client, people, event_id=str(e.id), relation="supports")
    assert again.json()["already_linked"] is True and again.json()["evidence_id"] is None
    evidence = client.get(
        f"/api/v1/events/{e.id}/evidence", headers=people["analyst_headers"]
    ).json()
    assert len(evidence) == 1 and evidence[0]["signal"]["source"]["source_type"] == "social"
    half = _add(client, people, event_id=str(e.id))
    assert half.status_code == 422


def test_only_analysts_and_admins(client, make_user, login):
    make_user("worker@office.local", Role.FIELD_WORKER)
    h = login("worker@office.local")
    r = client.post(URL, json={"url": POST, "text": RUMOUR, "published_at": POSTED}, headers=h)
    assert r.status_code == 403


def test_export_keeps_posts_as_links_and_accounts_unnamed(client, db, people, tmp_path):
    e = _event(db, people["analyst"], occurred=False)
    later = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    e.ground_truth_sources = [
        {"reference": "https://example.org/x", "kind": "news_followup", "published_at": later}
    ]
    db.commit()
    _add(client, people, event_id=str(e.id), relation="supports")
    yt = "https://youtu.be/dQw4w9WgXcQ"
    _add(client, people, url=yt, account="Somoy TV", event_id=str(e.id), relation="contradicts")
    db.expire_all()
    export = dataset.build(db, now=datetime.now(UTC) + timedelta(days=8))
    for name, rows in export.files.items():
        (tmp_path / name).write_text(dataset.write_jsonl(rows), encoding="utf-8")
    result = validate_dir(tmp_path)
    assert result.ok, result.errors
    obs = export.files["observations.jsonl"]
    assert {o["content_policy"] for o in obs} == {"reference_only"}
    assert all("text" not in o for o in obs)
    assert all("surface" not in c for o in obs for c in o["claims"])
    assert {o["modality"] for o in obs} == {"text", "video"}
    srcs = export.files["sources.jsonl"]
    assert {(s["name"], s["platform"]) for s in srcs} == {
        ("Facebook account", "facebook"), ("YouTube account", "youtube"),
    }  # fmt: skip
    assert all(len(s["account_ref"]) == 64 and "domain" not in s for s in srcs)
    # Named nowhere but in the post's own link (how posts are shared, by reference).
    without_links = str([{k: v for k, v in o.items() if k != "reference"} for o in obs]) + str(srcs)
    assert "DhakaUpdates" not in without_links and "Somoy" not in str(export.files)
    assert "links" in export.manifest["social_media"]
    assert db.scalar(select(Source).where(Source.source_type == SourceType.SOCIAL))
