"""The simulator's output is a valid CARCUX-BD dataset, and evaluation runs on it."""

import json
from pathlib import Path

import pytest

from carcux_correlation import evaluate, simulate
from carcux_correlation.data import load
from carcux_data.validate import validate_dir

REPO = Path(__file__).resolve().parents[3]
SAMPLE = REPO / "data" / "samples" / "v1" / "example"


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim")
    simulate.generate(out, events=20, seed=3)
    return out


def test_simulated_set_passes_the_validator(sim):
    report = validate_dir(sim)
    assert not report.errors, report.errors[:5]


def test_simulation_is_seeded(sim, tmp_path):
    simulate.generate(tmp_path, events=20, seed=3)
    for name in ("events.jsonl", "observations.jsonl", "relations.jsonl"):
        assert (tmp_path / name).read_text() == (sim / name).read_text()


def test_every_simulated_record_says_so(sim):
    for line in (sim / "observations.jsonl").read_text().splitlines():
        assert json.loads(line)["is_simulated"] is True
    for line in (sim / "events.jsonl").read_text().splitlines():
        ev = json.loads(line)
        assert ev["title"].startswith("[SIMULATED]")
        assert all(
            s["reference"].startswith("https://example.org/simulated/")
            for s in ev["ground_truth"]["sources"]
        )


def test_loader_reads_overlap_and_folds_children(sim):
    data = load(sim)
    events = {e["event_id"]: e for e in data.events.values()}
    assert data.unannotated == 0
    assert all(o.events for o in data.observations)
    for o in data.observations:
        assert o.primary in o.roots
        assert all("parent_event_id" not in events[r] for r in o.roots)
    times = [o.published for o in data.observations]
    assert times == sorted(times)


def test_evaluate_runs_end_to_end(sim, tmp_path):
    out = tmp_path / "result.json"
    assert evaluate.main([str(sim), "--folds", "3", "--json", str(out)]) == 0
    result = json.loads(out.read_text())
    assert set(result["methods"]) == {"text", "text+rules", "joint", "joint-space", "joint-time"}
    for summary in result["methods"].values():
        assert summary["folds"] == 3
        assert 0 <= summary["bcubed_f1"]["mean"] <= 1


def test_evaluate_on_the_repository_sample():
    data = load(SAMPLE)
    result = evaluate.run(data, folds=3, seed=0)
    assert result["observations"] == len(data.observations)


def test_evaluate_needs_two_events(tmp_path):
    simulate.generate(tmp_path, events=1, seed=0)
    data = load(tmp_path)
    data.observations = [o for o in data.observations if o.primary == data.observations[0].primary]
    with pytest.raises(ValueError):
        evaluate.run(data)
