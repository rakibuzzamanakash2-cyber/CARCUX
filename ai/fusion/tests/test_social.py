"""B7: social-sensing truth discovery (Wang et al. 2012, 2014)."""

from datetime import UTC, datetime, timedelta

from carcux_fusion import methods as M
from carcux_fusion.data import Dataset, Event, Evidence, Observation
from carcux_fusion.social import DENY, SILENT, SUPPORT, SocialSensing

T0 = datetime(2026, 7, 1, 8, tzinfo=UTC)


def world(n_true=6, n_false=6, extra=None):
    """Four honest sources confirm real events and deny false ones; one liar does the
    opposite. Each event also gets `extra` (event index -> [(obs, source, vote, copies)])."""
    events, obs, deps = {}, {}, {}
    k = 0
    for j in range(n_true + n_false):
        happened = j < n_true
        e = Event(f"E{j}", happened)
        speakers = [(f"S{i}", 1 if happened else -1) for i in range(4)]
        speakers.append(("LIAR", -1 if happened else 1))
        for s, vote in speakers:
            k += 1
            oid = f"O{k}"
            obs[oid] = Observation(oid, s, T0 + timedelta(minutes=k), "")
            e.evidence.append(Evidence(oid, vote))
        for oid, s, vote, copies in (extra or {}).get(j, []):
            obs[oid] = Observation(oid, s, T0 + timedelta(hours=1, minutes=k), "")
            e.evidence.append(Evidence(oid, vote))
            if copies:
                deps[oid] = (copies, "verbatim_copy")
        events[e.event_id] = e
    return Dataset(events, obs, {s: "social" for s in ("S0", "S1", "S2", "S3", "LIAR")}, deps)


def scores(method, data):
    ids = list(data.events)
    cutoffs = {e: T0 + timedelta(days=1) for e in ids}
    return method.raw(data, ids, cutoffs, data.dependences)


def test_finds_the_truth_and_the_liar_without_labels():
    data = world()
    for silence in (True, False):
        z = scores(SocialSensing(silence=silence), data)
        assert all(z[f"E{j}"] > 0 for j in range(6)), silence
        assert all(z[f"E{j}"] < 0 for j in range(6, 12)), silence


def test_labels_are_not_used():
    data = world()
    before = scores(SocialSensing(), data)
    for e in data.events.values():
        e.occurred = not e.occurred
    assert scores(SocialSensing(), data) == before


def test_a_copy_of_an_observation_in_view_drops_out():
    # On a false event, a parrot repeats the liar's (wrong) claim; another account
    # repeats it from an observation that is not in view, so it counts.
    extra = {
        6: [("C1", "PARROT", 1, "O35")],  # O35: the liar's report on E6 (5 per event)
        7: [("C2", "PARROT", 1, "MISSING")],
    }
    data = world(extra=extra)
    m = SocialSensing(dependence=True)
    events = list(data.events)
    sources, x, mask = m.observations(
        data, events, {e: T0 + timedelta(days=1) for e in events}, data.dependences
    )
    parrot = sources.index("PARROT")
    assert x[parrot, events.index("E6")] == SILENT  # dropped: its origin is in view
    assert x[parrot, events.index("E7")] == SUPPORT  # counted: origin not in view
    plain = SocialSensing()
    sources, x, _ = plain.observations(
        data, events, {e: T0 + timedelta(days=1) for e in events}, {}
    )
    assert x[sources.index("PARROT"), events.index("E6")] == SUPPORT


def test_silence_mask_and_latest_vote():
    data = world(extra={0: [("L1", "S0", -1, None)]})  # S0 changes its mind on E0
    events = list(data.events)
    cut = {e: T0 + timedelta(days=1) for e in events}
    sources, x, mask = SocialSensing(silence=False).observations(data, events, cut, {})
    assert x[sources.index("S0"), 0] == DENY  # the later vote stands
    assert mask.sum() == (x != SILENT).sum()
    _, _, all_pairs = SocialSensing(silence=True).observations(data, events, cut, {})
    assert all_pairs.all()


def test_registered_as_b7():
    names = [m.name for m in M.methods()]
    for name in ("socialsensing", "socialsensing-dep", "socialsensing-dep-nosilence"):
        assert name in names
