"""Public signals: parsing each source format, storing runs, manual bulletins, triage,
linking signals to events, and managing sources."""

import json
import re
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ingest import gdacs, reliefweb, rss, runner
from app.ingest.base import FetchError, Request, _check_url, excerpt, parse_date
from app.ingest.classify import classify
from app.ingest.places import best_place
from app.models.audit import AuditLog
from app.models.signal import IngestRun, Signal, SignalStatus, Source
from app.models.user import Role
from app.services.audit import AuditAction
from tests.test_events import MIRPUR, NOW, create

# The feed samples were saved on 3 October 2026; read them as if it were that day.
SAMPLE_DAY = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)

FIXTURES = Path(__file__).parent / "fixtures"
SIGNALS = "/api/v1/signals"
SOURCES = "/api/v1/sources"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def source(db, key: str) -> Source:
    return db.scalar(select(Source).where(Source.key == key))


def fresh_news() -> bytes:
    """The news sample with its dates moved to the last few hours, so it stays current."""
    body = fixture("news.xml").decode()
    for hours, date in enumerate(re.findall(r"<pubDate>(.*?)</pubDate>", body), start=1):
        body = body.replace(date, format_datetime(datetime.now(UTC) - timedelta(hours=hours)), 1)
    return body.encode()


def serving(body: bytes):
    """A fetcher that answers every request with `body`."""
    seen: list[Request] = []

    def _fetch(request: Request) -> bytes:
        seen.append(request)
        return body

    _fetch.seen = seen
    return _fetch


@pytest.fixture
def analyst(make_user, login):
    make_user("analyst@office.local", Role.ANALYST, full_name="Ana Analyst")
    return login("analyst@office.local")


@pytest.fixture
def viewer(make_user, login):
    make_user("viewer@office.local", Role.VIEWER)
    return login("viewer@office.local")


# --- Places and keywords ---------------------------------------------------------------


def test_places_prefer_the_most_specific_and_read_bangla():
    assert best_place("Waterlogging in Mirpur 10 after rain in Dhaka").name == "Mirpur"
    assert best_place("Flood in Kurigram's Chilmari").level == "upazila"
    place = best_place("সুনামগঞ্জে বন্যা")  # case ending on the district name
    assert (place.name, place.division) == ("Sunamganj", "Sylhet")
    assert best_place("Chittagong port").name == "Chattogram"  # old spelling
    assert best_place("Flood kills 30 in Pakistan's Sindh") is None
    # Several districts named: anchored on the first, widened to cover the rest.
    ports = best_place("Ports of Chattogram, Cox's Bazar and Mongla hoist signal 7")
    assert ports.name == "Chattogram" and ports.precision_m > 200_000


def test_keywords_are_strict_about_ordinary_words():
    assert classify("Ceasefire talks resume") is None
    assert classify("Minister fired over scandal") is None
    assert classify("Blast furnace reopens") is None
    assert classify("Flash flood hits Sunamganj").event_type == "flash_flood"
    assert classify("ঢাকায় জলাবদ্ধতা").event_type == "waterlogging"
    # One mention in a summary is not enough; two are.
    assert classify("City news", "a flood of complaints") is None
    assert (
        classify("City news", "Flood waters rose; flooding in three unions").event_type == "flood"
    )


def test_excerpt_and_dates():
    long = "word " * 100
    cut = excerpt(long)
    assert len(cut) <= 300 and cut.endswith("…")
    assert parse_date("Fri, 02 Oct 26 22:00:00 +0600") == datetime(2026, 10, 2, 16, 0, tzinfo=UTC)
    assert parse_date("2026-10-03T09:00:00+06:00").hour == 9
    assert parse_date("not a date") is None


# --- Parsers ---------------------------------------------------------------------------


def test_gdacs_keeps_bangladesh_floods_and_cyclones(db):
    parsed = gdacs.parse(fixture("gdacs.xml"), source(db, "gdacs"))

    assert (parsed.fetched, parsed.skipped) == (4, 2)  # Thailand flood, drought left out
    flood, cyclone = parsed.items
    assert (flood.external_id, flood.event_type, flood.severity) == (
        "FL1104200",
        "flood",
        "moderate",
    )
    assert flood.place_name == "Sunamganj"  # named in the description
    assert (flood.latitude, flood.longitude) == (24.95, 91.40)
    assert 50_000 < flood.precision_m < 80_000  # half the bounding box diagonal
    assert flood.valid_from == datetime(2026, 10, 1, tzinfo=UTC)
    assert flood.extraction["credit"] == "GDACS (CC BY 4.0)"
    assert (cyclone.event_type, cyclone.severity) == ("cyclone", "severe")
    assert cyclone.precision_m == gdacs.MAX_PRECISION_M


