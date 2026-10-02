"""The validator must accept the worked example and catch each kind of mistake."""

import json
import shutil
from pathlib import Path

import pytest

from carcux_data.validate import main, validate_dir

EXAMPLE = Path(__file__).resolve().parents[2] / "samples" / "v1" / "example"


def load(directory: Path, name: str) -> list[dict]:
    lines = (directory / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def save(directory: Path, name: str, rows: list[dict]) -> None:
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    (directory / f"{name}.jsonl").write_text(text, encoding="utf-8")


@pytest.fixture
def ds(tmp_path: Path) -> Path:
    target = tmp_path / "ds"
    shutil.copytree(EXAMPLE, target)
    return target


def mutate(directory: Path, name: str, fn) -> None:
    rows = load(directory, name)
    fn(rows)
    save(directory, name, rows)


def errors_of(directory: Path) -> str:
    report = validate_dir(directory)
    assert not report.ok, "expected the validator to report a problem"
    return "\n".join(report.errors)


def test_worked_example_is_valid(capsys):
    assert main([str(EXAMPLE)]) == 0
    assert "valid CARCUX-BD v1" in capsys.readouterr().out


# --- Schema-level mistakes -------------------------------------------------------------


def _set(index, path, value):
    def fn(rows):
        target = rows[index]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value

    return fn


def _delete(index, path):
    def fn(rows):
        target = rows[index]
        for key in path[:-1]:
            target = target[key]
        del target[path[-1]]

    return fn


SCHEMA_CASES = [
    ("relations", _set(0, ["gold", "label"], "agrees"), "is not one of"),
    ("relations", _delete(7, ["gold", "conflicts"]), "'conflicts' is a required property"),
    ("events", _set(0, ["start"], "2026-07-14T07:30:00"), "does not match"),
    ("events", _set(0, ["location", "geometry", "coordinates"], [151.2, -33.8]), "location"),
    ("events", _set(0, ["family"], "political"), "is not one of"),
    ("observations", _set(1, ["text"], "x" * 301), "is too long"),
    ("observations", _set(1, ["content_policy"], "reference_only"), "should not be valid"),
    ("observations", _delete(0, ["simulation"]), "'simulation' is a required property"),
    ("observations", _delete(1, ["reference"]), "'reference' is a required property"),
    ("sources", _set(2, ["account_ref"], "@real_handle"), "does not match"),
    ("sources", _delete(2, ["platform"]), "'platform' is a required property"),
    ("dependences", _set(0, ["type"], "similar"), "is not one of"),
]


@pytest.mark.parametrize(("file", "change", "expected"), SCHEMA_CASES)
def test_schema_mistakes_are_caught(ds, file, change, expected):
    mutate(ds, file, change)
    assert expected in errors_of(ds)


# --- Integrity mistakes ----------------------------------------------------------------


def test_type_must_match_family(ds):
    mutate(ds, "events", _set(0, ["type"], "fire"))
    assert "belongs to urban_emergency" in errors_of(ds)


def test_end_before_start(ds):
    mutate(ds, "events", _set(0, ["end"], "2026-07-14T06:00:00+06:00"))
    assert "end is before start" in errors_of(ds)


def test_duplicate_ids(ds):
    mutate(ds, "sources", lambda rows: rows.append(dict(rows[0])))
    assert "duplicate source_id SRC-000001" in errors_of(ds)


@pytest.mark.parametrize(
    ("file", "change", "expected"),
    [
        (
            "observations",
            _set(1, ["source_id"], "SRC-999999"),
            "source_id SRC-999999 does not exist",
        ),
        ("relations", _set(0, ["event_id"], "EVT-999999"), "event_id EVT-999999 does not exist"),
        ("events", _set(1, ["parent_event_id"], "EVT-999999"), "parent_event_id EVT-999999"),
        ("dependences", _set(0, ["origin_obs_id"], "OBS-9999999"), "must both exist"),
    ],
)
def test_dangling_references(ds, file, change, expected):
    mutate(ds, file, change)
    assert expected in errors_of(ds)


def test_copy_cannot_predate_its_origin(ds):
    # OBS-0000003 reposts OBS-0000002; move the repost before the original.
    mutate(ds, "observations", _set(2, ["published_at"], "2026-07-14T08:00:00+06:00"))
    assert "published before its origin" in errors_of(ds)


def test_dependence_cycle(ds):
    def fn(rows):
        rows.append({**rows[0], "obs_id": "OBS-0000002", "origin_obs_id": "OBS-0000003"})

    mutate(ds, "dependences", fn)
    errors = errors_of(ds)
    assert "cycle" in errors or "published before" in errors


def test_self_dependence(ds):
    mutate(ds, "dependences", _set(0, ["origin_obs_id"], "OBS-0000003"))
    assert "cannot depend on itself" in errors_of(ds)


def test_parent_cycle(ds):
    mutate(ds, "events", _set(0, ["parent_event_id"], "EVT-000002"))
    assert "parent_event_id cycle" in errors_of(ds)


def test_phone_numbers_are_rejected(ds):
    mutate(ds, "observations", _set(1, ["text"], "Call 01712345678 for help"))
    assert "phone number or email" in errors_of(ds)


def test_simulated_field_report_needs_simulated_field_source(ds):
    mutate(ds, "observations", _set(0, ["source_id"], "SRC-000003"))
    assert "simulated field source" in errors_of(ds)


def test_event_that_did_not_occur_cannot_end_verified(ds):
    mutate(ds, "events", _set(2, ["assessments", 1, "label"], "verified"))
    assert "did not occur" in errors_of(ds)


def test_assessments_in_time_order(ds):
    def fn(rows):
        rows[0]["assessments"].reverse()

    mutate(ds, "events", fn)
    assert "time order" in errors_of(ds)


def test_annotator_cannot_judge_twice(ds):
    def fn(rows):
        rows[0]["annotations"][1]["annotator"] = "ANN-001"

    mutate(ds, "relations", fn)
    assert "judged the same item twice" in errors_of(ds)


def test_duplicate_relation(ds):
    mutate(ds, "relations", lambda rows: rows.append(rows[0]))
    assert "duplicate relation" in errors_of(ds)


def test_invalid_json_line(ds):
    with (ds / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write("{not json\n")
    assert "invalid JSON" in errors_of(ds)


def test_missing_file(ds):
    (ds / "dependences.jsonl").unlink()
    assert "file is missing" in errors_of(ds)


def test_main_reports_failure(ds, capsys):
    mutate(ds, "events", _set(0, ["type"], "fire"))
    assert main([str(ds)]) == 1
    assert "FAILED" in capsys.readouterr().out
