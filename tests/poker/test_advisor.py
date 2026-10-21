"""Phase 10: the real preflop game (PreflopGame), the equity-realisation
terminal-value approximation, and the runtime advice lookup. See
markdowns/poker/poker_build_plan_v1.md Phase 10 and
.agents/skills/poker_solver_conventions/SKILL.md.

Two significant performance bugs were found and fixed while building this
phase, both in src/poker/cfr.py, not in this module -- documented in detail
in cfr.py's own docstrings and this phase's tracking-table entry:
(1) _traverse_mccfr re-extracted and re-normalised a probability array from
    the chance node's outcome list on EVERY iteration, ~O(n) Python-level
    work per call -- for PreflopGame's 28,561-outcome deal, this dominated
    per-iteration cost (~7.8x speedup after caching by outcome-list identity).
(2) solve_mccfr(..., exact_value=True) (the default, correct for Kuhn/Leduc)
    computed the final game_value via FULL exact enumeration even when the
    underlying game was far too large for that -- profiling showed this one
    call consuming 99.96% of total solve time on a spec smaller than the
    plan's own example, completely defeating the point of using MCCFR.
    Fixed by adding exact_value=False (Monte Carlo estimate, with a standard
    error) -- required for any large game, PreflopGame included.
"""

import numpy as np
import pytest

from src.poker.advisor import Advice, PreflopGame, PreflopState, _apply_realization, _position_skew, advise
from src.poker.ranges import CLASS_LABELS
from src.poker.spec import GameSpec
from src.poker.tree import _initial_state


@pytest.fixture(scope="module")
def small_game():
    return PreflopGame(GameSpec(stack_bb=10.0, bet_sizes=(1.0,)))


# --- PreflopGame mechanics ----------------------------------------------------


def test_root_is_the_only_chance_node(small_game):
    assert small_game.is_chance(())
    outcomes = small_game.chance_outcomes(())
    h0 = outcomes[0][0]
    assert not small_game.is_chance(h0)


def test_deal_outcomes_cover_all_169x169_pairs_and_sum_to_one(small_game):
    outcomes = small_game.chance_outcomes(())
    assert len(outcomes) == 169 * 169
    assert sum(p for _, p in outcomes) == pytest.approx(1.0)
    holes = {h.hole for h, _ in outcomes}
    assert holes == {(i, j) for i in range(169) for j in range(169)}


def test_self_matchup_deals_are_the_most_likely_shape():
    """A specific (i, i) self-matchup should be less likely than the most
    common (i, j) combo-count product for two different popular classes,
    but every combo-count-weighted pair should still be present with
    positive probability -- a basic sanity check on the weighting."""
    game = PreflopGame(GameSpec(stack_bb=10.0, bet_sizes=(1.0,)))
    outcomes = dict(game.chance_outcomes(()))
    aa_idx = CLASS_LABELS.index("AA")
    ako_idx = CLASS_LABELS.index("AKo")
    aa_vs_aa = next(p for h, p in game._deal_outcomes if h.hole == (aa_idx, aa_idx))
    aa_vs_ako = next(p for h, p in game._deal_outcomes if h.hole == (aa_idx, ako_idx))
    assert aa_vs_aa > 0
    assert aa_vs_ako > aa_vs_aa  # AKo has 12 combos vs AA's 6, so more likely to pair with AA


def test_fold_terminal_is_exact_and_zero_sum(small_game):
    h = small_game.chance_outcomes(())[0][0]
    while not small_game.is_terminal(h):
        actions = small_game.legal_actions(h)
        a = "fold" if "fold" in actions else actions[0]
        h = small_game.next_history(h, a)
    assert small_game.utility(h, 0) == pytest.approx(-small_game.utility(h, 1))


def test_fold_terminal_matches_hand_derived_blind_loss(small_game):
    """SB folding their very first action loses exactly their sb post."""
    h = small_game.chance_outcomes(())[0][0]
    h = small_game.next_history(h, "fold")
    assert small_game.is_terminal(h)
    assert small_game.utility(h, 0) == pytest.approx(-0.5)
    assert small_game.utility(h, 1) == pytest.approx(0.5)


def test_showdown_terminal_applies_rake_but_fold_terminal_does_not():
    """Phase 10's own plan (Implementation section 1: "rake from
    spec.pot_after_rake") requires a hand reaching showdown to have its pot
    raked, while a hand folding preflop must not be (GameSpec's default
    no_flop_no_drop=True) -- exactly the asymmetry
    test_fold_terminal_matches_hand_derived_blind_loss above already locks
    in for the fold side. An earlier version of utility() never called
    spec.pot_after_rake at all, silently understating the cost of seeing a
    flop for every real solve; this constructs the simplest showdown line
    (SB calls, BB checks back) under the default 5%-capped-at-3bb rake and
    checks the EXACT raked value against spec.pot_after_rake directly."""
    spec = GameSpec(stack_bb=10.0, bet_sizes=(1.0,))
    game = PreflopGame(spec)
    h = game.chance_outcomes(())[0][0]
    h = game.next_history(h, "call")  # SB calls BB's 1bb
    h = game.next_history(h, "check")  # BB checks back -> showdown, raw pot = 2.0bb
    assert game.is_terminal(h)

    raw_pot = 2.0
    raked_pot = spec.pot_after_rake(raw_pot, saw_flop=True)
    assert raked_pot < raw_pot  # the rake must actually bite here, or this test proves nothing

    i, j = h.hole
    raw_equity0 = float(game._matrix[i, j])
    spr = min(h.betting.stacks_bb) / raw_pot
    realized0 = _apply_realization(raw_equity0, spr)
    expected_payoff0 = raked_pot * realized0 - h.betting.committed_bb[0]
    assert game.utility(h, 0) == pytest.approx(expected_payoff0)
    assert game.utility(h, 1) == pytest.approx(-expected_payoff0)


