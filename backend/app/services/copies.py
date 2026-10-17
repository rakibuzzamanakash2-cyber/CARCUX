"""Copies among an event's evidence: which items repeat an earlier item from another
source, so they are not counted as independent voices. This is the research's copy
detector (ai/fusion/carcux_fusion/dependence.py) in the product.

For each item linked to an event, compared with the earlier items from other sources:

- **same photo:** a photo within a few bits (difference hash) of an earlier report's;
- **same words:** character n-gram TF-IDF cosine (Bangla, Banglish and English alike)
  of at least 0.7 for news and other signals, and 0.9 (near-verbatim) for field
  reports: two field workers at the same spot write similar short sentences ("Mirpur
  10 e hatu pani, rasta bondho" and "Mirpur 10 e pani, rasta bondho hoye gese" score
  0.71) and are still two eyewitnesses. Texts under 40 characters are never copies on
  wording alone. (The research used 0.6 on simulated text; these stricter values hold
  until real annotated copies can tune them.);
- **attribution:** "according to", "er moto", "এর মতে", "share korlam", "RT" … with at
  least 0.3 of the text in common;
- **order:** only an earlier item can be the origin; and an item that takes the
  opposite stance to its origin (quoting a claim to deny it) is not a copy.

Analysts confirm a detected copy, name the origin themselves, or say it is not a copy
(`CopyDecision`); their decision wins. Until then a detection stands, so a viral repost
is not counted many times while nobody has looked.

Known limits (as in the research): two eyewitnesses writing near-identical words look
like a copy, and a copy that rewrites everything is missed.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.copy import CopyDecision
from app.models.event import ABOUT_THE_EVENT, Event, EventEvidence, EvidenceRelation
from app.models.user import User
from app.services import audit
from app.services.details import headline_and_text
from app.services.media import photo_hashes, photo_match
from app.services.suggest import TextSpace

TEXT_COPY = 0.7  # news and other signals
FIELD_TEXT_COPY = 0.9  # field reports: first-hand unless near-verbatim
MIN_TEXT = 40  # characters: shorter texts are not copies on wording alone
ATTRIBUTION_FLOOR = 0.3
_PUNCT = re.compile(r"[^\w\u0980-\u09FF]+")
ATTRIBUTION = re.compile(
    r"according to|reported by|\bvia\b|\bRT\b|sharing:|shared from|"
    r"er moto|theke jana|share korlam|share korsi|"
    r"এর মতে|সূত্রে|জানিয়েছে|শেয়ার করছি|শেয়ার করলাম",
    re.IGNORECASE,
)
STANCE = {
    EvidenceRelation.SUPPORTS: 1,
    EvidenceRelation.PARTIALLY_SUPPORTS: 1,
    EvidenceRelation.CONTRADICTS: -1,
}


@dataclass(frozen=True)
class Item:
    evidence_id: uuid.UUID
    field: bool  # a field report (first-hand by design)
    source_key: str
    source_name: str
    at: datetime
    text: str
    photos: tuple[dict, ...]  # each photo's hashes (services.media.photo_hashes)
    stance: int  # 1 says it happened, -1 denies it, 0 neither


@dataclass
class Copy:
    evidence_id: uuid.UUID
    origin_evidence_id: uuid.UUID
    origin_source: str
    kind: str  # same_media, verbatim_copy, cites, rewrite (dataset dependence types)
    text_similarity: float | None
    reasons: list[str]
    status: str  # detected, confirmed, rejected
    decided_by: str | None = None
    decided_by_id: uuid.UUID | None = None
    decided_at: datetime | None = None


def _relation(link: EventEvidence) -> EvidenceRelation:
    return link.gold_relation or link.relation


def items(event: Event) -> list[Item]:
    out = []
    for link in event.evidence:
        relation = _relation(link)
        if relation not in ABOUT_THE_EVENT:
            continue
        if link.field_report is not None:
            r = link.field_report
            name = f"Field worker {r.reporter.full_name}" if r.reporter else "Field worker"
            item = Item(
                link.id, True, f"reporter:{r.reporter_id}", name, r.received_at, r.text,
                tuple(photo_hashes(m) for m in r.media), STANCE.get(relation, 0),
            )  # fmt: skip
        else:
            s = link.signal
            item = Item(
                link.id, False, f"source:{s.source_id}", s.source.name, s.published_at,
                headline_and_text(s.title, s.text), (), STANCE.get(relation, 0),
            )  # fmt: skip
        out.append(item)
    out.sort(key=lambda i: (i.at, str(i.evidence_id)))
    return out


def _plain(text: str) -> str:
    return " ".join(_PUNCT.sub(" ", text.lower()).split())


def verbatim(copy: str, origin: str) -> bool:
    """The same words in the same order (case and punctuation aside), possibly with
    something added around them ("share korlam: …")."""
    a, b = _plain(copy), _plain(origin)
    return bool(b) and (a == b or (len(b) >= 20 and b in a))


def _opposed(a: Item, b: Item) -> bool:
    return a.stance * b.stance < 0


def detect(event: Event) -> dict[uuid.UUID, Copy]:
    """Copies the rules find, keyed by the copying item's evidence id."""
    its = items(event)
    if len(its) < 2:
        return {}
    space = TextSpace([i.text for i in its])
    out: dict[uuid.UUID, Copy] = {}
    for j, item in enumerate(its):
        earlier = [
            i
            for i in range(j)
            if its[i].source_key != item.source_key
            and its[i].at <= item.at
            and not _opposed(its[i], item)
        ]
        if not earlier:
            continue
        sims = {i: space.dot(space.vectors[j], space.vectors[i]) for i in earlier}
        photo = [
            i for i in earlier if any(photo_match(a, b) for a in item.photos for b in its[i].photos)
        ]
        best = max(earlier, key=lambda i: sims[i])
        attributes = bool(ATTRIBUTION.search(item.text))
        similarity = sims[best]
        if photo:
            origin, kind = photo[-1], "same_media"
            reasons = ["same photo"]
            if sims[origin] >= TEXT_COPY:
                reasons.append(f"{sims[origin]:.0%} the same words")
        elif (
            len(item.text) >= MIN_TEXT
            and similarity >= (FIELD_TEXT_COPY if item.field else TEXT_COPY)
        ) or (attributes and similarity >= ATTRIBUTION_FLOOR):
            origin = best
            kind = (
                "verbatim_copy"
                if verbatim(item.text, its[origin].text)
                else ("cites" if attributes else "rewrite")
            )
            reasons = [f"{similarity:.0%} the same words"]
            if attributes:
                reasons.append("says it is passing on someone else's report")
        else:
            continue
        out[item.evidence_id] = Copy(
            evidence_id=item.evidence_id,
            origin_evidence_id=its[origin].evidence_id,
            origin_source=its[origin].source_name,
            kind=kind,
            text_similarity=round(sims[origin], 3),
            reasons=reasons,
            status="detected",
        )
    return out


