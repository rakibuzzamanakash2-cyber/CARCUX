"""Dataset fields on events and links, and the CARCUX-BD export, checked with the
dataset's own validator (data/tools)."""

import io
import json
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ingest import runner
from app.models.audit import AuditLog
from app.models.signal import Signal, Source
from app.models.user import Role
from app.services import dataset
from app.services.audit import AuditAction
from tests.test_events import NOW, create, report
from tests.test_field_reports import photo
from tests.test_signals import fresh_news, serving

DATA_TOOLS = Path(__file__).resolve().parents[2] / "data" / "tools"
sys.path.insert(0, str(DATA_TOOLS))
from carcux_data.validate import validate_dir  # noqa: E402

EVENTS = "/api/v1/events"
FOLLOWUP = {
    "reference": "https://example.org/followup/mirpur",
    "published_at": (NOW + timedelta(hours=8)).isoformat(),
    "kind": "news_followup",
}


@pytest.fixture
def analyst(make_user, login):
    make_user("analyst@office.local", Role.ANALYST, full_name="Ana Analyst")
    return login("analyst@office.local")


@pytest.fixture
def worker(make_user, login):
    make_user("worker@office.local", Role.FIELD_WORKER, full_name="Rahim Uddin")
    return login("worker@office.local")


def link(client, headers, event_id, **body):
    return client.post(f"{EVENTS}/{event_id}/evidence", json=body, headers=headers)


# --- Links: conflicts, stale, confidence ------------------------------------------------


def test_partly_supports_needs_what_it_gets_wrong(client, analyst, worker):
    event = create(client, analyst).json()
    r = report(client, worker)
    missing = link(
        client, analyst, event["id"], field_report_id=r["id"], relation="partially_supports"
    )
    assert missing.status_code == 422 and "what it gets wrong" in missing.text

    ok = link(client, analyst, event["id"], field_report_id=r["id"],
              relation="partially_supports", conflicts=["magnitude", "magnitude"], stale=True,
              confidence=3)  # fmt: skip
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert (body["conflicts"], body["stale"], body["confidence"]) == (["magnitude"], True, 3)

    url = f"{EVENTS}/{event['id']}/evidence/{body['id']}"
    related = client.patch(url, json={"relation": "related"}, headers=analyst)
    assert related.json()["conflicts"] == []  # cleared: related-only makes no claim
    back = client.patch(url, json={"relation": "partially_supports"}, headers=analyst)
    assert back.status_code == 422
    fixed = client.patch(
        url, json={"relation": "partially_supports", "conflicts": ["location"]}, headers=analyst
    )
    assert fixed.json()["conflicts"] == ["location"]
    assert client.patch(url, json={"confidence": 4}, headers=analyst).status_code == 422
    bad = link(client, analyst, event["id"], field_report_id=report(client, worker)["id"],
               relation="related", conflicts=["cause"])  # fmt: skip
    assert bad.status_code == 422


# --- Ground truth ---------------------------------------------------------------------


def test_ground_truth_is_recorded_and_audited(client, analyst, db):
    event = create(client, analyst).json()
    assert (event["occurred"], event["ground_truth_sources"]) == (None, [])
    url = f"{EVENTS}/{event['id']}"
    done = client.patch(
        url,
        json={"occurred": True, "ground_truth_sources": [FOLLOWUP], "ground_truth_note": "Ok"},
        headers=analyst,
    )
    assert done.status_code == 200, done.text
    assert done.json()["ground_truth_sources"][0]["kind"] == "news_followup"
    entry = db.scalar(
        select(AuditLog)
        .where(AuditLog.action == AuditAction.EVENT_UPDATED)
        .order_by(AuditLog.id.desc())
    )
    assert set(entry.details["changes"]) == {
        "occurred",
        "ground_truth_sources",
        "ground_truth_note",
    }

    cleared = client.patch(url, json={"occurred": None}, headers=analyst)
    assert cleared.json()["occurred"] is None
    for bad in (
        {**FOLLOWUP, "reference": "not a url"},
        {**FOLLOWUP, "published_at": "2026-10-03T10:00:00"},
        {**FOLLOWUP, "kind": "rumour"},
    ):
        response = client.patch(url, json={"ground_truth_sources": [bad]}, headers=analyst)
        assert response.status_code == 422, bad


# --- Export -----------------------------------------------------------------------------


@pytest.fixture
def scenario(client, analyst, worker, db, settings):
    """One complete event (report + news item + reused photo), one without ground truth,
    and one partly-supporting link that has since lost its conflicts."""
    first = report(client, worker, text="Mirpur 10 e hatu pani, rasta bondho. Call 01712345678",
                   photos=[photo(1)])  # fmt: skip
    copy = report(client, worker, text="Same place, water still there", photos=[photo(1)])
    runner.run_source(db, db.scalar(select(Source).where(Source.key == "prothomalo-en")),
                      settings, fetcher=serving(fresh_news()))  # fmt: skip
    news = db.scalar(select(Signal).where(Signal.external_id == "a1"))

    event = create(client, analyst, assessment="unverified").json()
    eid = event["id"]
    assert link(client, analyst, eid, field_report_id=first["id"], relation="supports",
                confidence=3).status_code == 201  # fmt: skip
    assert link(client, analyst, eid, field_report_id=copy["id"], relation="partially_supports",
                conflicts=["status"], stale=True).status_code == 201  # fmt: skip
    assert (
        link(client, analyst, eid, signal_id=str(news.id), relation="supports").status_code == 201
    )
    client.patch(f"{EVENTS}/{eid}", json={"assessment": "verified"}, headers=analyst)
    client.patch(
        f"{EVENTS}/{eid}",
        json={"occurred": True, "ground_truth_sources": [FOLLOWUP]},
        headers=analyst,
    )

    pending = create(client, analyst, title="Fire at Gazipur factory", event_type="fire",
                     latitude=24.0023, longitude=90.4264).json()  # fmt: skip
    broken = link(client, analyst, pending["id"], field_report_id=first["id"],
                  relation="partially_supports", conflicts=["location"]).json()  # fmt: skip
    db.execute(
        __import__("sqlalchemy").text("UPDATE event_evidence SET conflicts='[]' WHERE id=:i"),
        {"i": broken["id"]},
    )
    db.commit()
    return {"event": eid, "pending": pending["id"], "first": first["id"], "copy": copy["id"]}


