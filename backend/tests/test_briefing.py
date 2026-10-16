"""Decision support in the product: an event's briefing (suggested priority, a summary
whose every sentence cites evidence, what changed), and whether analysts follow the
suggested priority, logged like the other suggestions."""

from datetime import timedelta

from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.event import EvidenceRelation
from app.models.user import Role
from app.services import briefing
from app.services.audit import AuditAction
from tests.test_assessment import NOW, _event, _feed, _report, _signal
from tests.test_assessment import people as people  # noqa: F401 (fixture)

TWO_DEAD = "Mirpur 10 e komor pani, 2 jon mara geche"


def _flooded(db, people):
    a, (w1, w2, _) = people["analyst"], people["workers"]
    w1.full_name, w2.full_name = "Rahim Uddin", "Karim Mia"
    e = _event(db, a)
    _report(db, e, w1, a, text=TWO_DEAD)
    _report(db, e, w2, a, text="Mirpur 10 e komor pani", minutes=10)
    _signal(db, e, _feed(db, "Daily Star"), a, minutes=20)
    _report(db, e, people["workers"][2], a, relation=EvidenceRelation.CONTRADICTS,
            text="eta gujob, kono pani nai", minutes=30)  # fmt: skip
    db.commit()
    return e


def test_the_briefing_cites_evidence_and_never_names_field_workers(client, db, people):
    e = _flooded(db, people)
    r = client.get(f"/api/v1/events/{e.id}/briefing", headers=people["analyst_headers"])
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["priority"]["level"] in ("low", "medium", "high", "critical")
    assert b["priority"]["score"] == sum(f["points"] for f in b["priority"]["factors"])
    links = {str(link.id) for link in e.evidence}
    assert b["summary"] and all(set(s["cites"]) <= links for s in b["summary"])
    assert all(s["cites"] for s in b["summary"])  # no sentence without evidence
    text = str(b)
    assert "Rahim Uddin" not in text and "Karim Mia" not in text
    assert "A field worker" in text
    assert any(s["kind"] == "denial" and "gujob" in s["text"] for s in b["summary"])


def test_the_briefing_is_for_reviewers(client, db, people, make_user, login):
    e = _flooded(db, people)
    make_user("viewer@office.local", Role.VIEWER)
    r = client.get(f"/api/v1/events/{e.id}/briefing", headers=login("viewer@office.local"))
    assert r.status_code == 403


def test_what_changed_lists_new_items_and_decisions(client, db, people):
    e = _flooded(db, people)
    h = people["analyst_headers"]
    client.patch(f"/api/v1/events/{e.id}", json={"status": "monitoring"}, headers=h)
    b = briefing.briefing(db, e, NOW + timedelta(hours=2), NOW + timedelta(minutes=15))
    kinds = [c["kind"] for c in b["changes"]]
    assert kinds[0] == "new" and "denial" in kinds
    # The status change happened at the real time of this test, after the window.
    later = briefing.briefing(db, e, NOW + timedelta(days=3650), NOW)
    assert any(c["text"].endswith("Status set to monitoring.") for c in later["changes"])


def test_setting_a_priority_logs_the_suggestion_and_it_is_evaluated(client, db, people):
    e = _flooded(db, people)
    h = people["analyst_headers"]
    suggested = client.get(f"/api/v1/events/{e.id}/briefing", headers=h).json()["priority"]
    chosen = "critical" if suggested["level"] != "critical" else "low"
    r = client.patch(f"/api/v1/events/{e.id}", json={"priority": chosen}, headers=h)
    assert r.status_code == 200, r.text
    row = db.scalars(select(AuditLog).where(AuditLog.action == AuditAction.EVENT_UPDATED)).all()[-1]
    logged = row.details["priority_suggestion"]
    assert logged["followed"] is False and logged["level"] in ("low", "medium", "high")
    result = briefing.evaluate(db)
    assert (result["shown"], result["followed"]) == (1, 0)
    assert result["confusion"][chosen][logged["level"]] == 1
    assert "followed 0 (0%)" in briefing.table(result)
