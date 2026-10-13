"""Read a CARCUX-BD dataset (data/schema/v1) into what correlation needs.

Each observation becomes an `Obs`: its text, when it was seen, where (with how
precisely), and the event type it claims. The gold answer comes from relations:
an observation belongs to every event it is *about* (supports, partially supports,
contradicts or is related to). "unrelated" is not membership: it is a hard negative.

Two gold views are kept:

- `events`: the overlapping truth. One report can describe both the waterlogging and
  the road blockage it caused.
- `roots`: child events folded into their root parent (`parent_event_id`), giving one
  group per observation where possible. Partition measures (ARI) use this view.

Observations that no annotator placed in any event are left out of scoring: there is
no truth to score them against.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

MEMBER_LABELS = {"supports", "partially_supports", "contradicts", "related"}
# Strongest first: used to choose one event when a partition is needed.
LABEL_RANK = {"supports": 0, "partially_supports": 1, "contradicts": 2, "related": 3}

FAMILY = {
    **dict.fromkeys(
        [
            "flood",
            "flash_flood",
            "waterlogging",
            "cyclone",
            "storm_surge",
            "landslide",
            "river_erosion",
            "heavy_rainfall",
            "earthquake",
        ],
        "natural_calamity",
    ),
    **dict.fromkeys(
        [
            "road_blockage",
            "road_accident",
            "road_damage",
            "bridge_damage",
            "power_outage",
            "gas_outage",
            "water_outage",
            "construction_closure",
            "rail_accident",
        ],
        "road_infrastructure",
    ),
    **dict.fromkeys(
        ["fire", "building_collapse", "building_hazard", "explosion"], "urban_emergency"
    ),
}


@dataclass
class Obs:
    obs_id: str
    text: str
    language: str
    time: datetime  # observed_at if the item says, else published_at
    published: datetime
    lat: float | None
    lon: float | None
    precision_m: float | None
    event_type: str | None
    events: set[str] = field(default_factory=set)  # gold, overlapping
    roots: set[str] = field(default_factory=set)  # gold, children folded into parents
    primary: str | None = None  # one root event, for partition measures
    negatives: set[str] = field(default_factory=set)  # events it is labelled "unrelated" to

    @property
    def family(self) -> str | None:
        return FAMILY.get(self.event_type or "")

    @property
    def located(self) -> bool:
        return self.lat is not None and self.lon is not None


@dataclass
class Dataset:
    observations: list[Obs]  # annotated ones only, in time order
    unannotated: int
    events: dict[str, dict]
    name: str = ""


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _label(relation: dict) -> str | None:
    """Gold if adjudicated, else the label most annotators gave (first wins a tie)."""
    if relation.get("gold"):
        return relation["gold"]["label"]
    labels = [a["label"] for a in relation.get("annotations", [])]
    if not labels:
        return None
    return max(dict.fromkeys(labels), key=labels.count)


def _root(event_id: str, events: dict[str, dict]) -> str:
    seen = set()
    while (parent := events.get(event_id, {}).get("parent_event_id")) and parent not in seen:
        seen.add(event_id)
        event_id = parent
    return event_id


def load(directory: str | Path) -> Dataset:
    directory = Path(directory)
    events = {e["event_id"]: e for e in _jsonl(directory / "events.jsonl")}
    membership: dict[str, dict[str, str]] = {}
    negatives: dict[str, set[str]] = {}
    for rel in _jsonl(directory / "relations.jsonl"):
        label = _label(rel)
        if label in MEMBER_LABELS:
            membership.setdefault(rel["obs_id"], {})[rel["event_id"]] = label
        elif label == "unrelated":
            negatives.setdefault(rel["obs_id"], set()).add(rel["event_id"])

    observations, unannotated = [], 0
    for ob in _jsonl(directory / "observations.jsonl"):
        oid = ob["obs_id"]
        if oid not in membership and oid not in negatives:
            unannotated += 1
            continue
        mentions = ob.get("location_mentions") or []
        # GPS first, then the most precise mention.
        mention = min(
            mentions,
            key=lambda m: (not m.get("from_gps", False), m["resolved"]["precision_m"]),
            default=None,
        )
        lat = lon = precision = None
        if mention and mention["resolved"]["geometry"]["type"] == "Point":
            lon, lat = mention["resolved"]["geometry"]["coordinates"]
            precision = float(mention["resolved"]["precision_m"])
        event_type = next(
            (str(c["value"]) for c in ob.get("claims", []) if c["attribute"] == "event_type"),
            None,
        )
        published = _dt(ob["published_at"])
        member = membership.get(oid, {})
        roots = {_root(e, events) for e in member}
        primary = None
        if member:
            best = min(member, key=lambda e: (LABEL_RANK[member[e]], e))
            primary = _root(best, events)
        else:
            # Only "unrelated" labels: about some event not in the dataset. Its own group.
            primary = f"_alone:{oid}"
            roots = {primary}
        observations.append(
            Obs(
                obs_id=oid,
                text=ob.get("text") or "",
                language=ob.get("language", "en"),
                time=_dt(ob["observed_at"]) if ob.get("observed_at") else published,
                published=published,
                lat=lat,
                lon=lon,
                precision_m=precision,
                event_type=event_type,
                events=set(member) or {primary},
                roots=roots,
                primary=primary,
                negatives=negatives.get(oid, set()),
            )
        )
    observations.sort(key=lambda o: (o.published, o.obs_id))
    return Dataset(observations, unannotated, events, name=directory.name)