def test_news_feed_keeps_placeable_disaster_items_as_excerpts(db):
    parsed = rss.parse(fixture("news.xml"), source(db, "prothomalo-en"), now=SAMPLE_DAY)

    assert (parsed.fetched, parsed.skipped) == (4, 2)  # mobile story; Pakistan flood
    water, slide = parsed.items
    assert (water.event_type, water.place_name, water.precision_m) == (
        "waterlogging",
        "Mirpur",
        2_500,
    )
    assert water.text.startswith("Several roads in Mirpur 10")
    assert len(water.text) <= 300 and water.text.endswith("…")  # never the article
    assert water.extraction["matched"] == ["waterlogging"]
    assert slide.title == "Landslide in Cox's Bazar camp kills two"  # markup removed
    assert (slide.event_type, slide.district) == ("landslide", "Cox's Bazar")
    assert slide.published_at == datetime(2026, 10, 2, 16, 0, tzinfo=UTC)


def test_old_news_is_left_out(db):
    """Some feed addresses redirect to archives that stopped years ago."""
    src = source(db, "prothomalo-en")
    month_later = rss.parse(fixture("news.xml"), src, now=SAMPLE_DAY + timedelta(days=30))
    assert (month_later.fetched, month_later.items) == (4, [])


def test_atom_feed_in_bangla(db):
    src = source(db, "prothomalo-bn")
    parsed = rss.parse(fixture("news_bn.atom"), src, now=SAMPLE_DAY)

    assert (parsed.fetched, len(parsed.items)) == (2, 1)
    (item,) = parsed.items
    assert (item.event_type, item.place_name, item.language) == ("flood", "Sunamganj", "bn")
    assert item.url == "https://example.bn/sunamganj-flood"


def test_reliefweb_needs_an_app_name_and_reads_bulletins(db, settings):
    src = source(db, "reliefweb")
    with pytest.raises(ValueError, match="RELIEFWEB_APPNAME"):
        reliefweb.request(src, settings)
    req = reliefweb.request(src, settings.model_copy(update={"reliefweb_appname": "carcux-test"}))
    assert (req.method, req.params) == ("POST", {"appname": "carcux-test"})

    parsed = reliefweb.parse(fixture("reliefweb.json"), src)
    (item,) = parsed.items  # the annual report is not about a disruption
    assert (item.event_type, item.place_name) == ("cyclone", "Chattogram")
    assert item.precision_m > 200_000  # the bulletin covers four ports
    assert item.extraction["publishers"] == ["BMD"]


# --- Runs ------------------------------------------------------------------------------


def test_run_stores_new_items_once_and_updates_changed_ones(db, settings):
    src = source(db, "gdacs")
    run = runner.run_source(db, src, settings, fetcher=serving(fixture("gdacs.xml")))
    assert (run.ok, run.fetched, run.created, run.updated, run.skipped) == (True, 4, 2, 0, 2)
    assert src.last_success_at is not None and src.last_error is None

    again = runner.run_source(db, src, settings, fetcher=serving(fixture("gdacs.xml")))
    assert (again.created, again.updated) == (0, 0)

    # The analyst reviews the flood; then GDACS raises it to red.
    flood = db.scalar(select(Signal).where(Signal.external_id == "FL1104200"))
    flood.status = SignalStatus.REVIEWED
    db.commit()
    raised = fixture("gdacs.xml").replace(b"<gdacs:alertlevel>Orange", b"<gdacs:alertlevel>Red")
    third = runner.run_source(db, src, settings, fetcher=serving(raised))
    assert (third.created, third.updated) == (0, 1)
    db.refresh(flood)
    assert (flood.severity, flood.status) == ("severe", SignalStatus.REVIEWED)
    assert db.query(Signal).count() == 2


def test_run_records_failures_without_raising(db, settings):
    src = source(db, "prothomalo-en")

    def broken(_request):
        raise FetchError("The source answered HTTP 503")

    run = runner.run_source(db, src, settings, fetcher=broken)
    assert (run.ok, run.error) == (False, "The source answered HTTP 503")
    assert src.last_error == "The source answered HTTP 503" and src.last_run_at is not None

    garbage = runner.run_source(db, src, settings, fetcher=serving(b"<html><p>oops"))
    assert not garbage.ok and garbage.error.startswith("Could not read the response")

    with pytest.raises(runner.NotReadableError):
        runner.run_source(db, source(db, "bmd"), settings)


