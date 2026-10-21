"""Phase 10: scripts/poker/solve_spot.py's SpotGame (the bounded, river-only
postflop game) and solve_spot's wall-clock/iteration cap. See
markdowns/poker/poker_build_plan_v1.md Phase 10 and this module's own
docstring for the river-only scope decision.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.poker.solve_spot import SpotGame, format_strategy, solve_spot
from src.poker.cards import card_ids
from src.poker.evaluator import evaluate
from src.poker.ranges import Range

BOARD = tuple(card_ids("AsKd7h2c9s"))


def _small_game(**kwargs):
    defaults = dict(
        board=BOARD, hero_range=Range("QQ+"), villain_range=Range("QQ+"), pot_bb=10.0, stack_bb=20.0, bet_sizes=(1.0,)
    )
    defaults.update(kwargs)
    return SpotGame(**defaults)


# --- Construction / scope enforcement ---------------------------------------


def test_rejects_a_non_river_board():
    with pytest.raises(ValueError):
        SpotGame(board=BOARD[:3], hero_range=Range("QQ+"), villain_range=Range("QQ+"), pot_bb=10.0, stack_bb=20.0)


def test_rejects_nonpositive_pot_or_stack():
    with pytest.raises(ValueError):
        _small_game(pot_bb=0.0)
    with pytest.raises(ValueError):
        _small_game(stack_bb=0.0)


def test_deal_outcomes_sum_to_one_and_never_overlap_board_or_each_other():
    game = _small_game()
    assert len(game._deal_outcomes) > 0
    assert sum(p for _, p in game._deal_outcomes) == pytest.approx(1.0)
    board_set = set(BOARD)
    for state, _ in game._deal_outcomes:
        h, v = state.hole
        assert not (set(h) & board_set)
        assert not (set(v) & board_set)
        assert not (set(h) & set(v))  # hero and villain can never share a card


def test_deal_outcomes_exclude_combos_that_conflict_with_the_board():
    """QQ+ = QQ, KK, AA (18 raw combos); the board holds one A and one K, so
    KcKh/KsKh-style combos and every Ac-paired/Ad-paired-with-board-suit
    combo lose exactly one card each -- construction must drop those via
    Range.conditioned(), not merely skip them at solve time."""
    game = _small_game()
    seen_hero = {state.hole[0] for state, _ in game._deal_outcomes}
    board_set = set(BOARD)
    for combo in seen_hero:
        assert not (set(combo) & board_set)


def test_raises_when_no_valid_combo_pairs_exist():
    """Hero and villain both restricted to the SAME single combo can never
    produce a non-conflicting pair."""
    with pytest.raises(ValueError):
        SpotGame(board=BOARD, hero_range=Range("AsAh"), villain_range=Range("AsAh"), pot_bb=10.0, stack_bb=20.0)


# --- Terminal utility: exact showdown values, zero-sum, rake ----------------


def test_fold_terminal_is_exact_and_zero_sum():
    game = _small_game()
    h = game.chance_outcomes(())[0][0]
    h = game.next_history(h, "check")
    actions = game.legal_actions(h)
    bet_action = next(a for a in actions if a.startswith("bet_"))
    h = game.next_history(h, bet_action)
    h = game.next_history(h, "fold")
    assert game.is_terminal(h)
    assert game.utility(h, 0) == pytest.approx(-game.utility(h, 1))


def test_showdown_utility_matches_the_exact_evaluator_ranking():
    """Construct the simplest showdown line (both check) and confirm the
    winner/payoff matches evaluate() directly -- no equity approximation
    should be involved anywhere in this path, unlike PreflopGame."""
    game = _small_game()
    # Find a deal where hero's rank strictly beats villain's rank on this board.
    state = next(s for s, _ in game._deal_outcomes if evaluate(s.hole[0] + BOARD) < evaluate(s.hole[1] + BOARD))
    h = state
    h = game.next_history(h, "check")
    h = game.next_history(h, "check")
    assert game.is_terminal(h)

    pot = 10.0  # no rake by default (rake_pct=0.0 in _small_game)
    expected_payoff0 = pot / 2.0  # hero already had pot_bb/2 = 5.0 in, wins the other half
    assert game.utility(h, 0) == pytest.approx(expected_payoff0)
    assert game.utility(h, 1) == pytest.approx(-expected_payoff0)


def test_showdown_utility_splits_the_pot_on_an_exact_tie():
    game = _small_game()
    state = next(s for s, _ in game._deal_outcomes if evaluate(s.hole[0] + BOARD) == evaluate(s.hole[1] + BOARD))
    h = game.next_history(state, "check")
    h = game.next_history(h, "check")
    assert game.utility(h, 0) == pytest.approx(0.0)
    assert game.utility(h, 1) == pytest.approx(0.0)


def test_showdown_rake_reduces_the_winners_payoff():
    """The same construction as test_showdown_utility_matches_the_exact_
    evaluator_ranking, but with a real rake -- the winner's payoff must
    shrink by exactly the raked amount, matching spec.pot_after_rake."""
    game = _small_game(rake_pct=0.05, rake_cap_bb=3.0)
    state = next(s for s, _ in game._deal_outcomes if evaluate(s.hole[0] + BOARD) < evaluate(s.hole[1] + BOARD))
    h = game.next_history(state, "check")
    h = game.next_history(h, "check")

    raw_pot = 10.0
    raked_pot = game.spec.pot_after_rake(raw_pot, saw_flop=True)
    assert raked_pot < raw_pot
    expected_payoff0 = raked_pot - raw_pot / 2.0
    assert game.utility(h, 0) == pytest.approx(expected_payoff0)


# --- solve_spot: bounded by both iterations and wall-clock -------------------


def test_solve_spot_never_exceeds_the_requested_iteration_cap():
    game = _small_game()
    _, n_iters, _ = solve_spot(game, iterations=300, max_seconds=30.0, seed=1, warmup_iterations=100)
    assert n_iters <= 300


def test_solve_spot_respects_a_tight_wall_clock_cap():
    """A near-zero max_seconds must still return a valid result -- the
    warm-up batch alone, never more -- rather than blowing through the
    budget by running the full requested iteration count regardless."""
    game = _small_game()
    result, n_iters, elapsed = solve_spot(game, iterations=1_000_000, max_seconds=0.001, seed=1, warmup_iterations=50)
    assert n_iters == 50
    assert result.average_strategy  # still a usable (if under-converged) result


def test_solve_spot_game_value_has_a_standard_error():
    game = _small_game()
    result, _, _ = solve_spot(game, iterations=2000, max_seconds=30.0, seed=2, warmup_iterations=200)
    assert result.game_value_se is not None
    assert result.game_value_se >= 0


# --- format_strategy ----------------------------------------------------------


def test_format_strategy_frequencies_sum_to_one_and_cover_legal_actions():
    game = _small_game()
    result, _, _ = solve_spot(game, iterations=2000, max_seconds=30.0, seed=3, warmup_iterations=200)
    out = format_strategy(result.average_strategy, game)
    assert "OOP:start" in out
    for situation, hands in out.items():
        for combo, freqs in hands.items():
            total = sum(freqs.values())
            assert total == pytest.approx(1.0, abs=1e-2) or total == pytest.approx(0.0, abs=1e-9)


def test_format_strategy_situation_labels_alternate_oop_and_ip():
    game = _small_game()
    result, _, _ = solve_spot(game, iterations=2000, max_seconds=30.0, seed=4, warmup_iterations=200)
    out = format_strategy(result.average_strategy, game)
    assert any(k.startswith("OOP:") for k in out)
    assert any(k.startswith("IP:") for k in out)
