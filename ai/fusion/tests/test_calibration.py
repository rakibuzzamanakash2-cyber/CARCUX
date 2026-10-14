import json

import numpy as np
import pytest

from carcux_fusion import calibrate, metrics, simulate
from carcux_fusion.data import load


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim")
    simulate.generate(out, events=50, contamination=0.3, seed=4)
    return out


@pytest.fixture(scope="module")
def result(sim):
    return calibrate.run(load(sim), k=3)


# --- Metrics -------------------------------------------------------------------------------


def test_adaptive_ece_zero_when_calibrated_and_large_when_not():
    p = np.array([0.2] * 10 + [0.8] * 10)
    y = np.array([1, 1] + [0] * 8 + [1] * 8 + [0, 0])
    assert metrics.ece_adaptive(p, y, bins=2) == pytest.approx(0.0)
    assert metrics.ece_adaptive(np.full(4, 0.9), np.zeros(4)) == pytest.approx(0.9)
    assert metrics.ece_adaptive(np.array([]), np.array([])) == 0.0


# --- Calibrators -----------------------------------------------------------------------------


def _toy(n=400, scale=3.0, seed=0):
    """Scores that are log-odds three times too large: overconfident when read as is."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.5, n)
    y = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)
    return (scale * z).tolist(), y.tolist()


@pytest.mark.parametrize("kind", ["temperature", "platt", "isotonic"])
def test_learned_calibration_repairs_overconfident_scores(kind):
    s, y = _toy()
    st, yt = _toy(seed=1)
    raw = calibrate.fit("none", s, y)(st)
    fitted = calibrate.fit(kind, s, y)(st)
    assert metrics.ece_adaptive(fitted, np.array(yt)) < metrics.ece_adaptive(raw, np.array(yt))
    assert ((fitted >= 0) & (fitted <= 1)).all()


def test_temperature_learns_the_scale():
    s, y = _toy(n=4000)
    p = calibrate.fit("temperature", s, y)(np.array([3.0]))
    assert p[0] == pytest.approx(1 / (1 + np.exp(-1.0)), abs=0.05)


def test_calibrators_take_two_channel_scores():
    rng = np.random.default_rng(2)
    s = rng.normal(0, 2, (200, 2))
    y = (s[:, 0] + 0.3 * s[:, 1] + rng.normal(0, 1, 200) > 0).astype(int)
    for kind in calibrate.CALIBRATORS[:4]:
        p = calibrate.fit(kind, s.tolist(), y.tolist())(s.tolist())
        assert p.shape == (200,)


def test_one_class_training_gives_its_base_rate():
    assert calibrate.fit("platt", [1.0, 2.0], [1, 1])([0.0, -5.0]).tolist() == [1.0, 1.0]


def test_unknown_calibrator():
    with pytest.raises(ValueError):
        calibrate.fit("magic", [0.0, 1.0], [0, 1])


# --- Study -----------------------------------------------------------------------------------


def test_every_method_and_calibrator_is_scored(result):
    for block in result["calibration"]["checkpoints"].values():
        assert set(block["methods"]) == {m.name for m in calibrate.method_list()}
        for by_cal in block["methods"].values():
            assert set(by_cal) == set(calibrate.CALIBRATORS)
            for c, s in by_cal.items():
                assert 0 <= s["ece_adaptive"] <= 1 and -1 <= s["bias"] <= 1
                assert (s["brier_vs_platt"] is None) == (c == calibrate.REFERENCE)
                assert sum(b["n"] for b in s["reliability"]) == result["events"]


def test_one_calibrator_for_all_times_equals_platt_at_final(result):
    final = result["calibration"]["checkpoints"]["final"]["methods"]
    for by_cal in final.values():
        assert by_cal["platt-final"]["brier"] == pytest.approx(by_cal["platt"]["brier"])


def test_labels_cover_every_scored_event(result):
    for block in result["labels"]["checkpoints"].values():
        assert sum(s["n"] for s in block["by_label"].values()) > 0
        assert set(block["occurrence"]) == set(calibrate.SIGNALS)
        assert set(block["signals_vs_probability"]) == set(list(calibrate.SIGNALS)[1:])


def test_dispute_is_not_used_to_predict_occurrence():
    """In the simulator only real events have disputed details: using it would leak."""
    row = {"p": 0.7, "support": 1, "deny": 1, "seen": 3, "detected": True}
    assert calibrate._features(row, ("both", "count")) == calibrate._features(
        {**row, "detected": False}, ("both", "count")
    )


def test_cli_dataset_and_json(sim, tmp_path, capsys):
    out = tmp_path / "c.json"
    assert calibrate.main([str(sim), "--folds", "3", "--json", str(out)]) == 0
    assert "Brier vs platt" in capsys.readouterr().out
    assert set(json.loads(out.read_text())) == {"dataset", "events", "calibration", "labels"}


def test_cli_needs_a_dataset_or_simulate():
    with pytest.raises(SystemExit):
        calibrate.main([])


def test_sweep_tables_and_figures(tmp_path, monkeypatch):
    summary = calibrate.sweep([0.0, 0.3], seeds=1, events=40, log=lambda *_: None)
    text = calibrate.sweep_table(summary, "final")
    assert "platt-clean" in text and "partially_verified" in text
    bins = calibrate.pooled_reliability(summary, 0.3, "final", "platt")
    assert sum(b["n"] for b in bins) == summary["runs"][1]["result"]["events"]
    pytest.importorskip("matplotlib")
    paths = calibrate.figures(summary, tmp_path)
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)