def test_due_sources_respect_interval_and_switches(db):
    keys = {s.key for s in runner.due_sources(db)}
    assert keys == {"gdacs", "prothomalo-en", "prothomalo-bn", "dailystar"}  # not manual, not off
    src = source(db, "gdacs")
    src.last_run_at = datetime.now(UTC) - timedelta(minutes=10)  # every 30 minutes
    db.commit()
    assert "gdacs" not in {s.key for s in runner.due_sources(db)}


def test_xml_bombs_are_refused(db, settings):
    bomb = b"""<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>
    <rss><channel><item><title>&b;</title></item></channel></rss>"""
    run = runner.run_source(db, source(db, "dailystar"), settings, fetcher=serving(bomb))
    assert not run.ok


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/feed",
        "http://127.0.0.1/feed",
        "http://localhost:8000/",
        "file:///etc/passwd",
    ],
)
def test_private_and_odd_addresses_are_refused(url):
    with pytest.raises(FetchError):
        _check_url(url, allow_private=False)


# --- API: reading and triage -------------------------------------------------------------


@pytest.fixture
def stored(db, settings):
    runner.run_source(db, source(db, "gdacs"), settings, fetcher=serving(fixture("gdacs.xml")))
    runner.run_source(db, source(db, "prothomalo-en"), settings, fetcher=serving(fresh_news()))
    return {s.external_id: str(s.id) for s in db.scalars(select(Signal))}


def test_everyone_signed_in_can_read_and_filter_signals(client, viewer, stored):
    page = client.get(SIGNALS, headers=viewer).json()
    assert page["total"] == 4
    assert page["items"][0]["source"]["key"] in {"gdacs", "prothomalo-en"}

    floods = client.get(SIGNALS, params={"event_type": "flood"}, headers=viewer).json()
    assert [i["external_id"] for i in floods["items"]] == ["FL1104200"]
    found = client.get(SIGNALS, params={"q": "Mirpur"}, headers=viewer).json()
    assert found["total"] == 1
    assert client.get(SIGNALS).status_code == 401
    assert client.get(SIGNALS, params={"family": "nope"}, headers=viewer).status_code == 422


def test_triage_needs_a_reason_to_dismiss(client, analyst, viewer, stored, db):
    sid = stored["a1"]
    url = f"{SIGNALS}/{sid}/review"
    assert client.post(url, json={"status": "dismissed"}, headers=analyst).status_code == 422
    assert client.post(url, json={"status": "reviewed"}, headers=viewer).status_code == 403

    done = client.post(url, json={"status": "dismissed", "note": "Old story"}, headers=analyst)
    assert done.status_code == 200
    assert (done.json()["status"], done.json()["review_note"]) == ("dismissed", "Old story")
    assert done.json()["reviewed_by"]["full_name"] == "Ana Analyst"
    back = client.post(url, json={"status": "new"}, headers=analyst).json()
    assert (back["status"], back["reviewed_by"]) == ("new", None)
    entries = db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.SIGNAL_REVIEWED))
    assert [e.details["to"] for e in entries] == ["dismissed", "new"]


def bulletin(db, **overrides) -> dict:
    body = {
        "source_id": str(source(db, "bmd").id),
        "title": "Special Weather Bulletin No. 4: heavy rainfall advisory",
        "text": "Heavy to very heavy rainfall is likely over Chattogram division.",
        "url": "https://bmd.gov.bd/bulletin/4",
        "event_type": "heavy_rainfall",
        "severity": "moderate",
        "published_at": NOW.isoformat(),
        "district": "Chittagong",
    }
    body.update(overrides)
    return {k: v for k, v in body.items() if v is not None}