def decisions(db: Session, event: Event) -> dict[uuid.UUID, CopyDecision]:
    ids = [link.id for link in event.evidence]
    if not ids:
        return {}
    rows = db.scalars(select(CopyDecision).where(CopyDecision.evidence_id.in_(ids))).all()
    return {d.evidence_id: d for d in rows}


def resolved(db: Session, event: Event) -> dict[uuid.UUID, Copy]:
    """Detections with analysts' decisions applied: confirmed, named by an analyst,
    rejected (kept, so the page can show it was looked at), or still only detected."""
    found = detect(event)
    by_id = {i.evidence_id: i for i in items(event)}
    for evidence_id, d in decisions(db, event).items():
        who = d.decided_by.full_name if d.decided_by else None
        if d.origin_evidence_id is None:
            if evidence_id in found:
                found[evidence_id].status, found[evidence_id].decided_by = "rejected", who
            continue
        origin = by_id.get(d.origin_evidence_id)
        if origin is None or evidence_id not in by_id:
            continue
        detected = found.get(evidence_id)
        same = detected is not None and detected.origin_evidence_id == d.origin_evidence_id
        found[evidence_id] = Copy(
            evidence_id=evidence_id,
            origin_evidence_id=d.origin_evidence_id,
            origin_source=origin.source_name,
            kind=detected.kind if same else "repost",
            text_similarity=detected.text_similarity if same else None,
            reasons=detected.reasons if same else ["marked by an analyst"],
            status="confirmed",
            decided_by=who,
            decided_by_id=d.decided_by_id,
            decided_at=d.decided_at,
        )
    return found


def counted_once(copies: dict[uuid.UUID, Copy]) -> set[uuid.UUID]:
    """Items not counted as voices of their own: confirmed or detected copies."""
    return {k for k, c in copies.items() if c.status != "rejected"}


class NotInEventError(Exception):
    pass


def decide(
    db: Session,
    *,
    actor: User,
    event: Event,
    item: EventEvidence,
    origin_evidence_id: uuid.UUID | None,
    ip_address: str | None,
) -> None:
    """Record an analyst's decision: `item` copies `origin_evidence_id`, or (None) it is
    not a copy. Replaces any earlier decision on the item; audit-logged."""
    if origin_evidence_id is not None and (
        origin_evidence_id == item.id
        or origin_evidence_id not in {link.id for link in event.evidence}
    ):
        raise NotInEventError
    detected = detect(event).get(item.id)
    decision = db.scalar(select(CopyDecision).where(CopyDecision.evidence_id == item.id))
    if decision is None:
        decision = CopyDecision(evidence_id=item.id, decided_by_id=actor.id)
        db.add(decision)
    decision.origin_evidence_id = origin_evidence_id
    decision.decided_by_id = actor.id
    audit.record(
        db,
        audit.AuditAction.COPY_DECIDED,
        actor_id=actor.id,
        target_type="event",
        target_id=event.id,
        ip_address=ip_address,
        details={
            **_item_ref(item),
            "copy_of": str(origin_evidence_id) if origin_evidence_id else None,
            "detected_origin": str(detected.origin_evidence_id) if detected else None,
        },
    )
    db.commit()


def clear(
    db: Session, *, actor: User, event: Event, item: EventEvidence, ip_address: str | None
) -> None:
    """Remove an analyst's decision: the automatic detection applies again."""
    decision = db.scalar(select(CopyDecision).where(CopyDecision.evidence_id == item.id))
    if decision is None:
        return
    db.delete(decision)
    audit.record(
        db,
        audit.AuditAction.COPY_DECIDED,
        actor_id=actor.id,
        target_type="event",
        target_id=event.id,
        ip_address=ip_address,
        details={**_item_ref(item), "cleared": True},
    )
    db.commit()


def _item_ref(item: EventEvidence) -> dict:
    if item.field_report_id:
        return {"evidence_id": str(item.id), "field_report_id": str(item.field_report_id)}
    return {"evidence_id": str(item.id), "signal_id": str(item.signal_id)}