def write(export: dataset.Export, directory: Path) -> Path:
    for name, rows in export.files.items():
        (directory / name).write_text(dataset.write_jsonl(rows), encoding="utf-8")
    return directory


def test_export_is_a_valid_carcux_bd_dataset(scenario, db, tmp_path):
    export = dataset.build(db, now=datetime.now(UTC) + timedelta(days=2))
    result = validate_dir(write(export, tmp_path))
    assert result.ok, result.errors

    files = export.files
    assert export.manifest["counts"] == {
        "events.jsonl": 1,
        "sources.jsonl": 2,  # Prothom Alo English, one field worker
        "observations.jsonl": 3,
        "relations.jsonl": 3,
        "dependences.jsonl": 1,
    }
    (event,) = files["events.jsonl"]
    assert event["event_id"] == "EVT-000001"
    assert event["ground_truth"]["occurred"] is True
    assert [a["checkpoint"] for a in event["assessments"]] == ["T+1h", "T+6h", "T+24h", "final"]
    assert event["assessments"][-1]["label"] == "verified"
    assert event["location"]["admin"] == {
        "division": "Dhaka",
        "district": "Dhaka",
        "locality": "Mirpur 10 golchottor",
    }

    obs = {o["obs_id"]: o for o in files["observations.jsonl"]}
    reports = [o for o in obs.values() if o["reference"].startswith("carcux:field_report:")]
    assert "[PHONE]" in reports[0]["text"] and "01712345678" not in reports[0]["text"]
    assert reports[0]["language"] == "bn-Latn"
    assert reports[0]["location_mentions"][0]["from_gps"] is True
    assert len(reports[0]["media"][0]["phash"]) == 16
    news = next(o for o in obs.values() if o["reference"].startswith("https://"))
    assert news["content_policy"] == "excerpt" and len(news["text"]) <= 300

    rels = {r["obs_id"]: r["annotations"][0] for r in files["relations.jsonl"]}
    partial = next(a for a in rels.values() if a["label"] == "partially_supports")
    assert (partial["conflicts"], partial["stale"]) == (["status"], True)
    assert {a["annotator"] for a in rels.values()} == {"ANN-001"}  # the analyst, by number
    (dep,) = files["dependences.jsonl"]
    assert (dep["type"], dep["annotations"][0]["annotator"]) == ("same_media", "ANN-000")
    assert obs[dep["origin_obs_id"]]["published_at"] <= obs[dep["obs_id"]]["published_at"]

    # Nobody's name or email is in the dataset.
    text = json.dumps(export.files, ensure_ascii=False)
    for private in ("Ana Analyst", "Rahim Uddin", "analyst@office.local", "worker@office.local"):
        assert private not in text

    kinds = sorted(p.kind for p in export.problems)
    assert kinds == ["needs_ground_truth"]  # the pending event; its broken link goes with it


def test_problems_list_links_that_need_conflicts(scenario, client, analyst, db):
    client.patch(
        f"{EVENTS}/{scenario['pending']}",
        json={"occurred": True, "ground_truth_sources": [FOLLOWUP]},
        headers=analyst,
    )
    export = dataset.build(db)
    assert [p.kind for p in export.problems] == ["needs_conflicts"]
    assert export.manifest["counts"]["events.jsonl"] == 2


def test_did_not_happen_but_verified_is_a_problem(client, analyst, db):
    event = create(client, analyst).json()
    client.patch(
        f"{EVENTS}/{event['id']}",
        json={"assessment": "verified", "occurred": False, "ground_truth_sources": [FOLLOWUP]},
        headers=analyst,
    )
    assert [p.kind for p in dataset.build(db).problems] == ["contradiction"]


def test_unlinked_items_on_request(scenario, db, tmp_path):
    export = dataset.build(db, include_unlinked=True)
    assert validate_dir(write(export, tmp_path)).ok
    assert export.manifest["counts"]["observations.jsonl"] == 4  # + the unlinked landslide item


def test_summary_and_download(scenario, client, analyst, admin_headers, db):
    summary = client.get("/api/v1/dataset/summary", headers=analyst).json()
    assert summary["counts"]["events.jsonl"] == 1
    assert summary["problems_by_kind"] == {"needs_ground_truth": 1}
    assert summary["problems"][0]["event_title"] == "Fire at Gazipur factory"

    assert client.get("/api/v1/dataset/export", headers=analyst).status_code == 403
    response = client.get("/api/v1/dataset/export", headers=admin_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert set(names) >= {"events.jsonl", "observations.jsonl", "manifest.json", "problems.json"}
    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.DATASET_EXPORTED))
    assert entry.details["counts"]["events.jsonl"] == 1


def test_cli_writes_a_valid_directory(scenario, tmp_path, monkeypatch, settings):
    from app import cli

    monkeypatch.setenv("CARCUX_DATABASE_URL", settings.database_url)
    cli.get_settings.cache_clear()
    assert cli.main(["export-dataset", str(tmp_path)]) == 0
    assert validate_dir(tmp_path).ok
    assert json.loads((tmp_path / "manifest.json").read_text())["problems"] == 1
