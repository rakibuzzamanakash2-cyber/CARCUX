import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from carcux_data.validate import validate_dir
from carcux_fusion import dependence, evaluate, metrics, simulate, sweep
from carcux_fusion import methods as M
from carcux_fusion.data import Dataset, Event, Evidence, Observation, load

T0 = datetime(2026, 7, 1, 8, tzinfo=UTC)


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim")
    simulate.generate(out, events=40, contamination=0.3, seed=4)
    return out


# --- Simulator ---------------------------------------------------------------------------


def test_simulated_set_is_valid_carcux_bd(sim):
    report = validate_dir(sim)
    assert not report.errors, report.errors[:5]


def test_simulation_is_seeded(sim, tmp_path):
    simulate.generate(tmp_path, events=40, contamination=0.3, seed=4)
    for name in ("events.jsonl", "observations.jsonl", "dependences.jsonl"):
        assert (tmp_path / name).read_text() == (sim / name).read_text()


@pytest.mark.parametrize("c", [0.0, 0.3, 0.6])
def test_contamination_share_is_what_was_asked(tmp_path, c):
    simulate.generate(tmp_path, events=60, contamination=c, seed=2)
    rows = [json.loads(x) for x in (tmp_path / "observations.jsonl").read_text().splitlines()]
    clean = simulate._Sim(60, 0.0, 2)
    clean.run()
    injected = len(rows) - len(clean.items)
    assert injected / len(rows) == pytest.approx(c, abs=0.03)


def test_contamination_out_of_range_is_refused(tmp_path):
    with pytest.raises(ValueError):
        simulate.generate(tmp_path, contamination=0.7)


def test_every_record_says_it_is_simulated(sim):
    for line in (sim / "sources.jsonl").read_text().splitlines():
        s = json.loads(line)
        assert s["is_simulated"] and "simulated" in s["name"]
    for line in (sim / "events.jsonl").read_text().splitlines():
        assert json.loads(line)["title"].startswith("[SIMULATED]")


def test_loader_reads_votes_truth_and_copies(sim):
    data = load(sim)
    assert data.dependences
    assert any(e.occurred for e in data.events.values())
    assert any(not e.occurred for e in data.events.values())
    for child, (origin, _) in data.dependences.items():
        assert data.observations[origin].published <= data.observations[child].published
    for e in data.events.values():
        times = [data.observations[v.obs_id].published for v in e.evidence]
        assert times == sorted(times) and all(v.vote in (1, -1) for v in e.evidence)


# --- Metrics ------------------------------------------------------------------------------


def test_metrics_on_known_values():
    s = metrics.score([1.0, 0.0, 1.0, 0.0], [1, 0, 1, 0])
    assert s.brier == pytest.approx(0, abs=1e-9) and s.accuracy == 1 and s.auc == 1
    s = metrics.score([0.5] * 4, [1, 0, 1, 0])
    assert s.brier == pytest.approx(0.25) and s.ece == pytest.approx(0.0)
    # Always 0.9 but only half happen: miscalibrated by 0.4.
    assert metrics.ece(np.full(10, 0.9), np.array([1, 0] * 5)) == pytest.approx(0.4)


def test_reliability_bins_count_everything():
    p, y = np.linspace(0, 1, 50), np.arange(50) % 2
    assert sum(b["n"] for b in metrics.reliability(p, y)) == 50


# --- Hand-made evidence ---------------------------------------------------------------------


def _ds() -> Dataset:
    def ob(oid, src, minutes, text, ph=()):
        return Observation(oid, src, T0 + timedelta(minutes=minutes), text, ph)

    obs = {
        "OBS-0000001": ob(
            "OBS-0000001",
            "SRC-1",
            0,
            "fire at the kawran bazar kitchen market now",
            ("00000000000000ff",),
        ),
        "OBS-0000002": ob(
            "OBS-0000002", "SRC-2", 10, "fire at the kawran bazar kitchen market now"
        ),
        "OBS-0000003": ob(
            "OBS-0000003",
            "SRC-3",
            20,
            "smoke rising behind tejgaon college gate",
            ("00000000000000fe",),
        ),
        "OBS-0000004": ob("OBS-0000004", "SRC-4", 30, "According to SRC-1, fire at kawran bazar"),
        "OBS-0000005": ob("OBS-0000005", "SRC-5", 40, "no fire anywhere, that was a drill"),
    }
    ev = Event("EVT-000001", True, [Evidence(o, -1 if o.endswith("5") else 1) for o in obs])
    return Dataset(
        events={ev.event_id: ev},
        observations=obs,
        source_type={
            f"SRC-{k}": t
            for k, t in enumerate(["", "field", "social", "field", "news", "social"])
            if k
        },
        dependences={
            "OBS-0000002": ("OBS-0000001", "verbatim_copy"),
            "OBS-0000003": ("OBS-0000001", "same_media"),
            "OBS-0000004": ("OBS-0000001", "cites"),
        },
    )