def test_analyst_enters_a_bulletin_by_district(client, analyst, viewer, db):
    response = client.post(SIGNALS, json=bulletin(db), headers=analyst)
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["district"], body["place_name"], body["precision_m"]) == (
        "Chattogram",
        "Chattogram",
        30_000,
    )
    assert (body["content_policy"], body["entered_by"]["full_name"]) == ("full", "Ana Analyst")
    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.SIGNAL_ENTERED))
    assert entry.target_id == body["id"] and entry.details["source"] == "bmd"

    assert client.post(SIGNALS, json=bulletin(db), headers=viewer).status_code == 403
    gdacs_src = str(source(db, "gdacs").id)
    wrong = client.post(SIGNALS, json=bulletin(db, source_id=gdacs_src), headers=analyst)
    assert wrong.status_code == 422 and "read automatically" in wrong.text
    nowhere = client.post(SIGNALS, json=bulletin(db, district=None), headers=analyst)
    assert nowhere.status_code == 422
    atlantis = client.post(SIGNALS, json=bulletin(db, district="Atlantis"), headers=analyst)
    assert atlantis.status_code == 422 and "Unknown district" in atlantis.text
    bad_url = client.post(SIGNALS, json=bulletin(db, url="javascript:alert(1)"), headers=analyst)
    assert bad_url.status_code == 422


def test_districts_for_the_picker(client, viewer):
    districts = client.get("/api/v1/places/districts", headers=viewer).json()
    assert len(districts) == 64
    assert {"name": "Sunamganj", "division": "Sylhet"}.items() <= next(
        d for d in districts if d["name"] == "Sunamganj"
    ).items()


# --- Signals as evidence -----------------------------------------------------------------


def test_signal_links_to_an_event_and_counts_as_evidence(client, analyst, stored, db):
    event = create(client, analyst).json()  # waterlogging at Mirpur 10
    sid = stored["a1"]  # "Waterlogging cripples Mirpur after heavy rain"

    suggested = client.get(f"/api/v1/events/{event['id']}/candidate-signals", headers=analyst)
    assert [c["signal"]["id"] for c in suggested.json()][:1] == [sid]
    assert suggested.json()[0]["same_type"] is True
    back = client.get(f"{SIGNALS}/{sid}/candidate-events", headers=analyst).json()
    assert [c["event"]["id"] for c in back] == [event["id"]]

    url = f"/api/v1/events/{event['id']}/evidence"
    linked = client.post(url, json={"signal_id": sid, "relation": "supports"}, headers=analyst)
    assert linked.status_code == 201, linked.text
    assert linked.json()["signal"]["title"].startswith("Waterlogging cripples")
    assert linked.json()["field_report"] is None
    again = client.post(url, json={"signal_id": sid, "relation": "related"}, headers=analyst)
    assert again.status_code == 409 and "signal is already" in again.text

    counts = client.get(f"/api/v1/events/{event['id']}", headers=analyst).json()["evidence_counts"]
    assert (counts["supports"], counts["signals"], counts["reporters"]) == (1, 1, 0)
    assert client.get(f"{SIGNALS}/{sid}", headers=analyst).json()["status"] == "reviewed"
    links = client.get(f"{SIGNALS}/{sid}/events", headers=analyst).json()
    assert [(link["event"]["id"], link["relation"]) for link in links] == [
        (event["id"], "supports")
    ]
    # No longer suggested once linked.
    after = client.get(f"/api/v1/events/{event['id']}/candidate-signals", headers=analyst).json()
    assert sid not in [c["signal"]["id"] for c in after]

    evidence_id = linked.json()["id"]
    assert client.delete(f"{url}/{evidence_id}", headers=analyst).status_code == 204
    unlinked = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.EVIDENCE_UNLINKED))
    assert unlinked.details["signal_id"] == sid


def test_evidence_must_be_one_report_or_one_signal(client, analyst, stored):
    event = create(client, analyst).json()
    url = f"/api/v1/events/{event['id']}/evidence"
    both = {"signal_id": stored["a1"], "field_report_id": stored["a1"], "relation": "supports"}
    assert client.post(url, json=both, headers=analyst).status_code == 422
    assert client.post(url, json={"relation": "supports"}, headers=analyst).status_code == 422
    ghost = {"signal_id": "00000000-0000-0000-0000-000000000000", "relation": "supports"}
    missing = client.post(url, json=ghost, headers=analyst)
    assert missing.status_code == 422 and "Signal not found" in missing.text


def test_event_created_from_a_signal(client, analyst, stored):
    sid = stored["FL1104200"]
    response = create(
        client,
        analyst,
        title="Flooding in Sunamganj",
        event_type="flood",
        latitude=25.0658,
        longitude=91.395,
        signal_ids=[sid],
    )
    assert response.status_code == 201, response.text
    assert response.json()["evidence_counts"]["signals"] == 1


