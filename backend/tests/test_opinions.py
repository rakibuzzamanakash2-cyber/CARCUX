"""People's opinions on incidents: shown at once as opinions, removed when reported,
moderated by admins, and fed to analysts as signals from one source per account."""

import uuid

from sqlalchemy import select

from app.models.signal import Signal, SignalStatus, Source
from app.services import public as rules
from tests.test_public import P, _person
from tests.test_public import post as post  # noqa: F401 (fixture)
from tests.test_statements import setup as setup  # noqa: F401 (fixture)

SAY = "Water is still knee-deep near Mirpur 10 at 7 pm, three shops flooded"


def _say(client, setup, headers, body=SAY):
    return client.post(f"{P}/incidents/{setup['event'].id}/opinions", json={"body": body},
                       headers=headers)  # fmt: skip


def test_only_on_public_incidents_and_only_signed_in(client, setup):
    rina = _person(client)
    assert _say(client, setup, rina).status_code == 404  # no official post yet


def test_an_opinion_shows_at_once_and_becomes_a_signal(client, setup, post, db):
    rina = _person(client)
    assert _say(client, setup, {}).status_code == 401
    r = _say(client, setup, rina)
    assert r.status_code == 201, r.text
    inc = client.get(f"{P}/incidents/{setup['event'].id}").json()
    assert [(o["author"], o["body"]) for o in inc["opinions"]] == [("Rina", SAY)]

    signal = db.scalar(
        select(Signal).where(Signal.external_id == f"carcux-opinion:{r.json()['id']}")
    )
    assert signal.text == SAY and signal.event_type == "waterlogging"
    assert signal.url.endswith(f"/public/incidents/{setup['event'].id}#opinion-{r.json()['id']}")
    source = db.get(Source, signal.source_id)
    assert source.name == "Rina · CARCUX public site" and source.source_type.value == "social"
    assert source.domain == "carcux"

    # Analysts see it on the event, with CARCUX's reading, until they link it.
    analyst = setup["h"]["analyst"]
    seen = client.get(f"/api/v1/events/{setup['event'].id}/public-opinions", headers=analyst)
    assert seen.status_code == 200 and [s["signal"]["id"] for s in seen.json()] == [str(signal.id)]
    assert seen.json()[0]["stance"]["relation"] in ("supports", "partially_supports")
    candidates = client.get(f"/api/v1/events/{setup['event'].id}/candidate-signals",
                            headers=analyst).json()  # fmt: skip
    assert str(signal.id) not in {c["signal"]["id"] for c in candidates}  # not twice
    link = client.post(f"/api/v1/events/{setup['event'].id}/evidence",
                       json={"signal_id": str(signal.id), "relation": "supports",
                             "conflicts": []}, headers=analyst)  # fmt: skip
    assert link.status_code == 201, link.text
    again = client.get(f"/api/v1/events/{setup['event'].id}/public-opinions", headers=analyst)
    assert again.json() == []
    assert client.get(f"/api/v1/events/{setup['event'].id}/public-opinions",
                      headers=rina).status_code == 401  # fmt: skip

    # A second opinion from the same person: the same source (one track record).
    _say(client, setup, rina, "Pumps have started near the bus stand")
    sources = db.scalars(select(Source).where(Source.domain == "carcux")).all()
    assert len(sources) == 1


def test_rate_limit(client, setup, post):
    rina = _person(client)
    for k in range(rules.OPINIONS_PER_WINDOW):
        assert _say(client, setup, rina, f"Update {k} from Mirpur").status_code == 201
    fast = _say(client, setup, rina, "One more")
    assert fast.status_code == 422 and "too fast" in fast.json()["detail"]


def test_reports_hide_and_admins_decide(client, setup, post, db):
    rina = _person(client)
    oid = _say(client, setup, rina, "The government is hiding 100 deaths").json()["id"]
    for k in range(3):
        h = _person(client, f"r{k}@example.com", f"Reader {k}")
        assert client.post(f"{P}/opinions/{oid}/report", json={"reason": "false_information"},
                           headers=h).status_code == 204  # fmt: skip
    assert client.get(f"{P}/incidents/{setup['event'].id}").json()["opinions"] == []
    signal = db.scalar(select(Signal).where(Signal.external_id == f"carcux-opinion:{oid}"))
    assert signal.status == SignalStatus.DISMISSED  # left out of analysts' queues

    official, admin = setup["h"]["official"], setup["h"]["admin"]
    assert client.get("/api/v1/moderation/opinions", headers=official).status_code == 403
    waiting = client.get("/api/v1/moderation/opinions", headers=admin).json()
    assert [(w["id"], w["kind"], w["reports"]) for w in waiting] == [(oid, "opinion", 3)]
    kept = client.post(f"/api/v1/moderation/opinions/{oid}/restore", headers=admin)
    assert kept.status_code == 200
    db.expire_all()
    assert db.get(Signal, signal.id).status == SignalStatus.NEW
    hidden = client.post(f"/api/v1/moderation/opinions/{oid}/hide",
                         json={"reason": "False death toll"}, headers=admin)  # fmt: skip
    assert hidden.json()["hidden_reason"] == "False death toll"


def test_deleting_takes_the_words_back(client, setup, post, db):
    rina = _person(client)
    oid = _say(client, setup, rina).json()["id"]
    assert client.delete(f"{P}/opinions/{oid}", headers=_person(client, "x@example.com", "Xavier")
                         ).status_code == 404  # fmt: skip
    assert client.delete(f"{P}/opinions/{oid}", headers=rina).status_code == 204
    signal = db.scalar(select(Signal).where(Signal.external_id == f"carcux-opinion:{oid}"))
    db.refresh(signal)
    assert (signal.title, signal.text, signal.status) == (
        "Removed by its author", None, SignalStatus.DISMISSED,
    )  # fmt: skip

    other = _say(client, setup, rina, "Another view").json()["id"]
    client.post(f"{P}/auth/delete", json={"password": "correct horse"}, headers=rina)
    db.expire_all()
    s2 = db.scalar(select(Signal).where(Signal.external_id == f"carcux-opinion:{other}"))
    assert s2.text is None
    assert db.get(Source, s2.source_id).name == "Deleted account · CARCUX public site"


def test_banning_hides_opinions(client, setup, post):
    rina = _person(client)
    oid = _say(client, setup, rina).json()["id"]
    rows = client.get("/api/v1/moderation/opinions?state=all", headers=setup["h"]["admin"]).json()
    account_id = next(r["account_id"] for r in rows if r["id"] == oid)
    client.post(f"/api/v1/moderation/accounts/{account_id}/ban", json={"reason": "Abuse"},
                headers=setup["h"]["admin"])  # fmt: skip
    assert client.get(f"{P}/incidents/{setup['event'].id}").json()["opinions"] == []
    assert uuid.UUID(oid)
