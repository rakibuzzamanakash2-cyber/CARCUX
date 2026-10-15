"""Copies among an event's evidence: detected, decided by analysts, counted once, and
exported as dataset dependences."""

import sys
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.event import EventEvidence, EvidenceRelation
from app.models.field_report import FieldReportMedia
from app.models.signal import Signal
from app.services import assess, copies, dataset
from app.services.audit import AuditAction
from tests.test_assessment import NOW, S, _event, _feed, _report, _signal, _suggestion
from tests.test_assessment import people as people  # noqa: F401 (fixture)

DATA_TOOLS = Path(__file__).resolve().parents[2] / "data" / "tools"
sys.path.insert(0, str(DATA_TOOLS))
from carcux_data.validate import validate_dir  # noqa: E402

C = EvidenceRelation.CONTRADICTS
RUMOUR = "Building collapses in Tejgaon, many trapped under the rubble near the rail gate"


def _news(db, event, analyst, name, text, minutes, relation=S):
    feed = _feed(db, name)
    _signal(db, event, feed, analyst, relation=relation, minutes=minutes)
    db.flush()
    sig = db.scalars(select(Signal).where(Signal.source_id == feed.id)).one()
    sig.title, sig.text = text, None
    return db.scalars(select(EventEvidence).where(EventEvidence.signal_id == sig.id)).one()


def _photo(db, link, dhash):
    db.add(
        FieldReportMedia(
            id=uuid.uuid4(), report_id=link.field_report_id, position=0,
            content_type="image/jpeg", size_bytes=1, width=1, height=1, sha256="0" * 64,
            dhash=dhash, storage_key=f"x/{uuid.uuid4()}.jpg",
        )
    )  # fmt: skip


# --- Detection -------------------------------------------------------------------------------


def test_reworded_news_is_a_copy_of_the_first_report(db, people):
    a = people["analyst"]
    e = _event(db, a)
    first = _news(db, e, a, "Daily One", RUMOUR, 0)
    reworded = "Tejgaon: building collapses, many trapped under rubble near the rail gate"
    copy = _news(db, e, a, "Daily Two", reworded, 30)
    other = _news(db, e, a, "Daily Three", "Fire service says search continues at Tejgaon", 60)
    db.commit()
    db.refresh(e)
    found = copies.detect(e)
    assert set(found) == {copy.id}
    c = found[copy.id]
    assert (
        c.origin_evidence_id == first.id and c.kind == "rewrite" and c.origin_source == "Daily One"
    )
    assert other.id not in found


def test_attribution_and_verbatim(db, people):
    a = people["analyst"]
    e = _event(db, a)
    _news(db, e, a, "Daily One", RUMOUR, 0)
    cited = _news(db, e, a, "Page A", "According to Daily One, a building collapsed in Tejgaon", 10)
    same = _news(db, e, a, "Page B", RUMOUR, 20)
    db.commit()
    db.refresh(e)
    found = copies.detect(e)
    assert found[cited.id].kind == "cites"
    assert "passing on" in found[cited.id].reasons[-1]
    assert found[same.id].kind == "verbatim_copy"


