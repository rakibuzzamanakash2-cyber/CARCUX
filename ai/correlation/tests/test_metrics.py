import pytest

from carcux_correlation.metrics import bcubed, pairwise, score


def test_perfect_grouping_scores_one():
    gold = [{"A"}, {"A"}, {"B"}]
    s = score([0, 0, 1], gold, ["A", "A", "B"])
    assert (s.pair_f1, s.bcubed_f1, s.ari) == (1.0, 1.0, 1.0)
    assert s.clusters == s.gold_groups == 2


def test_everything_in_one_cluster():
    gold = [{"A"}, {"A"}, {"B"}, {"B"}]
    p, r, f = pairwise([0, 0, 0, 0], gold)
    # 6 predicted pairs, 2 of them true.
    assert p == pytest.approx(2 / 6)
    assert r == 1.0
    bp, br, _ = bcubed([0, 0, 0, 0], gold)
    assert bp == pytest.approx(0.5)
    assert br == 1.0


def test_all_singletons():
    gold = [{"A"}, {"A"}, {"B"}]
    p, r, _ = pairwise([0, 1, 2], gold)
    assert p == 1.0  # no predicted pairs: nothing wrong on that side
    assert r == 0.0
    bp, br, _ = bcubed([0, 1, 2], gold)
    assert bp == 1.0
    assert br == pytest.approx((0.5 + 0.5 + 1) / 3)


def test_overlapping_gold_counts_shared_event_as_positive():
    # The middle report is about both the waterlogging (W) and the blockage (R).
    gold = [{"W"}, {"W", "R"}, {"R"}]
    p, r, _ = pairwise([0, 0, 1], gold)
    assert (p, r) == (1.0, pytest.approx(1 / 2))
    # Grouping all three is wrong only for the W-R pair.
    p, r, _ = pairwise([0, 0, 0], gold)
    assert (p, r) == (pytest.approx(2 / 3), 1.0)


def test_extended_bcubed_matches_plain_bcubed_without_overlap():
    gold = [{"A"}, {"A"}, {"B"}, {"B"}, {"B"}]
    pred = [0, 1, 1, 1, 2]
    bp, br, _ = bcubed(pred, gold)
    # Plain B-cubed by hand.
    precision = [1, 1 / 3, 2 / 3, 2 / 3, 1]
    recall = [1 / 2, 1 / 2, 2 / 3, 2 / 3, 1 / 3]
    assert bp == pytest.approx(sum(precision) / 5)
    assert br == pytest.approx(sum(recall) / 5)


def test_empty_input():
    assert bcubed([], []) == (1.0, 1.0, 1.0)
