"""Read a CARCUX-BD dataset into what fusion needs.

For each event: whether it really happened (`ground_truth.occurred`), and every
observation linked to it with its stance. For each observation: its source, when it
was published, its text and media hashes. Dependences say which observation copied
which (gold, from annotators or the simulator).

Stance is reduced to a vote on occurrence:

- supports, partially_supports: +1 (it happened; partly-supporting items disagree on
  details, not on occurrence)
- contradicts: -1 (denied, or called a rumour)
- related, unrelated: no vote

For details (RQ3): each observation's claims on magnitude, counts and cause; each
link's `conflicts` (the details it gets wrong, from annotators); each event's true
values (`ground_truth.facts`) and gold assessment labels at its checkpoints.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

VOTE = {"supports": 1, "partially_supports": 1, "contradicts": -1}
DETAILS = ("magnitude", "affected_count", "casualty_count", "cause")


@dataclass
class Observation:
    obs_id: str
    source_id: str
    published: datetime
    text: str
    phashes: tuple[str, ...] = ()
    claims: dict = field(default_factory=dict)  # detail -> claimed value


@dataclass
class Evidence:
    obs_id: str
    vote: int  # +1 happened, -1 did not
    conflicts: frozenset = frozenset()  # details it gets wrong (annotated)


@dataclass
class Event:
    event_id: str
    occurred: bool
    evidence: list[Evidence] = field(default_factory=list)
    injected: bool = False  # created by simulated contamination (simulator only)
    facts: dict = field(default_factory=dict)  # detail -> true value
    gold_labels: dict = field(default_factory=dict)  # checkpoint -> assessment label


@dataclass
class Dataset:
    events: dict[str, Event]
    observations: dict[str, Observation]
    source_type: dict[str, str]
    dependences: dict[str, tuple[str, str]]  # obs_id -> (origin_obs_id, type)
    name: str = ""

    def first_seen(self, event: Event) -> datetime | None:
        times = [self.observations[e.obs_id].published for e in event.evidence]
        return min(times) if times else None


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _judgement(rel: dict) -> dict | None:
    """Gold if adjudicated, else the most common annotation (first wins a tie)."""
    if rel.get("gold"):
        return rel["gold"]
    anns = rel.get("annotations", [])
    if not anns:
        return None
    labels = [a["label"] for a in anns]
    best = max(dict.fromkeys(labels), key=labels.count)
    return next(a for a in anns if a["label"] == best)


def _label(rel: dict) -> str | None:
    j = _judgement(rel)
    return j["label"] if j else None


def _details(claims: list[dict]) -> dict:
    return {c["attribute"]: c["value"] for c in claims if c["attribute"] in DETAILS}


def load(directory: str | Path) -> Dataset:
    directory = Path(directory)
    events = {
        e["event_id"]: Event(
            e["event_id"],
            bool(e["ground_truth"]["occurred"]),
            facts=_details(e["ground_truth"].get("facts", [])),
            gold_labels={
                a["checkpoint"]: a["label"] for a in e.get("assessments", []) if "checkpoint" in a
            },
        )
        for e in _jsonl(directory / "events.jsonl")
    }
    raw_obs = _jsonl(directory / "observations.jsonl")
    observations = {
        o["obs_id"]: Observation(
            obs_id=o["obs_id"],
            source_id=o["source_id"],
            published=_dt(o["published_at"]),
            text=o.get("text") or "",
            phashes=tuple(m["phash"] for m in o.get("media", []) if m.get("phash")),
            claims=_details(o.get("claims", [])),
        )
        for o in raw_obs
    }
    for o in raw_obs:
        params = (o.get("simulation") or {}).get("parameters") or {}
        derived = (o.get("simulation") or {}).get("derived_from")
        if params.get("injected_event") and derived in events:
            events[derived].injected = True
    for rel in _jsonl(directory / "relations.jsonl"):
        j = _judgement(rel) or {}
        vote = VOTE.get(j.get("label", ""))
        if vote and rel["event_id"] in events and rel["obs_id"] in observations:
            events[rel["event_id"]].evidence.append(
                Evidence(rel["obs_id"], vote, frozenset(j.get("conflicts", [])))
            )
    for e in events.values():
        e.evidence.sort(key=lambda ev: (observations[ev.obs_id].published, ev.obs_id))
    return Dataset(
        events=events,
        observations=observations,
        source_type={s["source_id"]: s["source_type"] for s in _jsonl(directory / "sources.jsonl")},
        dependences={
            d["obs_id"]: (d["origin_obs_id"], d["type"])
            for d in _jsonl(directory / "dependences.jsonl")
        },
        name=directory.name,
    )
