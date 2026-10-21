"""Phase 4: 169-grid notation parsing, weighted combo expansion, card
removal, and range-vs-range equity.

See .agents/skills/poker_range_conventions/SKILL.md for the invariants this
locks in: combo counts per notation shape (6/4/12/16), card removal must
drop conflicting combos without rescaling the survivors, and range-vs-range
equity must be a joint weighted sum over non-conflicting combo pairs -- never
the naive per-combo average against the opponent's unconditioned range.
"""

import pytest

from src.poker.cards import card_ids, mask
from src.poker.equity import equity_exact
from src.poker.ranges import CLASS_LABELS, Range, load_range, range_vs_range_equity, save_range


# --- The 169-class registry -------------------------------------------------


def test_class_registry_has_169_classes_covering_all_1326_combos():
    assert len(CLASS_LABELS) == 169
    assert sum(Range(label).n_combos() for label in CLASS_LABELS) == 1326


# --- Combo counts per notation shape ----------------------------------------


@pytest.mark.parametrize(
    "notation,expected",
    [
        ("AA", 6),  # pair
        ("77", 6),
        ("AKs", 4),  # suited
        ("AKo", 12),  # offsuit
        ("AK", 16),  # bare rank pair = suited + offsuit combined
        ("KA", 16),  # order-insensitive
        ("TT+", 30),  # TT,JJ,QQ,KK,AA -> 5 * 6
        ("88-55", 24),  # 55,66,77,88 -> 4 * 6
        ("55-88", 24),  # order-insensitive
        ("A5s+", 36),  # A5s..AKs -> 9 * 4
        ("A5s-A2s", 16),  # A5s,A4s,A3s,A2s -> 4 * 4
        ("A5o-A2o", 48),  # same kicker range, offsuit -> 4 * 12
        ("100%", 1326),
        ("random", 1326),
        ("0%", 0),
    ],
)
def test_combo_counts_by_notation_shape(notation, expected):
    assert Range(notation).n_combos() == expected


def test_explicit_combo_and_weight_suffix():
    r = Range("AsKd:0.5")
    a, k = card_ids("As")[0], card_ids("Kd")[0]
    assert r.combos() == {(min(a, k), max(a, k)): 0.5}


def test_comma_separated_mixed_tokens():
    r = Range("AA,KK,AKs:0.5,QQ")
    assert r.n_combos() == 6 + 6 + 4 * 0.5 + 6


def test_weight_out_of_bounds_rejected():
    with pytest.raises(ValueError):
        Range("AA:1.5")
    with pytest.raises(ValueError):
        Range("AA:-0.1")


def test_duplicate_card_combo_rejected():
    with pytest.raises(ValueError):
        Range("AsAs")


# --- Card removal: drop and (not-)rescale -----------------------------------


def test_conditioned_drops_conflicting_combos_plan_worked_example():
    r = Range("AA")
    assert r.n_combos() == 6
    conditioned = r.conditioned(mask(card_ids("As")))
    assert conditioned.n_combos() == 3


def test_conditioned_keeps_surviving_weights_unchanged():
    """Conditioning must NOT rescale survivors -- a weighted combo's weight
    means "how often we hold this still-possible combo", which blocking a
    different combo doesn't change. See ranges.Range.conditioned()'s
    docstring for why this is deliberate, not a missing normalisation step."""
    r = Range("AJs:0.4")
    conditioned = r.conditioned(mask(card_ids("As")))
    assert conditioned.n_combos() == 3 * 0.4
    assert all(w == 0.4 for w in conditioned.combos().values())


def test_conditioned_on_all_cards_yields_empty_range():
    r = Range("AA")
    blockers = mask(card_ids("As") + card_ids("Ah") + card_ids("Ad") + card_ids("Ac"))
    assert r.conditioned(blockers).n_combos() == 0


# --- Range arithmetic --------------------------------------------------------


def test_union_takes_max_weight():
    a = Range("AA,KK,AJs:0.5")
    b = Range("KK,QQ,AJs:0.8")
    u = a.union(b)
    assert u.n_combos() == pytest.approx(6 + 6 + 6 + 4 * 0.8)
    assert (a | b).n_combos() == u.n_combos()


