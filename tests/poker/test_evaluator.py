"""Phase 5, Checks 1-3: the evaluator is either exact or subtly, invisibly
wrong -- these tests admit no tolerance, because the reference answers are
combinatorial facts about C(52,7)/C(52,5), not published figures.

See .agents/skills/poker_evaluator_conventions/SKILL.md and
markdowns/poker/poker_build_plan_v1.md Appendix A.1/A.2.

Check 2 (two independent evaluators agree) is reformulated from the plan's
original "Strategy A vs Strategy B" framing: Strategy B (the 124MB 7-card DAG
table) was never built, because Strategy A's numba-accelerated batch
evaluator (~6.9M hands/sec) turned out fast enough on its own -- the
"escalate only if needed" clause in evaluator.py's own docstring never
triggered for a second table. The reference used here instead is
_classify5(): pure rank/suit rule logic with zero lookup-table involvement,
run independently over every 5-card subset of a sampled hand. It catches a
different bug class than Check 1 (table-construction/lookup-machinery bugs,
not classification-rule bugs -- Check 1's exact category counts are what
catch those), so the two checks together give comparable coverage to the
plan's original two-implementation design.
"""

from itertools import combinations, islice

import numpy as np
import pytest

from src.poker.cards import card_ids
from src.poker.evaluator import (
    HandCategory,
    _classify5,
    category,
    category_batch,
    distinct_five_card_values,
    evaluate,
    evaluate5,
    evaluate_batch,
)

FIVE_CARD_CATEGORY_COUNTS = {
    HandCategory.STRAIGHT_FLUSH: 40,
    HandCategory.FOUR_OF_A_KIND: 624,
    HandCategory.FULL_HOUSE: 3744,
    HandCategory.FLUSH: 5108,
    HandCategory.STRAIGHT: 10200,
    HandCategory.THREE_OF_A_KIND: 54912,
    HandCategory.TWO_PAIR: 123552,
    HandCategory.ONE_PAIR: 1098240,
    HandCategory.HIGH_CARD: 1302540,
}

SEVEN_CARD_CATEGORY_COUNTS = {
    HandCategory.STRAIGHT_FLUSH: 41584,
    HandCategory.FOUR_OF_A_KIND: 224848,
    HandCategory.FULL_HOUSE: 3473184,
    HandCategory.FLUSH: 4047644,
    HandCategory.STRAIGHT: 6180020,
    HandCategory.THREE_OF_A_KIND: 6461620,
    HandCategory.TWO_PAIR: 31433400,
    HandCategory.ONE_PAIR: 58627800,
    HandCategory.HIGH_CARD: 23294460,
}


def _batch_category_counts(chunk_size: int, n_cards: int, cat_totals: np.ndarray) -> None:
    it = combinations(range(52), n_cards)
    while True:
        batch = list(islice(it, chunk_size))
        if not batch:
            return
        arr = np.array(batch, dtype=np.int64)
        vals = evaluate_batch(arr) if n_cards == 7 else np.array([evaluate5(h) for h in batch], dtype=np.int32)
        cats = category_batch(vals)
        cat_totals += np.bincount(cats, minlength=9)


# --- Check 3: five-card category counts and distinct-value count -----------


def test_five_card_category_counts_exact():
    """All C(52,5) = 2,598,960 five-card hands, classified exactly -- no
    tolerance. Catches perfect-hash collisions Check 1 alone could mask."""
    cat_totals = np.zeros(9, dtype=np.int64)
    _batch_category_counts(chunk_size=500_000, n_cards=5, cat_totals=cat_totals)

    assert cat_totals.sum() == 2_598_960
    for cat, expected in FIVE_CARD_CATEGORY_COUNTS.items():
        assert cat_totals[cat.value] == expected, f"{cat.name}: got {cat_totals[cat.value]}, expected {expected}"


def test_distinct_five_card_values_is_7462():
    assert distinct_five_card_values() == 7462


# --- Check 1: full seven-card category enumeration --------------------------


