"""Phase 5, Checks 4-5: equity identities that need no external source
(exact by construction, or provable by symmetry), and the published/exact
matchup anchors from Appendix A.4.

See markdowns/poker/poker_build_plan_v1.md Appendix A.4. Note on Check 5:
Appendix A.4's values were computed by equity_exact itself (this project's
own tool), not sourced from an external calculator -- these are frozen
regression anchors, not independent validation. What they do lock in: any
future change to the evaluator or equity engine that shifts these numbers
gets caught immediately, exactly like the blackjack area's house-edge
baseline.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from src.poker.cards import card_ids
from src.poker.equity import equity_exact, equity_mc
from src.poker.ranges import hand_classes

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "poker"


# --- Check 4: equity identities requiring no external source ----------------


def test_equity_exact_sums_to_exactly_one():
    for h1, h2 in [("AsAh", "KsKh"), ("AsKs", "QhQd"), ("7s2d", "AcKc")]:
        e = equity_exact([card_ids(h1), card_ids(h2)], [], None)
        assert e.sum() == 1.0


def test_equity_symmetry():
    """equity(A, B) == 1 - equity(B, A) on the same board -- trivially true
    by construction (equity_exact's own two outputs already sum to 1), but
    worth locking in explicitly since it's the property every downstream
    range-vs-range and matrix computation leans on."""
    a, b = card_ids("AsKs"), card_ids("QhQd")
    board = card_ids("2c7hTd")
    eq_ab = equity_exact([a, b], board, None)
    eq_ba = equity_exact([b, a], board, None)
    assert eq_ab[0] == pytest.approx(1.0 - eq_ba[0], abs=1e-12)


def test_three_way_equity_sums_to_one():
    e = equity_exact([card_ids("AsAh"), card_ids("KsKh"), card_ids("QsQh")], [], None)
    assert e.sum() == pytest.approx(1.0, abs=1e-9)


def test_nuts_on_a_complete_board_has_equity_exactly_one():
    """A hand that is already the nuts with no runout able to change that has
    equity exactly 1.0 -- not 0.9999. Quad aces on a fully-dealt board beats
    anything the remaining deck could have given the villain, and there ARE
    no more cards to come (a 5-card board), so this is a single deterministic
    showdown, not an average over runouts."""
    hero = card_ids("AsAh")
    villain = card_ids("KsKh")
    board = card_ids("AdAc2c3d4h")  # quad aces, complete board
    eq = equity_exact([hero, villain], board, None)
    assert eq[0] == 1.0
    assert eq[1] == 0.0


def test_average_equity_of_every_starting_hand_vs_random_is_exactly_half():
    """Averaging all 169 starting-hand classes against a random hand,
    weighted by real combo counts, gives exactly 0.5 -- a full-coverage
    symmetry identity (for every ordered (hero, opponent) combo pair
    counted, the reversed pair is also counted, with complementary equity,
    so the grand total divided by the grand pair count is exactly 1/2)
    across the ENTIRE preflop_169x169.npz matrix, not a sample of it. Reuses
    the already-computed, already-locked matrix (Phase 3) rather than
    re-running equity_exact -- the pair-count weighting itself needs no
    equity computation at all, just conflict counting."""
    matrix_path = DATA_DIR / "equity" / "preflop_169x169.npz"
    if not matrix_path.exists():
        pytest.skip("preflop_169x169.npz not built -- run scripts/poker/build_preflop_equity.py")
    data = np.load(matrix_path, allow_pickle=True)
    matrix = data["matrix"]
    saved_labels = list(data["labels"])

    labels, groups = hand_classes()
    assert saved_labels == labels, "matrix labels/order no longer match ranges.hand_classes()"

    sets = [[set(c) for c in g] for g in groups]
    n = len(labels)
    acc, total_w = 0.0, 0
    for i in range(n):
        for j in range(n):
            w = sum(1 for a in sets[i] for b in sets[j] if not (a & b))
            acc += matrix[i, j] * w
            total_w += w

    assert total_w == 1326 * 1225
    assert acc / total_w == pytest.approx(0.5, abs=1e-9)


# --- Check 5: matchup anchors (Appendix A.4) ---------------------------------

APPENDIX_A4_ANCHORS = [
    ("AsAh", "KsKh", (), 0.826366113),
    ("AsAh", "KsKd", (), 0.819460505),
    ("AsAh", "KdKc", (), 0.812554897),
    ("AsAh", "7s2d", (), 0.882055698),
    ("AsKs", "QhQd", (), 0.462144572),
    ("AsKs", "QsQd", (), 0.458825944),
    ("AsKd", "QhQc", (), 0.428351508),
    ("AsKd", "2h2c", (), 0.469596520),
]


@pytest.mark.parametrize("hero,villain,board,expected", APPENDIX_A4_ANCHORS, ids=lambda x: str(x)[:12])
def test_appendix_a4_anchors_exact(hero, villain, board, expected):
    eq = equity_exact([card_ids(hero), card_ids(villain)], list(board), None)
    assert eq[0] == pytest.approx(expected, abs=5e-6)


def test_equity_baseline_file_matches_current_computation():
    baseline_path = DATA_DIR / "baselines" / "equity_baseline.json"
    if not baseline_path.exists():
        pytest.skip("equity_baseline.json not yet locked")
    baseline = json.loads(baseline_path.read_text())
    for anchor in baseline["anchors"]:
        eq = equity_exact([card_ids(anchor["hero"]), card_ids(anchor["villain"])], [], None)
        assert eq[0] == pytest.approx(anchor["hero_equity"], abs=1e-6), anchor["hero"] + " vs " + anchor["villain"]


# --- Monte Carlo sanity ------------------------------------------------------


def test_equity_mc_agrees_with_exact_within_standard_error():
    hero, villain = card_ids("AsKs"), card_ids("QhQd")
    exact = equity_exact([hero, villain], [], None)
    mean, se = equity_mc([hero, villain], [], n=100_000, seed=7)
    assert abs(mean[0] - exact[0]) < 4 * se[0]
    assert se[0] > 0