def test_detector_finds_text_media_and_attribution_copies():
    data = _ds()
    found = dependence.Detector(data, threshold=0.8).detect(data.events)
    assert set(found) == {"OBS-0000002", "OBS-0000003", "OBS-0000004"}
    assert found["OBS-0000003"] == ("OBS-0000001", "same_media")
    assert found["OBS-0000004"][1] == "cites"
    s = dependence.score(found, data, list(data.events))
    assert (s["precision"], s["recall"], s["origin_in_cascade"]) == (1.0, 1.0, 1.0)


def test_hamming():
    assert dependence.hamming("00000000000000ff", "00000000000000fe") == 1


def test_votes_follow_cascades_and_count_each_once():
    data = _ds()
    vs = M.votes(data, data.events["EVT-000001"], T0 + timedelta(hours=1), data.dependences)
    assert {v.obs_id: v.root for v in vs}["OBS-0000004"] == "OBS-0000001"
    once = M.independent(vs)
    assert sorted(v.obs_id for v in once) == ["OBS-0000001", "OBS-0000005"]
    early = M.votes(data, data.events["EVT-000001"], T0 + timedelta(minutes=15), None)
    assert len(early) == 2


def test_simple_scorers():
    data = _ds()
    cut = {"EVT-000001": T0 + timedelta(hours=1)}
    assert M.Equal().raw(data, cut, cut, {})["EVT-000001"] == 3.0
    assert M.Majority().raw(data, cut, cut, {})["EVT-000001"] > 0


def test_platt_takes_one_or_two_scores():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, 2))
    y = (x[:, 0] + 0.3 * x[:, 1] > 0).astype(int)
    p = M.Platt().fit(x, y).predict(x)
    assert ((p > 0.5) == y).mean() > 0.9
    one = M.Platt().fit(x[:, 0], y).predict(x[:, 0])
    assert one.shape == (200,)
    assert np.all(M.Platt().fit([1.0, 2.0], [1, 1]).predict([0.0]) == 1.0)


def test_two_channel_model_learns_amplifiers(sim):
    data = load(sim)
    model = M.Reliability("gold").fit(data, list(data.events), {}, data.dependences)
    # Rumour accounts pass on mostly false claims: their copy-channel rate is low.
    rumour = [
        s for s, t in data.source_type.items() if t == "social" and model.rate(s, copy=True) < 0.4
    ]
    assert rumour
    cut = {e: datetime.max.replace(tzinfo=UTC) for e in data.events}
    raw = model.raw(data, data.events, cut, data.dependences)
    assert all(isinstance(v, tuple) and len(v) == 2 for v in raw.values())


# --- Evaluation ----------------------------------------------------------------------------


def test_evaluate_end_to_end(sim, tmp_path):
    out = tmp_path / "r.json"
    assert evaluate.main([str(sim), "--folds", "4", "--json", str(out)]) == 0
    r = json.loads(out.read_text())
    assert set(r["checkpoints"]) == {"T+1h", "T+6h", "T+24h", "final"}
    final = r["checkpoints"]["final"]
    assert {m.name for m in M.methods()} == set(final["methods"])
    for s in final["methods"].values():
        assert 0 <= s["brier"] <= 1 and 0 <= s["ece"] <= 1
    assert evaluate.PROPOSED not in final["brier_vs_proposed"]
    assert 0 <= r["detection"]["f1"] <= 1
    # Learned reliability beats a plain majority when a third of the items are injected.
    assert final["methods"]["reliability-dep"]["brier"] < final["methods"]["majority"]["brier"]


def test_evaluate_needs_both_outcomes(tmp_path, capsys):
    data = _ds()
    with pytest.raises(ValueError):
        evaluate.run(data, k=1)


def test_paired_bootstrap_signs():
    c = evaluate.paired_bootstrap([0.3] * 50, [0.1] * 50)
    assert c["diff"] == pytest.approx(-0.2) and c["ci_high"] < 0


def test_sweep_summarises_levels():
    summary = sweep.run(levels=[0.0, 0.4], seeds=1, events=30, folds=3, log=lambda m: None)
    assert summary["levels"] == [0.0, 0.4]
    final = summary["checkpoints"]["final, clean events"]
    assert set(final["majority"]) == {"0.0", "0.4"}
    assert "copy detection F1" in sweep.table(summary)
