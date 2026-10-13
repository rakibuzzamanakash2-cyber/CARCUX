from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from carcux_correlation import cluster_model as CM
from carcux_correlation import evaluate, simulate, stream
from carcux_correlation.data import Obs, load
from carcux_correlation.features import haversine_km

T0 = datetime(2026, 7, 1, tzinfo=UTC)


def _obs(oid, text, hours, story, lat=None, lon=None, etype=None):
    t = T0 + timedelta(hours=hours)
    return Obs(
        obs_id=oid,
        text=text,
        language="en",
        time=t,
        published=t,
        lat=lat,
        lon=lon,
        precision_m=100.0 if lat is not None else None,
        event_type=etype,
        events={story},
        roots={story},
        primary=story,
    )


@pytest.fixture(scope="module")
def sim_stream(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim")
    simulate.generate(out, events=15, seed=7)
    obs = load(out).observations
    vec = stream.make_vectorizer("char")
    vec.set_params(min_df=1)
    vec.fit([o.text.lower() for o in obs])
    return stream.build(obs, vec)


def test_cluster_features_match_brute_force(sim_stream):
    s = sim_stream
    vectors = s.vectors.toarray()
    st = CM.State(len(s))
    seen: dict[str, int] = {}
    for i, f in stream.rows(s):
        if st.m:
            every = np.arange(st.m)
            x, cands, dot = CM.features(s, i, f, st, clusters=every)
            for c in every:
                members = np.flatnonzero(st.labels[:i] == c)
                total = vectors[members].sum(axis=0)
                cos = vectors[members] @ vectors[i]
                want = {
                    "centroid_cos": float(vectors[i] @ total / np.linalg.norm(total)),
                    "max_cos": float(np.clip(cos, 0, 1).max()),
                    "log_hours_newest": np.log1p(s.hours[i] - s.hours[members].max()),
                    "log_hours_oldest": np.log1p(s.hours[i] - s.hours[members].min()),
                    "log_size": np.log(len(members)),
                }
                located = [j for j in members if s.located[j]] if s.located[i] else []
                want["any_located"] = float(bool(located))
                if located:
                    km = min(haversine_km(s.lat[i], s.lon[i], s.lat[j], s.lon[j]) for j in located)
                    want["log_min_km"] = np.log1p(km)
                for name, value in want.items():
                    assert x[c, CM.NC[name]] == pytest.approx(value, abs=1e-6), (i, c, name)
            # The default call retrieves the most text-similar clusters, best first.
            _, top, _ = CM.features(s, i, f, st)
            centroid = x[:, CM.NC["centroid_cos"]]
            assert centroid[top].tolist() == sorted(centroid, reverse=True)[: len(top)]
        c = seen.setdefault(s.gold[i], st.m)
        dot_c = float(CM.features(s, i, f, st, clusters=[c])[2][c]) if c < st.m else 0.0
        st.add(i, c, s.hours[i], dot_c)


def test_training_data_has_one_positive_per_continuing_item(sim_stream):
    x, y = CM.ClusterJoint().training_data(sim_stream)
    gold = sim_stream.gold
    continuing = sum(gold[i] in gold[:i] for i in range(len(gold)))
    assert int(y.sum()) == continuing
    assert x.shape == (len(y), len(CM.NAMES))


def test_long_running_stories_stay_together():
    """The failure seen on the news benchmark: stories that run for weeks were split by
    the pair-level joint model. Two training and two test streams of three stories,
    one article every 20 hours for 40 days, interleaved."""

    def make(prefix, offset):
        obs = []
        for k in range(48):
            for st, words in enumerate(
                ["flood river embankment", "garment factory strike", "metro rail construction"]
            ):
                obs.append(
                    _obs(
                        f"{prefix}{st}-{k}",
                        f"{words} update {k} {prefix}",
                        offset + k * 20 + st,
                        f"{prefix}{st}",
                    )
                )
        return obs

    vec = stream.make_vectorizer("word")
    vec.set_params(min_df=1)
    train_obs, test_obs = make("a", 0), make("b", 2000)
    vec.fit([o.text.lower() for o in train_obs])
    train, test = stream.build(train_obs, vec), stream.build(test_obs, vec)
    outcomes = {
        o.method: o.test for o in stream.run(train, test, [CM.ClusterJoint(label="cjoint")])
    }
    assert outcomes["cjoint"].clusters <= 6
    assert outcomes["cjoint"].bcubed_f1 > 0.8


def test_evaluate_includes_cluster_methods(tmp_path):
    simulate.generate(tmp_path, events=15, seed=2)
    result = evaluate.run(load(tmp_path), folds=3, seed=0)
    for name in ("ctext", "cjoint", "cjoint-space", "cjoint-time"):
        assert result["methods"][name]["folds"] == 3