def test_intersect_takes_min_weight():
    a = Range("AA,KK,AJs:0.5")
    b = Range("KK,QQ,AJs:0.8")
    i = a.intersect(b)
    assert i.n_combos() == pytest.approx(6 + 4 * 0.5)
    assert (a & b).n_combos() == i.n_combos()


def test_difference_is_set_difference_not_weight_subtraction():
    a = Range("AA,KK,AJs:0.5")
    b = Range("KK,QQ,AJs:0.8")
    d = a.difference(b)
    assert d.n_combos() == 6  # only AA survives; KK and AJs are both in b entirely
    assert (a - b).n_combos() == d.n_combos()


def test_reweight_scales_every_combo():
    a = Range("AA,KK")
    assert a.reweight(0.5).n_combos() == pytest.approx(a.n_combos() * 0.5)


# --- Save / load round-trip --------------------------------------------------


def test_save_load_round_trip(tmp_path):
    original = Range("AA,AKs:0.5,AsKd:0.3")
    path = tmp_path / "test_range.json"
    save_range(original, path)
    loaded = load_range(path)
    assert loaded.combos() == pytest.approx(original.combos())


# --- Range-vs-range equity ---------------------------------------------------


def test_range_vs_range_equity_sums_to_one():
    hero = Range("AA")
    villain = Range("KK")
    eq_a, eq_b = range_vs_range_equity(hero, villain, [], None)
    assert eq_a + eq_b == 1.0


def test_range_vs_range_equity_matches_single_matchup_when_ranges_are_single_combos():
    hero = Range("AsAh")
    villain = Range("KsKh")
    eq_a, eq_b = range_vs_range_equity(hero, villain, [], None)
    exact = equity_exact([card_ids("AsAh"), card_ids("KsKh")], [], None)
    assert eq_a == pytest.approx(float(exact[0]), abs=1e-9)


def test_joint_range_vs_range_equity_differs_from_naive_average_by_more_than_half_a_point():
    """THE Phase 4 correctness gate (build plan Phase 4 verification block):
    the naive method averages each hero combo's equity against villain's
    range using villain's UNCONDITIONED total combo-weight as the
    denominator, silently understating equity whenever hero's own cards
    block a meaningful share of villain's combos. Constructed spot: hero
    holds a specific AA combo, villain's range is "AA" itself -- 5 of
    villain's 6 combos conflict with hero's exact cards, leaving only 1
    valid villain combo, so the naive denominator (6) vastly overstates the
    true conditional total (1)."""

    def naive_range_vs_range_equity(range_a: Range, range_b: Range, board=()) -> float:
        total_b_weight = range_b.n_combos()
        board = tuple(board)
        acc, total_a_weight = 0.0, 0.0
        for a, wa in range_a.combos().items():
            numerator = 0.0
            for b, wb in range_b.combos().items():
                if set(a) & set(b):
                    continue
                eq = equity_exact([list(a), list(b)], list(board), None)
                numerator += wb * float(eq[0])
            acc += wa * (numerator / total_b_weight)  # BUG: should divide by the surviving weight only
            total_a_weight += wa
        return acc / total_a_weight

    hero = Range("AsAh")
    villain = Range("AA")

    joint_eq, _ = range_vs_range_equity(hero, villain, [], None)
    naive_eq = naive_range_vs_range_equity(hero, villain, [])

    assert joint_eq == pytest.approx(0.5, abs=1e-9)  # AsAh vs its own class's sole surviving combo: exactly symmetric
    divergence_pp = abs(joint_eq - naive_eq) * 100
    assert divergence_pp > 0.5, f"expected joint vs naive to diverge by >0.5pp, got {divergence_pp:.2f}pp"


def test_range_vs_range_equity_with_a_board():
    hero = Range("AsAh")
    villain = Range("KsKh")
    board = card_ids("2c7hTd9s")  # 4-card turn board, no pairs/flush interaction
    eq_a, eq_b = range_vs_range_equity(hero, villain, board, None)
    assert eq_a + eq_b == 1.0
    assert 0.0 <= eq_a <= 1.0


def test_range_vs_range_equity_rejects_fully_conflicting_ranges():
    hero = Range("AsAh")
    villain = Range("AsAh")  # identical single combo -- every pairing conflicts
    with pytest.raises(ValueError):
        range_vs_range_equity(hero, villain, [], None)