def test_far_or_old_signals_are_not_suggested(client, analyst, stored, db):
    # Far from Mirpur: the Cox's Bazar landslide is not suggested for a Mirpur event,
    # but the nationwide cyclone alert (300 km reach) is.
    event = create(client, analyst).json()
    ids = [
        c["signal"]["external_id"]
        for c in client.get(
            f"/api/v1/events/{event['id']}/candidate-signals", headers=analyst
        ).json()
    ]
    assert "a4" not in ids
    # An event from last month matches nothing published this week.
    old = create(
        client,
        analyst,
        title="Old waterlogging at Mirpur",
        started_at=(NOW - timedelta(days=30)).isoformat(),
        ended_at=(NOW - timedelta(days=29)).isoformat(),
        latitude=MIRPUR[0],
        longitude=MIRPUR[1],
    ).json()
    assert client.get(f"/api/v1/events/{old['id']}/candidate-signals", headers=analyst).json() == []


# --- Sources -----------------------------------------------------------------------------


def test_sources_list_with_counts_for_reviewers_only(client, analyst, viewer, stored):
    rows = {s["key"]: s for s in client.get(SOURCES, headers=analyst).json()}
    assert rows["gdacs"]["signal_count"] == 2 and rows["gdacs"]["last_success_at"]
    assert rows["bmd"]["adapter"] == "manual" and rows["reliefweb"]["enabled"] is False
    assert client.get(SOURCES, headers=viewer).status_code == 403


def test_admin_adds_a_feed_and_switches_sources(client, admin_headers, analyst, db):
    body = {"name": "Dhaka Tribune", "url": "https://www.dhakatribune.com/feed/rss.xml"}
    added = client.post(SOURCES, json=body, headers=admin_headers)
    assert added.status_code == 201, added.text
    assert (added.json()["key"], added.json()["domain"]) == ("dhaka-tribune", "dhakatribune.com")
    twin = client.post(SOURCES, json=body, headers=admin_headers).json()
    assert twin["key"] == "dhaka-tribune-2"
    assert client.post(SOURCES, json=body, headers=analyst).status_code == 403
    ftp = {"name": "Odd", "url": "ftp://example.com/feed"}
    assert client.post(SOURCES, json=ftp, headers=admin_headers).status_code == 422

    sid = added.json()["id"]
    off = client.patch(f"{SOURCES}/{sid}", json={"enabled": False}, headers=admin_headers)
    assert off.json()["enabled"] is False
    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.SOURCE_UPDATED))
    assert entry.details["changes"] == {"enabled": [True, False]}
    bmd = str(source(db, "bmd").id)
    manual = client.patch(f"{SOURCES}/{bmd}", json={"url": "https://x.y"}, headers=admin_headers)
    assert manual.status_code == 422


def test_fetch_now_is_for_admins_and_reports_the_run(
    client, admin_headers, analyst, db, monkeypatch
):
    monkeypatch.setattr(runner, "default_fetcher", lambda _s: serving(fixture("gdacs.xml")))
    gid = str(source(db, "gdacs").id)
    assert client.post(f"{SOURCES}/{gid}/fetch", headers=analyst).status_code == 403

    run = client.post(f"{SOURCES}/{gid}/fetch", headers=admin_headers)
    assert run.status_code == 200, run.text
    assert (run.json()["ok"], run.json()["created"]) == (True, 2)
    history = client.get(f"{SOURCES}/{gid}/runs", headers=analyst).json()
    assert [h["created"] for h in history] == [2]
    assert db.scalar(select(IngestRun.triggered_by_id)) is not None
    bmd = str(source(db, "bmd").id)
    assert client.post(f"{SOURCES}/{bmd}/fetch", headers=admin_headers).status_code == 422


def test_overview_counts_new_signals(client, analyst, stored):
    body = client.get("/api/v1/overview", headers=analyst).json()
    assert body["signals_24h"] >= 1
    assert body["unreviewed_signals"] == 4


def test_dataset_vocabulary_is_shared():
    """Signal languages and source types are the dataset's."""
    common = json.loads(
        (Path(__file__).resolve().parents[2] / "data/schema/v1/common.schema.json").read_text()
    )["$defs"]
    from app.models.signal import SourceType
    from app.schemas.signal import LANGUAGES

    assert set(LANGUAGES) == set(common["language"]["enum"])
    assert {t.value for t in SourceType} <= set(common["source_type"]["enum"])
