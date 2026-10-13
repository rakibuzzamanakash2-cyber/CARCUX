"""Second opinions, agreement and adjudication (annotation guideline, section 7)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.user import Role
from app.services import dataset
from app.services.annotation import cohen_kappa, krippendorff_alpha
from app.services.audit import AuditAction
from tests.test_dataset import FOLLOWUP, validate_dir, write
from tests.test_events import create, report

EVENTS = "/api/v1/events"
ANN = "/api/v1/annotation"


@pytest.fixture
def first(make_user, login):
    make_user("first@office.local", Role.ANALYST, full_name="First Analyst")
    return login("first@office.local")


@pytest.fixture
def second(make_user, login):
    make_user("second@office.local", Role.ANALYST, full_name="Second Analyst")
    return login("second@office.local")


@pytest.fixture
def worker(make_user, login):
    make_user("worker@office.local", Role.FIELD_WORKER)
    return login("worker@office.local")


@pytest.fixture
def links(client, first, worker):
    """One event with three reports linked by the first analyst."""
    event = create(client, first).json()
    out = []
    for relation, conflicts in (("supports", []), ("partially_supports", ["magnitude"]),
                                ("related", [])):  # fmt: skip
        r = report(client, worker)
        body = {"field_report_id": r["id"], "relation": relation, "conflicts": conflicts}
        response = client.post(f"{EVENTS}/{event['id']}/evidence", json=body, headers=first)
        assert response.status_code == 201, response.text
        out.append(response.json())
    return {"event": event, "links": out}


def judge(client, headers, evidence_id, relation, conflicts=(), **extra):
    body = {"evidence_id": evidence_id, "relation": relation, "conflicts": list(conflicts), **extra}
    return client.post(f"{ANN}/judgements", json=body, headers=headers)


# --- Statistics -------------------------------------------------------------------------


def test_kappa_and_alpha_on_known_values():
    assert cohen_kappa([("a", "a"), ("b", "b")]) == 1.0
    assert cohen_kappa([("a", "a"), ("a", "b"), ("b", "b"), ("b", "b")]) == pytest.approx(0.5)
    # Value from the reference implementation (krippendorff on PyPI), nominal level.
    units = [["a", "a"], ["a", "b"], ["b", "a"], ["b", "b"], ["c", "c"], ["a", "c"]]
    assert krippendorff_alpha(units) == pytest.approx(0.2978723404255319)
    # Units can have more than two annotators.
    assert krippendorff_alpha([["a", "a", "a"], ["b", "b", "b"]]) == 1.0
    assert krippendorff_alpha([["a"]]) is None


# --- The workflow -----------------------------------------------------------------------


def test_linking_records_the_first_judgement(client, first, links):
    item = links["links"][1]
    assert (item["judgement_count"], item["agreement"]) == (1, "single")


def test_queue_is_blind_and_excludes_own_links(client, first, second, links):
    mine = client.get(f"{ANN}/queue", headers=first).json()
    assert mine["total"] == 0  # the first analyst judged them by linking

    theirs = client.get(f"{ANN}/queue", headers=second).json()
    assert theirs["total"] == 3
    item = theirs["items"][0]
    assert set(item) == {"evidence_id", "event", "field_report", "signal", "judgements"}
    assert "relation" not in item and item["judgements"] == 1  # no label shown


def test_second_opinions_agreement_and_adjudication(client, first, second, links, db):
    supp, part, rel = (link["id"] for link in links["links"])
    assert judge(client, second, supp, "supports", confidence=3).status_code == 201
    assert judge(client, second, part, "partially_supports", ["location"]).status_code == 201
    assert judge(client, second, rel, "unrelated").status_code == 201
    assert client.get(f"{ANN}/queue", headers=second).json()["total"] == 0

    stats = client.get(f"{ANN}/agreement", headers=first).json()
    assert (stats["items_with_two"], stats["items_total"]) == (3, 3)
    assert stats["percent"] == pytest.approx(2 / 3)  # labels: supports, partly, related≠unrelated
    assert stats["matrix"]["related"]["unrelated"] == 1
    assert stats["target"] == 0.70
    assert stats["open_disagreements"] == 2  # different conflicts count too

    dis = client.get(f"{ANN}/disagreements", headers=first).json()
    assert {d["evidence_id"] for d in dis} == {part, rel}
    names = {j["annotator"]["full_name"] for j in dis[0]["judgements"]}
    assert names == {"First Analyst", "Second Analyst"}

    resolved = client.post(
        f"{ANN}/adjudicate",
        json={"evidence_id": rel, "relation": "unrelated", "note": "A different street"},
        headers=first,
    )
    assert resolved.status_code == 200, resolved.text
    assert (resolved.json()["relation"], resolved.json()["agreement"]) == ("unrelated", "resolved")
    entry = db.scalar(select(AuditLog).where(AuditLog.action == AuditAction.EVIDENCE_ADJUDICATED))
    assert entry.details["judgements"] == ["related", "unrelated"]

    event = client.get(f"{EVENTS}/{links['event']['id']}", headers=first).json()
    counts = event["evidence_counts"]
    assert (counts["unrelated"], counts["related"], counts["reporters"]) == (1, 0, 1)
    assert client.get(f"{ANN}/agreement", headers=first).json()["open_disagreements"] == 1


def test_judgements_follow_the_rules(client, second, links):
    supp = links["links"][0]["id"]
    assert judge(client, second, supp, "partially_supports").status_code == 422
    assert judge(client, second, supp, "unrelated", ["location"]).status_code == 422
    missing = judge(client, second, "00000000-0000-0000-0000-000000000000", "supports")
    assert missing.status_code == 422
    # Judging again replaces the earlier judgement.
    assert judge(client, second, supp, "supports").status_code == 201
    assert judge(client, second, supp, "contradicts").status_code == 201
    link = client.get(f"{EVENTS}/{links['event']['id']}/evidence", headers=second).json()[0]
    assert (link["judgement_count"], link["agreement"]) == (2, "disagree")


def test_unrelated_can_be_chosen_when_linking(client, first, worker):
    """Rejecting a suggestion records a hard negative instead of losing it."""
    event = create(client, first).json()
    r = report(client, worker)
    body = {"field_report_id": r["id"], "relation": "unrelated"}
    linked = client.post(f"{EVENTS}/{event['id']}/evidence", json=body, headers=first)
    assert linked.status_code == 201
    suggested = client.get(f"{EVENTS}/{event['id']}/candidate-reports", headers=first).json()
    assert r["id"] not in [c["report"]["id"] for c in suggested]
    counts = client.get(f"{EVENTS}/{event['id']}", headers=first).json()["evidence_counts"]
    assert (counts["unrelated"], counts["reporters"]) == (1, 0)


def test_overview_counts_waiting_second_opinions(client, second, links):
    assert client.get("/api/v1/overview", headers=second).json()["second_opinions"] == 3


def test_viewers_cannot_annotate(client, make_user, login, links):
    make_user("viewer@office.local", Role.VIEWER)
    viewer = login("viewer@office.local")
    assert client.get(f"{ANN}/queue", headers=viewer).status_code == 403
    assert judge(client, viewer, links["links"][0]["id"], "supports").status_code == 403


def test_export_carries_both_annotators_and_gold(client, first, second, links, db, tmp_path):
    supp, part, rel = (link["id"] for link in links["links"])
    judge(client, second, supp, "supports")
    judge(client, second, part, "partially_supports", ["location"])
    judge(client, second, rel, "unrelated")
    client.post(f"{ANN}/adjudicate", json={"evidence_id": rel, "relation": "unrelated"},
                headers=first)  # fmt: skip
    client.patch(
        f"{EVENTS}/{links['event']['id']}",
        json={"occurred": True, "ground_truth_sources": [FOLLOWUP]},
        headers=first,
    )
    export = dataset.build(db, now=datetime.now(UTC) + timedelta(days=2))
    result = validate_dir(write(export, Path(tmp_path)))
    assert result.ok, result.errors

    rels = export.files["relations.jsonl"]
    assert all(len(r["annotations"]) == 2 for r in rels)
    assert {a["annotator"] for r in rels for a in r["annotations"]} == {"ANN-001", "ANN-002"}
    gold = sorted(r.get("gold", {}).get("label", "-") for r in rels)
    # agreed (supports), adjudicated (unrelated), open disagreement (no gold yet)
    assert gold == ["-", "supports", "unrelated"]