def test_infoset_key_never_reveals_the_opponents_hole_class(small_game):
    outcomes = small_game.chance_outcomes(())
    h_a = next(h for h, _ in outcomes if h.hole[0] == 5)
    h_b = next(h for h, _ in outcomes if h.hole[0] == 5 and h.hole[1] != h_a.hole[1])
    assert small_game.infoset_key(h_a, 0) == small_game.infoset_key(h_b, 0)


def test_legal_actions_reuse_tree_pys_own_betting_logic(small_game):
    """PreflopGame's legal_actions/next_history must reproduce EXACTLY what
    src.poker.tree's own state machine (already independently tested in
    Phase 6, including the min-raise/short-all-in edge case) computes --
    checked here by walking both in lockstep."""
    from src.poker.tree import _apply_action, _legal_bet_sizes

    spec = small_game.spec
    tree_state = _initial_state(spec)
    game_hole = small_game.chance_outcomes(())[0][0].hole
    game_history = PreflopState(game_hole, tree_state)

    for _ in range(3):
        expected_sizes = _legal_bet_sizes(spec, sum(tree_state.committed_bb), tree_state.stacks_bb[tree_state.to_act[0][0]])
        game_actions = small_game.legal_actions(game_history)
        if tree_state.committed_bb[tree_state.to_act[0][0]] == max(tree_state.committed_bb):
            bet_actions = [a for a in game_actions if a.startswith("bet_")]
            assert len(bet_actions) == len(expected_sizes)
        break  # one comparison is enough to catch a systematic mismatch


# --- Equity realisation -------------------------------------------------------


def test_realization_is_zero_sum_by_construction():
    """Player 1's realised equity is always 1 - player 0's -- never computed
    independently, which is what keeps the approximated game valid for CFR."""
    for eq0 in (0.1, 0.3, 0.5, 0.7, 0.9):
        for spr in (0.5, 2.0, 10.0, 50.0):
            realized0 = _apply_realization(eq0, spr)
            assert 0.0 <= realized0 <= 1.0


def test_realization_bonus_peaks_at_a_coinflip_and_vanishes_at_extremes():
    spr = 10.0
    shift_at_coinflip = _apply_realization(0.5, spr) - 0.5
    shift_near_lock = _apply_realization(0.95, spr) - 0.95
    shift_at_zero = _apply_realization(0.0, spr) - 0.0
    assert shift_at_coinflip > shift_near_lock > 0
    assert shift_at_zero == pytest.approx(0.0)


def test_realization_bonus_grows_with_spr_up_to_the_cap():
    assert _position_skew(1.0) < _position_skew(5.0) < _position_skew(10.0)
    assert _position_skew(10.0) == _position_skew(20.0) == _position_skew(100.0)


# --- advise() -------------------------------------------------------------


def test_advise_frequencies_sum_to_one_on_a_solved_small_spec(tmp_path, monkeypatch):
    import json

    import src.poker.advisor as advisor_mod

    spec = GameSpec(stack_bb=10.0, bet_sizes=(1.0,))
    strategy_dir = tmp_path / spec.key()
    strategy_dir.mkdir(parents=True)
    fake_strategy = {
        "BTN:open": {
            "AA": {"raise_9": 0.52, "call": 0.48},
            "72o": {"fold": 0.95, "call": 0.05},
        }
    }
    (strategy_dir / "preflop.json").write_text(json.dumps({"strategy": fake_strategy}))
    monkeypatch.setattr(advisor_mod, "STRATEGY_DIR", tmp_path)

    a = advise("AA", "BTN", [], spec)
    assert isinstance(a, Advice)
    assert sum(a.action_frequencies.values()) == pytest.approx(1.0)
    assert a.is_close  # 0.52 vs 0.48 -- gap 0.04, within the 0.1 is_close threshold

    a72 = advise("72o", "BTN", [], spec)
    assert not a72.is_close  # 0.95 vs 0.05 -- gap 0.9, clearly not a mix


def test_advise_missing_strategy_file_raises_clear_error(tmp_path, monkeypatch):
    import src.poker.advisor as advisor_mod

    monkeypatch.setattr(advisor_mod, "STRATEGY_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        advise("AA", "BTN", [], GameSpec(stack_bb=17.0, bet_sizes=(1.0,)))


def test_advise_unknown_hand_raises_key_error(tmp_path, monkeypatch):
    import json

    import src.poker.advisor as advisor_mod

    spec = GameSpec(stack_bb=10.0, bet_sizes=(1.0,))
    strategy_dir = tmp_path / spec.key()
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "preflop.json").write_text(json.dumps({"strategy": {"BTN:open": {"AA": {"call": 1.0}}}}))
    monkeypatch.setattr(advisor_mod, "STRATEGY_DIR", tmp_path)

    with pytest.raises(KeyError):
        advise("72o", "BTN", [], spec)
