from carcux_integrity.evaluate import _auc, run, summarise, table
from carcux_integrity.simulate import SCENARIOS, simulate


def test_simulation_is_reproducible_and_labelled():
    a, b = simulate(workers=12, compromised=6, seed=1), simulate(workers=12, compromised=6, seed=1)
    assert [r.text for r in a.reports] == [r.text for r in b.reports]
    assert sorted(a.scenario.values()) == sorted(SCENARIOS)
    assert a.injected and all(a.report_scenario[i] in SCENARIOS for i in a.injected)


def test_auc():
    assert _auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert _auc([0.5], [0.5]) == 0.5
    assert _auc([], [0.1]) is None


def test_small_run_end_to_end():
    s = summarise([run(0, workers=12, compromised=6)])
    assert s["accounts"] == {"misused": 6, "ordinary": 6}
    # Reused photos and copied rumours are caught; the night shift only by the account score.
    assert s["scenario_recall"]["old_photos"] == 1.0
    assert s["scenario_recall"]["copier"] == 1.0
    assert s["scenario_recall"]["night_shift"] == 0.0
    assert s["account_auc"] > 0.7
    assert "Account score" in table(s)
