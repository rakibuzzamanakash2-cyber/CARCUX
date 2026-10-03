"""Backfilling past periods from archives, and importing lists of past news items."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ingest import gdacs_archive, reliefweb, runner
from app.ingest.base import Request
from app.models.audit import AuditLog
from app.models.signal import Signal, Source
from app.models.user import Role
from app.services.audit import AuditAction

FIXTURES = Path(__file__).parent / "fixtures"
SOURCES = "/api/v1/sources"


def source(db, key: str) -> Source:
    return db.scalar(select(Source).where(Source.key == key))


@pytest.fixture
def analyst(make_user, login):
    make_user("analyst@office.local", Role.ANALYST)
    return login("analyst@office.local")


def paging(first: bytes, empty: bytes = b'{"features": []}'):
    """First page from a fixture, then nothing; remembers what was asked."""
    seen: list[Request] = []

    def _fetch(request: Request) -> bytes:
        seen.append(request)
        return first if len(seen) == 1 else empty

    _fetch.seen = seen
    return _fetch


# --- GDACS archive -----------------------------------------------------------------------


def test_gdacs_archive_keeps_bangladesh_floods_and_cyclones(db):
    parsed = gdacs_archive.parse(
        (FIXTURES / "gdacs_archive.json").read_bytes(), source(db, "gdacs")
    )
    assert (parsed.fetched, parsed.skipped) == (4, 2)  # Thailand flood; drought
    flood, remal = parsed.items
    assert (flood.external_id, flood.event_type, flood.severity) == ("FL1102990", "flood", "severe")
    assert flood.place_name == "Feni"  # named first in the description
    assert flood.url.startswith("https://www.gdacs.org/report.aspx")
    assert flood.published_at == datetime(2024, 8, 20, tzinfo=UTC)
    assert flood.valid_until == datetime(2024, 9, 4, tzinfo=UTC)
    assert 50_000 < flood.precision_m < 100_000
    assert (remal.external_id, remal.event_type, remal.severity) == (
        "TC1000990",
        "cyclone",
        "moderate",
    )
    assert remal.precision_m == 300_000  # capped


def test_backfill_reads_pages_and_records_the_period(db, settings):
    gdacs = source(db, "gdacs")
    fetch = paging((FIXTURES / "gdacs_archive.json").read_bytes())
    run = runner.backfill(db, gdacs, settings, date(2024, 5, 1), date(2024, 9, 30), fetcher=fetch)

    assert (run.ok, run.fetched, run.created, run.skipped) == (True, 4, 2, 2)
    assert (run.window_start, run.window_end) == (date(2024, 5, 1), date(2024, 9, 30))
    assert len(fetch.seen) == 1  # fewer than a full page: no need for page 2
    params = fetch.seen[0].params
    assert (params["fromdate"], params["todate"], params["pagenumber"]) == (
        "2024-05-01", "2024-09-30", "1",
    )  # fmt: skip
    assert gdacs.last_run_at is None  # the live schedule is not disturbed

    fetch = paging((FIXTURES / "gdacs_archive.json").read_bytes())
    again = runner.backfill(db, gdacs, settings, date(2024, 5, 1), date(2024, 9, 30), fetcher=fetch)
    assert (again.created, again.updated) == (0, 0)


def test_backfill_follows_full_pages(db, settings, monkeypatch):
    monkeypatch.setattr(gdacs_archive, "PAGE_SIZE", 4)  # the fixture is a "full" page
    fetch = paging((FIXTURES / "gdacs_archive.json").read_bytes())
    run = runner.backfill(db, source(db, "gdacs"), settings, date(2024, 5, 1), date(2024, 9, 30),
                          fetcher=fetch)  # fmt: skip
    assert [r.params["pagenumber"] for r in fetch.seen] == ["1", "2"]
    assert run.ok and run.fetched == 4


def test_backfill_refuses_odd_periods_and_sources(db, settings):
    gdacs = source(db, "gdacs")
    for start, end in (
        (date(2024, 9, 1), date(2024, 8, 1)),  # end before start
        (date(2023, 1, 1), date(2024, 6, 1)),  # longer than a year
        (date(2099, 1, 1), date(2099, 2, 1)),  # future
    ):
        with pytest.raises(runner.BadWindowError):
            runner.backfill(db, gdacs, settings, start, end, fetcher=paging(b"{}"))
    with pytest.raises(runner.NoArchiveError):
        runner.backfill(db, source(db, "dailystar"), settings, date(2024, 8, 1), date(2024, 8, 9))


def test_reliefweb_pages_by_original_date(db, settings):
    rw = source(db, "reliefweb")
    named = settings.model_copy(update={"reliefweb_appname": "carcux-test"})
    first, second = list(reliefweb.pages(rw, named, date(2024, 8, 15), date(2024, 9, 10)))[:2]
    condition = first.json["filter"]["conditions"][1]
    assert condition["field"] == "date.original"
    assert condition["value"]["from"].startswith("2024-08-15")
    assert (first.json["offset"], second.json["offset"]) == (0, reliefweb.PAGE_SIZE)
    run = runner.backfill(db, rw, settings, date(2024, 8, 15), date(2024, 9, 10),
                          fetcher=paging(b"{}"))  # fmt: skip
    assert not run.ok and "RELIEFWEB_APPNAME" in run.error


def test_backfill_api_is_for_admins(client, admin_headers, analyst, db, monkeypatch):
    monkeypatch.setattr(
        runner, "default_fetcher",
        lambda _s: paging((FIXTURES / "gdacs_archive.json").read_bytes()),
    )  # fmt: skip
    gid = str(source(db, "gdacs").id)
    body = {"start": "2024-05-01", "end": "2024-09-30"}
    assert client.post(f"{SOURCES}/{gid}/backfill", json=body, headers=analyst).status_code == 403
    run = client.post(f"{SOURCES}/{gid}/backfill", json=body, headers=admin_headers)
    assert run.status_code == 200, run.text
    assert (run.json()["created"], run.json()["window_start"]) == (2, "2024-05-01")
    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.SOURCE_BACKFILLED))
    assert entry.details["start"] == "2024-05-01"

    star = str(source(db, "dailystar").id)
    no_archive = client.post(f"{SOURCES}/{star}/backfill", json=body, headers=admin_headers)
    assert no_archive.status_code == 422 and "import a list" in no_archive.text
    too_long = {"start": "2022-01-01", "end": "2024-01-01"}
    long = client.post(f"{SOURCES}/{gid}/backfill", json=too_long, headers=admin_headers)
    assert long.status_code == 422


# --- Importing a list ----------------------------------------------------------------------


def upload(client, headers, data: bytes, dry_run: bool):
    return client.post(
        "/api/v1/signals/import",
        params={"dry_run": str(dry_run).lower()},
        files={"file": ("list.csv", data, "text/csv")},
        headers=headers,
    )


def test_checking_a_list_saves_nothing(client, analyst, db):
    result = upload(client, analyst, (FIXTURES / "archive_list.csv").read_bytes(), True)
    assert result.status_code == 200, result.text
    body = result.json()
    assert (body["dry_run"], body["added"], body["duplicates"], body["errors"]) == (True, 4, 0, 4)
    rows = {r["line"]: r for r in body["rows"]}
    assert (rows[2]["event_type"], rows[2]["place"]) == ("flood", "Feni")
    assert (rows[3]["event_type"], rows[3]["place"]) == ("cyclone", "Mongla")
    assert (rows[4]["event_type"], rows[4]["place"]) == ("flood", "Noakhali")
    assert (rows[5]["event_type"], rows[5]["place"]) == ("rail_accident", "Bhairab")
    assert "event type" in rows[6]["message"]
    assert "http" in rows[7]["message"]
    assert "date" in rows[8]["message"]
    assert "Atlantis" in rows[9]["message"]
    assert db.scalar(select(Signal.id)) is None
    assert source(db, "bdnews24-com") is None  # new publishers only on import


def test_importing_a_list(client, analyst, db):
    data = (FIXTURES / "archive_list.csv").read_bytes()
    body = upload(client, analyst, data, False).json()
    assert body["added"] == 4
    assert body["new_publishers"] == ["bdnews24.com"]  # rows with errors add nothing
    remal = db.scalar(select(Signal).where(Signal.url.like("%remal-landfall")))
    assert (remal.source.key, remal.severity) == ("prothomalo-en", "severe")  # matched by name
    assert remal.published_at == datetime(2024, 5, 26, 15, 0, tzinfo=UTC)
    assert remal.extraction["method"] == "imported list"
    star = db.scalar(select(Signal).where(Signal.url.like("%flood-feni-2024")))
    assert star.source.key == "dailystar" and star.extraction["matched"][0] == "flood"
    bn = db.scalar(select(Signal).where(Signal.url.like("%noakhali-bonna")))
    assert (bn.language, bn.source.key) == ("bn", "prothomalo-bn")
    train = db.scalar(select(Signal).where(Signal.url.like("%bhairab-train")))
    assert train.source.adapter == "manual" and train.source.domain == "bdnews24.com"

    again = upload(client, analyst, data, False).json()
    assert (again["added"], again["duplicates"]) == (0, 4)
    entry = db.scalar(
        select(AuditLog)
        .where(AuditLog.action == AuditAction.SIGNALS_IMPORTED)
        .order_by(AuditLog.id)
    )
    assert entry.details["added"] == 4


def test_unreadable_files_are_refused(client, analyst, make_user, login):
    no_cols = upload(client, analyst, b"link,headline\nhttps://x.y,Flood\n", True)
    assert no_cols.status_code == 422 and "Missing column" in no_cols.text
    latin1 = "url,title,published,publisher\nhttps://x.y,Flood in Feni \xe9,2024-08-01,X\n"
    assert upload(client, analyst, latin1.encode("latin-1"), True).status_code == 422
    make_user("viewer@office.local", Role.VIEWER)
    viewer = login("viewer@office.local")
    assert upload(client, viewer, b"url,title,published,publisher\n", True).status_code == 403


def test_imported_signals_export_like_live_ones(client, analyst, db):
    """They carry an excerpt and a place, and match events like any other signal."""
    upload(client, analyst, (FIXTURES / "archive_list.csv").read_bytes(), False)
    feni = db.scalar(select(Signal).where(Signal.url.like("%flood-feni-2024")))
    assert len(feni.text) <= 300 and feni.latitude is not None
    assert json.loads(json.dumps(feni.extraction))["place_level"] == "district"  # headline
