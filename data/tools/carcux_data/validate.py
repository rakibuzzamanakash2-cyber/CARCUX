"""Validate a CARCUX-BD dataset directory.

A dataset directory holds five JSON Lines files (one record per line):

    events.jsonl  sources.jsonl  observations.jsonl  relations.jsonl  dependences.jsonl

Two kinds of checks run:

1. Schema: every record matches its JSON Schema in data/schema/v1/.
2. Integrity: rules that span records or files, which a schema cannot express
   (unique ids, references exist, a copy is published after its original, ...).

Usage:
    python -m carcux_data.validate data/samples/v1/example
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema" / "v1"

FILES = {
    "events.jsonl": "event",
    "sources.jsonl": "source",
    "observations.jsonl": "observation",
    "relations.jsonl": "relation",
    "dependences.jsonl": "dependence",
}

# Each event type belongs to exactly one family.
TYPE_FAMILY = {
    **dict.fromkeys(
        [
            "flood", "flash_flood", "waterlogging", "cyclone", "storm_surge", "landslide",
            "river_erosion", "heavy_rainfall",
        ],
        "natural_calamity",
    ),
    **dict.fromkeys(
        [
            "road_blockage", "road_accident", "road_damage", "bridge_damage", "power_outage",
            "gas_outage", "water_outage", "construction_closure",
        ],
        "road_infrastructure",
    ),
    **dict.fromkeys(
        ["fire", "building_collapse", "building_hazard", "explosion"], "urban_emergency"
    ),
}  # fmt: skip

# Privacy lint: personal contact details must never be stored.
_BD_PHONE = re.compile(r"(?:\+?88)?01[3-9]\d{8}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    counts: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    @property
    def ok(self) -> bool:
        return not self.errors


def load_validators() -> dict[str, Draft202012Validator]:
    resources = []
    for path in SCHEMA_DIR.glob("*.schema.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append((contents["$id"], Resource.from_contents(contents)))
    registry = Registry().with_resources(resources)

    validators = {}
    for name in set(FILES.values()):
        schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validators[name] = Draft202012Validator(schema, registry=registry)
    return validators


def _read_jsonl(path: Path, report: Report) -> list[tuple[int, dict]]:
    records = []
    if not path.exists():
        report.error(path.name, "file is missing (an empty file is fine)")
        return records
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append((lineno, json.loads(line)))
        except json.JSONDecodeError as exc:
            report.error(f"{path.name}:{lineno}", f"invalid JSON ({exc.msg})")
    return records


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_dir(directory: Path) -> Report:
    report = Report()
    validators = load_validators()
    data: dict[str, list[tuple[int, dict]]] = {}

    # 1. Schema checks
    for filename, kind in FILES.items():
        records = _read_jsonl(directory / filename, report)
        data[kind] = records
        for lineno, record in records:
            for err in validators[kind].iter_errors(record):
                where = "/".join(str(p) for p in err.absolute_path) or "(record)"
                report.error(f"{filename}:{lineno}", f"{where}: {err.message}")

    # Integrity checks only make sense on schema-valid data.
    if not report.ok:
        return report
    _check_integrity(data, report)
    _count(data, report)
    return report


def _index(records, key, filename, report) -> dict[str, tuple[int, dict]]:
    index = {}
    for lineno, record in records:
        rid = record[key]
        if rid in index:
            report.error(
                f"{filename}:{lineno}", f"duplicate {key} {rid} (first on line {index[rid][0]})"
            )
        else:
            index[rid] = (lineno, record)
    return index


def _check_integrity(data, report: Report) -> None:
    events = _index(data["event"], "event_id", "events.jsonl", report)
    sources = _index(data["source"], "source_id", "sources.jsonl", report)
    observations = _index(data["observation"], "obs_id", "observations.jsonl", report)

    # Events
    for eid, (lineno, ev) in events.items():
        where = f"events.jsonl:{lineno}"
        if TYPE_FAMILY[ev["type"]] != ev["family"]:
            report.error(
                where, f"type {ev['type']} belongs to {TYPE_FAMILY[ev['type']]}, not {ev['family']}"
            )
        if "end" in ev and _dt(ev["end"]) < _dt(ev["start"]):
            report.error(where, "end is before start")
        parent = ev.get("parent_event_id")
        if parent:
            if parent == eid:
                report.error(where, "event is its own parent")
            elif parent not in events:
                report.error(where, f"parent_event_id {parent} does not exist")
        times = [_dt(a["as_of"]) for a in ev["assessments"]]
        if times != sorted(times):
            report.error(where, "assessments must be in time order")
        for a in ev["assessments"]:
            _check_annotators(a["annotations"], f"{where} assessment {a['as_of']}", report)
        if not ev["ground_truth"]["occurred"] and ev["assessments"][-1]["label"] == "verified":
            report.error(
                where, "last assessment is 'verified' but ground truth says it did not occur"
            )
    _check_parent_cycles(events, report)

    # Observations
    for lineno, ob in observations.values():
        where = f"observations.jsonl:{lineno}"
        src = sources.get(ob["source_id"])
        if src is None:
            report.error(where, f"source_id {ob['source_id']} does not exist")
        elif ob["is_simulated"] and ob["simulation"]["kind"] == "field_report":
            s = src[1]
            if s["source_type"] != "field" or not s.get("is_simulated", False):
                report.error(
                    where, "simulated field reports must come from a simulated field source"
                )
        if _dt(ob["collected_at"]) < _dt(ob["published_at"]):
            report.error(where, "collected_at is before published_at")
        derived = ob.get("simulation", {}).get("derived_from")
        if derived and derived not in events and derived not in observations:
            report.error(where, f"simulation.derived_from {derived} does not exist")
        for text_field in _texts(ob):
            if _BD_PHONE.search(text_field) or _EMAIL.search(text_field):
                report.error(where, "text contains a phone number or email address; remove it")

    # Relations
    seen_pairs = set()
    for lineno, rel in data["relation"]:
        where = f"relations.jsonl:{lineno}"
        pair = (rel["obs_id"], rel["event_id"])
        if pair in seen_pairs:
            report.error(where, f"duplicate relation {pair[0]} -> {pair[1]}")
        seen_pairs.add(pair)
        if rel["obs_id"] not in observations:
            report.error(where, f"obs_id {rel['obs_id']} does not exist")
        if rel["event_id"] not in events:
            report.error(where, f"event_id {rel['event_id']} does not exist")
        _check_annotators(rel["annotations"], where, report)

    # Dependences
    edges: dict[str, str] = {}
    for lineno, dep in data["dependence"]:
        where = f"dependences.jsonl:{lineno}"
        child, origin = dep["obs_id"], dep["origin_obs_id"]
        if child == origin:
            report.error(where, "an observation cannot depend on itself")
            continue
        if child not in observations or origin not in observations:
            report.error(where, "obs_id and origin_obs_id must both exist")
            continue
        if child in edges:
            report.error(
                where,
                f"{child} already has an origin ({edges[child]}); "
                "record only the item it was directly copied from",
            )
            continue
        edges[child] = origin
        if _dt(observations[child][1]["published_at"]) < _dt(
            observations[origin][1]["published_at"]
        ):
            report.error(where, f"{child} is published before its origin {origin}")
        _check_annotators(dep["annotations"], where, report)
    _check_dependence_cycles(edges, report)


def _texts(ob: dict):
    if "text" in ob:
        yield ob["text"]
    for m in ob.get("media", []):
        yield from (m[k] for k in ("transcript", "ocr_text") if k in m)


def _check_annotators(annotations: list[dict], where: str, report: Report) -> None:
    names = [a["annotator"] for a in annotations]
    dupes = [n for n, c in Counter(names).items() if c > 1]
    if dupes:
        report.error(where, f"annotator {dupes[0]} judged the same item twice")


def _check_parent_cycles(events, report: Report) -> None:
    for start in events:
        seen, node = set(), start
        while node is not None:
            if node in seen:
                report.error("events.jsonl", f"parent_event_id cycle involving {start}")
                break
            seen.add(node)
            node = events.get(node, (0, {}))[1].get("parent_event_id")


def _check_dependence_cycles(edges: dict[str, str], report: Report) -> None:
    for start in edges:
        seen, node = set(), start
        while node in edges:
            if node in seen:
                report.error("dependences.jsonl", f"dependence cycle involving {start}")
                break
            seen.add(node)
            node = edges[node]


def _count(data, report: Report) -> None:
    c = report.counts
    for _, ev in data["event"]:
        c["event_family"][ev["family"]] += 1
        c["final_assessment"][ev["assessments"][-1]["label"]] += 1
    for _, ob in data["observation"]:
        c["observation_modality"][ob["modality"]] += 1
        c["observation_language"][ob["language"]] += 1
        c["observation_simulated"][str(ob["is_simulated"]).lower()] += 1
    for _, rel in data["relation"]:
        c["relation_gold"][rel["gold"]["label"] if "gold" in rel else "(not adjudicated)"] += 1
    for _, dep in data["dependence"]:
        c["dependence_type"][dep["type"]] += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m carcux_data.validate")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)

    report = validate_dir(args.directory)
    if not report.ok:
        print(f"FAILED: {len(report.errors)} problem(s) in {args.directory}\n")
        for line in report.errors:
            print(f"  - {line}")
        return 1

    print(f"OK: {args.directory} is valid CARCUX-BD v1\n")
    for name, counter in report.counts.items():
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counter.items()))
        print(f"  {name:24} {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
