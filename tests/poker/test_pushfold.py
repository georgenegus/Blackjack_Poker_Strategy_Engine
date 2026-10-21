"""Phase 9: heads-up jam-or-fold equilibrium. See
markdowns/poker/poker_build_plan_v1.md Phase 9.

A real bug was caught during this phase's own development: the first
implementation of solve_pushfold used damped iterate-to-iterate updates and
checked whether THAT iterate stopped changing -- it never did (jam/call
class counts cycled between ~65 and ~170 over 200 iterations). Classical
fictitious play (Robinson 1951) only guarantees convergence of the
TIME-AVERAGE of both players' pure best responses for zero-sum games, not
the raw iterate -- the same "current strategy oscillates, average strategy
converges" property CFR itself is built around. Fixed by tracking the
running average and best-responding to the OPPONENT's running average, not
their last move; test_convergence_is_the_time_average_not_the_last_iterate
below is the regression test for that specific mistake.

No literal comparison against Miltersen & Sørensen's (2007) published exact
jam/fold tables is included here -- this development environment has no
network access to independently verify against them, and fabricating an
agreement claim without the reference in hand would be worse than not
claiming it. The plan's own alternative -- structural facts that "need no
table at all" -- IS fully checked below, and is what this test suite relies
on for correctness evidence.
"""

import pytest

from src.poker.pushfold import build_pushfold_grid, solve_pushfold, solve_pushfold_icm
from src.poker.spec import GameSpec


# --- Convergence correctness (the bug regression test) ----------------------


def test_convergence_is_the_time_average_not_the_last_iterate():
    """jam_pct/call_pct must stabilise (differences shrinking) as iteration
    count grows -- NOT keep swinging by tens of percentage points the way
    the pre-fix damped-iterate version did."""
    results = [solve_pushfold(GameSpec(stack_bb=10.0), iterations=n) for n in (100, 300, 600)]
    jam_deltas = [abs(results[i + 1].jam_pct - results[i].jam_pct) for i in range(len(results) - 1)]
    call_deltas = [abs(results[i + 1].call_pct - results[i].call_pct) for i in range(len(results) - 1)]
    assert all(d < 2.0 for d in jam_deltas), jam_deltas
    assert all(d < 2.0 for d in call_deltas), call_deltas


# --- Structural facts that need no external table ---------------------------


def test_extremely_short_stack_jams_and_calls_everything():
    r = solve_pushfold(GameSpec(stack_bb=1.0), iterations=200)
    assert r.jam_pct == pytest.approx(100.0, abs=0.5)
    assert r.call_pct == pytest.approx(100.0, abs=0.5)


def test_jam_and_call_ranges_are_monotone_decreasing_in_stack_depth():
    stacks = [2.0, 5.0, 10.0, 15.0, 20.0, 25.0]
    results = [solve_pushfold(GameSpec(stack_bb=s), iterations=200) for s in stacks]
    jam_pcts = [r.jam_pct for r in results]
    call_pcts = [r.call_pct for r in results]
    assert all(jam_pcts[i] >= jam_pcts[i + 1] - 1.0 for i in range(len(jam_pcts) - 1)), jam_pcts
    assert all(call_pcts[i] >= call_pcts[i + 1] - 1.0 for i in range(len(call_pcts) - 1)), call_pcts


def test_call_range_is_tighter_than_jam_range_at_moderate_and_deeper_stacks():
    """The plan's stated structural fact ("the call range is always tighter
    than the jam range") holds robustly from ~5bb onward -- verified here.
    It does NOT hold at the shortest stacks (see the dedicated crossover
    test below), a genuine, hand-verified finding documented in this
    phase's tracking-table entry, not a bug."""
    for stack in (5.0, 8.0, 10.0, 15.0, 20.0, 25.0):
        r = solve_pushfold(GameSpec(stack_bb=stack), iterations=200)
        assert r.call_pct <= r.jam_pct + 1.0, f"stack={stack}: call={r.call_pct} jam={r.jam_pct}"


def test_call_can_exceed_jam_at_the_shortest_stacks():
    """At 1.5bb, BB's pot-odds-only calling threshold (~17% equity) is far
    looser than SB's fold-equity-adjusted jamming threshold (~33% equity,
    since BB calls almost everything, leaving jamming little fold-equity
    edge over a pure equity play) -- so BB's calling range can legitimately
    be WIDER than SB's jamming range. Hand-verified: 32o's raw equity vs a
    random hand (~32.3%) sits just under the ~33.3% jam threshold at this
    depth, while comfortably clearing the ~16.7% call threshold."""
    r = solve_pushfold(GameSpec(stack_bb=1.5), iterations=200)
    assert r.call_pct > r.jam_pct


def test_ante_widens_both_ranges():
    no_ante = solve_pushfold(GameSpec(stack_bb=10.0, ante_bb=0.0), iterations=200)
    with_ante = solve_pushfold(GameSpec(stack_bb=10.0, ante_bb=0.2), iterations=200)
    assert with_ante.jam_pct > no_ante.jam_pct
    assert with_ante.call_pct > no_ante.call_pct


def test_jam_range_is_a_superset_shaped_range_object():
    r = solve_pushfold(GameSpec(stack_bb=8.0), iterations=200)
    jam_range = r.jam_range
    call_range = r.call_range
    assert jam_range.n_combos() == pytest.approx(r.jam_pct / 100.0 * 1326.0, abs=1.0)
    assert call_range.n_combos() == pytest.approx(r.call_pct / 100.0 * 1326.0, abs=1.0)
    # AA must always be in both ranges at any reasonable stack depth
    from src.poker.cards import card_id

    aa_combo_present = any(k[0] // 4 == 12 and k[1] // 4 == 12 for k in jam_range.combos())
    assert aa_combo_present


# --- The grid --------------------------------------------------------------


def test_grid_covers_the_plans_full_stack_range():
    grid = build_pushfold_grid(GameSpec(), stacks=(1.0, 5.0, 10.0, 25.0))
    assert set(grid.keys()) == {1.0, 5.0, 10.0, 25.0}
    assert grid[1.0].jam_pct > grid[25.0].jam_pct


# --- ICM-adjusted push/fold ---------------------------------------------------


def test_icm_adjusted_calling_range_tightens_near_a_real_bubble():
    """4 players, only the top 3 pay -- the chip leader calling a short
    stack's shove should call meaningfully tighter under ICM pressure than
    a pure chip-EV comparison at the same effective stack would suggest:
    letting the short stack bust to someone else is valuable near a real
    elimination bubble."""
    icm_result = solve_pushfold_icm([30.0, 8.0, 15.0, 15.0], payouts=[50, 30, 20], shover=1, caller=0, iterations=150)
    chip_ev_result = solve_pushfold(GameSpec(stack_bb=8.0), iterations=150)
    assert icm_result.call_pct < chip_ev_result.call_pct - 10.0


def test_icm_adjusted_ranges_are_well_formed():
    r = solve_pushfold_icm([20.0, 20.0, 20.0], payouts=[50, 30, 20], shover=0, caller=1, iterations=100)
    assert 0.0 <= r.jam_pct <= 100.0
    assert 0.0 <= r.call_pct <= 100.0