def test_two_field_workers_writing_alike_are_two_eyewitnesses(db, people):
    a, (w1, w2, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    _report(db, e, w1, a, text="Mirpur 10 e hatu pani, rasta bondho, gari choltese na")
    second = "Mirpur 10 e pani, rasta bondho hoye gese, gari cholche na"
    _report(db, e, w2, a, text=second, minutes=5)
    db.commit()
    db.refresh(e)
    assert copies.detect(e) == {}


def test_a_reused_photo_makes_a_copy(db, people):
    a, (w1, w2, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    first = _report(db, e, w1, a, text="Water at Mirpur 10")
    second = _report(db, e, w2, a, text="Mirpur flooded", minutes=5)
    db.flush()
    _photo(db, first, "ffff0000ffff0000")
    _photo(db, second, "ffff0000ffff0003")  # two bits apart
    db.commit()
    db.refresh(e)
    found = copies.detect(e)
    assert found[second.id].kind == "same_media" and found[second.id].origin_evidence_id == first.id


def test_denying_a_claim_while_quoting_it_is_not_a_copy(db, people):
    a = people["analyst"]
    e = _event(db, a)
    _news(db, e, a, "Daily One", RUMOUR, 0)
    denial = _news(db, e, a, "Fact Check", f"FALSE: '{RUMOUR}'", 30, relation=C)
    db.commit()
    db.refresh(e)
    assert denial.id not in copies.detect(e)


def test_a_source_repeating_itself_is_not_a_copy(db, people):
    a, (w1, _, _) = people["analyst"], people["workers"]
    e = _event(db, a)
    _report(db, e, w1, a, text=RUMOUR)
    _report(db, e, w1, a, text=RUMOUR, minutes=5)
    db.commit()
    db.refresh(e)
    assert copies.detect(e) == {}  # already one voice: one vote per source


# --- In the product ----------------------------------------------------------------------------


def _viral(db, people, n=4):
    """One rumour from a news page, reposted word for word by n other pages."""
    a = people["analyst"]
    e = _event(db, a)
    origin = _news(db, e, a, "Rumour Page", RUMOUR, 0)
    reposts = [_news(db, e, a, f"Page {k}", RUMOUR, 10 * (k + 1)) for k in range(n)]
    db.commit()
    db.refresh(e)
    return e, origin, reposts


def test_reposts_are_counted_once(client, db, people):
    e, origin, reposts = _viral(db, people)
    s = _suggestion(client, people, e)
    assert s["sources_supporting"] == 1 and s["counted_once"] == 4
    assert s["probability"] == assess.STARTING.probability(
        [assess.Vote("x", "news", "x", 1, S, (), NOW)]
    )


def test_evidence_shows_copies_and_analysts_decide(client, db, people):
    e, origin, reposts = _viral(db, people, n=2)
    h = people["analyst_headers"]
    url = f"/api/v1/events/{e.id}/evidence"
    items = {x["id"]: x for x in client.get(url, headers=h).json()}
    assert items[str(origin.id)]["copy_of"] is None
    c = items[str(reposts[0].id)]["copy_of"]
    assert c["status"] == "detected" and c["origin_source"] == "Rumour Page"
    assert c["kind"] == "verbatim_copy" and c["text_similarity"] > 0.9

    # Not a copy: counted as its own voice again.
    r = client.put(f"{url}/{reposts[0].id}/copy", json={"origin_evidence_id": None}, headers=h)
    assert r.status_code == 204
    assert _suggestion(client, people, e)["sources_supporting"] == 2
    items = {x["id"]: x for x in client.get(url, headers=h).json()}
    assert items[str(reposts[0].id)]["copy_of"]["status"] == "rejected"

    # Confirmed, with an origin the analyst names.
    body = {"origin_evidence_id": str(origin.id)}
    assert client.put(f"{url}/{reposts[1].id}/copy", json=body, headers=h).status_code == 204
    items = {x["id"]: x for x in client.get(url, headers=h).json()}
    confirmed = items[str(reposts[1].id)]["copy_of"]
    assert confirmed["status"] == "confirmed" and confirmed["decided_by"]

    # Back to the detection.
    assert client.delete(f"{url}/{reposts[0].id}/copy", headers=h).status_code == 204
    assert _suggestion(client, people, e)["sources_supporting"] == 1

    bad = {"origin_evidence_id": str(uuid.uuid4())}
    assert client.put(f"{url}/{reposts[1].id}/copy", json=bad, headers=h).status_code == 422
    itself = {"origin_evidence_id": str(reposts[1].id)}
    assert client.put(f"{url}/{reposts[1].id}/copy", json=itself, headers=h).status_code == 422
    logged = db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.COPY_DECIDED)).all()
    assert len(logged) == 3


def test_export_writes_copies_as_dependences(client, db, people, tmp_path):
    e, origin, reposts = _viral(db, people, n=2)
    e.occurred = False
    e.ground_truth_sources = [{"reference": "https://example.org/x", "kind": "news_followup",
                               "published_at": (NOW + timedelta(days=1)).isoformat()}]  # fmt: skip
    db.commit()
    h = people["analyst_headers"]
    url = f"/api/v1/events/{e.id}/evidence"
    body = {"origin_evidence_id": str(origin.id)}
    client.put(f"{url}/{reposts[0].id}/copy", json=body, headers=h)
    db.expire_all()
    export = dataset.build(db, now=NOW + timedelta(days=8))
    for name, rows in export.files.items():
        (tmp_path / name).write_text(dataset.write_jsonl(rows), encoding="utf-8")
    result = validate_dir(tmp_path)
    assert result.ok, result.errors
    deps = export.files["dependences.jsonl"]
    assert len(deps) == 2 and {d["type"] for d in deps} == {"verbatim_copy"}
    confirmed = [d for d in deps if "annotator_judgement" in d["evidence"]]
    automatic = [d for d in deps if d["annotations"][0]["annotator"] == "ANN-000"]
    assert len(confirmed) == 1 and len(automatic) == 1
    assert confirmed[0]["annotations"][0]["confidence"] == 3


def test_training_counts_copies_once(db, people):
    e, origin, reposts = _viral(db, people)
    e.occurred = False
    db.commit()
    ((event, vs),) = assess.resolved_events(db)
    assert len(vs) == 1  # one rumour page, not five