def test_seven_card_category_counts_exact():
    """All C(52,7) = 133,784,560 seven-card hands, classified exactly. The
    plan anticipated this needing @pytest.mark.slow with a stratified
    subsample in --fast mode ("with pure Python it is hours"); the
    numba-accelerated evaluator (added when Phase 3's preflop-matrix build
    needed it) runs the FULL enumeration in ~83s measured, well within normal
    test-suite budget, so no slow marker or subsampling is needed here."""
    cat_totals = np.zeros(9, dtype=np.int64)
    _batch_category_counts(chunk_size=2_000_000, n_cards=7, cat_totals=cat_totals)

    assert cat_totals.sum() == 133_784_560
    for cat, expected in SEVEN_CARD_CATEGORY_COUNTS.items():
        assert cat_totals[cat.value] == expected, f"{cat.name}: got {cat_totals[cat.value]}, expected {expected}"


# --- Check 2 (reformulated): table-based evaluator vs a from-first-principles
#     classification reference, on a large deterministic sample -----------------


def _direct_evaluate7(cards) -> tuple:
    """Reference 7-card evaluation using ONLY _classify5 (pure rank/suit
    rules) -- no lookup table anywhere in this call path."""
    ranks_full = [c >> 2 for c in cards]
    suits_full = [c & 3 for c in cards]
    best = None
    for idxs in combinations(range(7), 5):
        ranks5 = [ranks_full[i] for i in idxs]
        suits5 = [suits_full[i] for i in idxs]
        key = _classify5(ranks5, suits5)
        if best is None or key < best:
            best = key
    return best


def test_table_evaluator_agrees_with_direct_classification_reference():
    """A deterministic stride-400 sample of C(52,7) (334,462 hands, ~1-in-400
    coverage spanning the full enumeration order) -- the direct reference is
    too slow in pure Python to run at full 133.8M scale (~2-2.5h
    extrapolated), so this stays a large sample rather than the full space,
    unlike Check 1 above. Zero mismatches is the bar: any single one would
    mean the table and the from-first-principles classifier disagree on the
    RELATIVE STRENGTH of two real hands, which the exact category counts
    above cannot detect (they only check aggregate counts, not pairwise
    ordering)."""
    sample = list(islice(combinations(range(52), 7), 0, None, 400))
    sample_arr = np.array(sample, dtype=np.int64)
    table_vals = evaluate_batch(sample_arr)
    direct_keys = [_direct_evaluate7(h) for h in sample]

    table_rank = {v: i for i, v in enumerate(sorted(set(table_vals.tolist())))}
    direct_rank = {v: i for i, v in enumerate(sorted(set(direct_keys)))}

    mismatches = sum(
        1 for tv, dk in zip(table_vals.tolist(), direct_keys) if table_rank[tv] != direct_rank[dk]
    )
    assert mismatches == 0, f"{mismatches}/{len(sample)} hands disagree between table and direct classification"
    assert len(table_rank) == len(direct_rank), "table and direct classifier see a different number of distinct classes in this sample"


# --- Structural spot checks (ties, wheel, board-plays) ----------------------


def test_ties_are_exact_integer_equality():
    a = card_ids("2c3c4c5c7c")
    b = card_ids("2d3d4d5d7d")
    assert evaluate5(a) == evaluate5(b)


def test_wheel_is_weaker_than_six_high_straight():
    wheel = card_ids("As2d3h4s5c")
    six_high = card_ids("2s3d4h5c6d")
    assert evaluate5(wheel) > evaluate5(six_high)


def test_royal_flush_is_the_strongest_class():
    assert evaluate5(card_ids("AsKsQsJsTs")) == 0


def test_quads_beats_full_house_seven_card():
    quads = card_ids("AcAdAhAs2c3d4h")
    boat = card_ids("KcKdKh2c2d3h4s")
    assert evaluate(quads) < evaluate(boat)


def test_board_plays_ties_across_different_hole_cards():
    board = card_ids("AsKsQsJsTs")  # royal flush on the board
    hand1 = card_ids("2c3d") + board
    hand2 = card_ids("4h5s") + board
    assert evaluate(hand1) == evaluate(hand2) == evaluate5(board)


def test_category_matches_evaluate5_for_a_known_hand():
    assert category(evaluate5(card_ids("AsKsQsJsTs"))) == HandCategory.STRAIGHT_FLUSH
