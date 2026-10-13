from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from carcux_correlation import features as F
from carcux_correlation import models
from carcux_correlation.data import Obs

T0 = datetime(2026, 7, 1, 8, tzinfo=UTC)


def obs(oid, text, hours=0.0, lat=23.71, lon=90.41, precision=50.0, etype="fire", events=("A",)):
    t = T0 + timedelta(hours=hours)
    return Obs(
        obs_id=oid,
        text=text,
        language="en",
        time=t,
        published=t,
        lat=lat,
        lon=lon,
        precision_m=precision if lat is not None else None,
        event_type=etype,
        events=set(events),
        roots=set(events),
        primary=events[0],
    )


def test_haversine_dhaka_to_chattogram():
    km = F.haversine_km(23.7115, 90.4111, 22.3351, 91.8341)
    assert 205 < km < 215


def test_unlocated_pair_gets_neutral_place_features():
    a = obs("1", "fire", lat=None, lon=None)
    b = obs("2", "fire")
    f = dict(zip(F.NAMES, F.pair_features(a, b, 0.5), strict=True))
    assert f["both_located"] == 0.0
    assert f["log_km"] == f["log_scaled_km"] == 0.0


def test_imprecise_locations_shrink_scaled_distance():
    a, b = obs("1", "x", lat=23.70), obs("2", "x", lat=23.80)
    precise = dict(zip(F.NAMES, F.pair_features(a, b, 0), strict=True))
    a.precision_m = b.precision_m = 30000
    vague = dict(zip(F.NAMES, F.pair_features(a, b, 0), strict=True))
    assert precise["log_km"] == vague["log_km"]
    assert vague["log_scaled_km"] < precise["log_scaled_km"]


def test_text_similarity_is_symmetric_with_unit_diagonal():
    sim = F.TextEncoder().similarity(["fire in market", "market fire", "", "বন্যা"])
    assert np.allclose(sim, sim.T)
    assert np.allclose(np.diag(sim), 1.0)
    assert sim[0, 1] > sim[0, 3]


def test_cluster_threshold_extremes():
    s = np.array([[1, 0.9, 0.1], [0.9, 1, 0.2], [0.1, 0.2, 1]])
    assert models.cluster(s, 0.5) == [0, 0, 1]
    assert models.cluster(s, 0.0) == [0, 0, 0]
    assert models.cluster(s, 0.95) == [0, 1, 2]


def test_average_linkage_is_stricter_than_max():
    # Item 2 is close to item 1 but far from item 0.
    s = np.array([[1, 0.9, 0.1], [0.9, 1, 0.8], [0.1, 0.8, 1]])
    assert models.cluster(s, 0.6, "average") == [0, 0, 1]
    assert models.cluster(s, 0.6, "max") == [0, 0, 0]


def test_rules_baseline_cuts_far_and_late_pairs():
    o = [
        obs("1", "market fire in Dhaka"),
        obs("2", "market fire in Dhaka", hours=72),  # too late
        obs("3", "market fire in Dhaka", lat=22.33, lon=91.83),  # Chattogram: too far
        obs("4", "market fire in Dhaka", lat=None, lon=None),  # place unknown: kept
    ]
    feats = F.matrix(o)
    idx = list(range(4))
    text = models.TextOnly().scores(o, feats, idx)
    rules = models.TextThenRules().scores(o, feats, idx)
    assert text[0, 1] > 0.9
    assert rules[0, 1] == 0.0
    assert rules[0, 2] == 0.0
    assert rules[0, 3] == pytest.approx(text[0, 3])


def test_joint_learns_that_place_and_time_matter():
    rng = np.random.default_rng(0)
    o = []
    for e in range(12):
        lat, lon, h = 22 + rng.random() * 3, 89 + rng.random() * 3, e * 60.0
        for k in range(3):
            o.append(
                obs(
                    f"{e}-{k}", f"fire report {k}", hours=h + k, lat=lat, lon=lon, events=(f"E{e}",)
                )
            )
    feats = F.matrix(o)
    idx = list(range(len(o)))
    joint = models.Joint().fit(o, feats, idx)
    w = joint.weights()
    assert w["log_km"] + w["log_scaled_km"] < 0
    assert w["log_hours"] < 0
    pred = models.cluster(joint.scores(o, feats, idx), 0.5)
    assert len(set(pred)) == 12


def test_joint_refuses_single_class_training():
    o = [obs("1", "a"), obs("2", "b")]
    with pytest.raises(ValueError):
        models.Joint().fit(o, F.matrix(o), [0, 1])


def test_tuned_threshold_recovers_clean_split():
    s = np.array([[1, 0.9, 0.1], [0.9, 1, 0.2], [0.1, 0.2, 1]])
    t = models.tune_threshold(s, [{"A"}, {"A"}, {"B"}])
    assert models.cluster(s, t) == [0, 0, 1]
