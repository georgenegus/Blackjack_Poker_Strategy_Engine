"""Phase 6: card abstraction. See
.agents/skills/poker_solver_conventions/SKILL.md and
markdowns/poker/poker_build_plan_v1.md Phase 6.
"""

from itertools import combinations

from src.poker.abstraction import flop_buckets, hand_strength_feature, preflop_buckets
from src.poker.cards import card_ids


def test_preflop_buckets_are_lossless_169_classes():
    buckets = preflop_buckets()
    assert len(buckets) == 1326  # one entry per concrete starting-hand combo
    assert len(set(buckets)) == 169


def test_preflop_buckets_match_canonical_class_grouping():
    """Two combos land in the same bucket iff they're the same canonical
    class -- e.g. every AA combo together, separate from every AKs combo."""
    combos = list(combinations(range(52), 2))
    buckets = preflop_buckets()
    bucket_of = dict(zip(combos, buckets))

    aa_combos = [c for c in combos if c[0] // 4 == 12 and c[1] // 4 == 12]
    assert len(aa_combos) == 6
    assert len({bucket_of[c] for c in aa_combos}) == 1  # all 6 AA combos share one bucket

    aa_bucket = bucket_of[aa_combos[0]]
    ak_combo = tuple(sorted(card_ids("AsKs")))
    assert bucket_of[ak_combo] != aa_bucket


def test_hand_strength_feature_ranks_hands_sensibly():
    """Pocket aces should score far higher than the worst starting hand
    against a random opponent, with no board."""
    aa = hand_strength_feature(tuple(sorted(card_ids("AsAh"))), (), n_samples=4000, seed=1)
    trash = hand_strength_feature(tuple(sorted(card_ids("7s2d"))), (), n_samples=4000, seed=1)
    assert aa > 0.75
    assert trash < 0.5
    assert aa > trash


def test_hand_strength_feature_is_bounded():
    for hole_str in ("AsAh", "7s2d", "AsKs"):
        f = hand_strength_feature(tuple(sorted(card_ids(hole_str))), (), n_samples=1000, seed=2)
        assert 0.0 <= f <= 1.0


def test_flop_buckets_covers_every_valid_combo_and_respects_k():
    board = tuple(sorted(card_ids("2s7hTd")))
    k = 6
    buckets = flop_buckets(board, k=k, n_samples=200, seed=3)

    # every remaining combo (not conflicting with the board) is covered exactly once
    expected_combos = {c for c in combinations(range(52), 2) if not (set(c) & set(board))}
    assert set(buckets.keys()) == expected_combos
    assert len(buckets) == 1176  # C(49, 2)

    assert 1 <= len(set(buckets.values())) <= k


def test_flop_buckets_separates_strong_and_weak_hands():
    """A strong made hand (top set) and a weak hand (bottom pair no kicker
    relative to the board texture) should not be forced into the same
    bucket by a degenerate clustering."""
    board = tuple(sorted(card_ids("2s7hTd")))
    buckets = flop_buckets(board, k=6, n_samples=800, seed=4)
    top_set = tuple(sorted(card_ids("TsTh")))  # trips on this board
    weak = tuple(sorted(card_ids("3c4d")))  # no pair, no draw
    assert buckets[top_set] != buckets[weak]
