"""Phase 7: CFR against Kuhn poker's known analytic equilibrium. See
.agents/skills/poker_solver_conventions/SKILL.md and
markdowns/poker/poker_build_plan_v1.md Appendix A.5.

Phase 8 turns this into the formal validation gate (tolerance 1e-4 on the
game value, plus exploitability measured via best response); these tests are
Phase 7's own bar -- does the algorithm converge to Kuhn's equilibrium at
all, and does it get the STRUCTURE right (the plan's own warning: a
game-value-only check would pass a solver that found *a* value-preserving
strategy while getting the frequencies structurally wrong).

CFR here is fully deterministic (no RNG anywhere in the traversal), so every
tolerance below is a real bound, not a statistical one -- these numbers
don't jitter between runs.
"""

import numpy as np
import pytest

from src.poker.cfr import SolveResult, _regret_matching, save_state, load_state, solve, solve_mccfr
from src.poker.toy import KuhnPoker

KUHN_VALUE = -1.0 / 18.0


def _bet_freq(strategy, card, actions):
    """P(bet) for the info set (card, actions) -- legal_actions() is always
    ("p", "b"), so index 1 is "bet"."""
    return strategy[(card, actions)][1]


# --- Game value convergence --------------------------------------------------


def test_vanilla_cfr_converges_tightly_to_kuhn_value():
    s = solve(KuhnPoker(), iterations=20_000, variant="vanilla")
    assert s.game_value == pytest.approx(KUHN_VALUE, abs=1e-5)


def test_dcfr_converges_tightly_to_kuhn_value():
    s = solve(KuhnPoker(), iterations=20_000, variant="dcfr")
    assert s.game_value == pytest.approx(KUHN_VALUE, abs=1e-4)


def test_cfr_plus_converges_to_kuhn_value():
    """CFR+'s alternating updates converge more slowly than vanilla/DCFR on
    a game this tiny (empirically ~5.7e-5 at 100k iterations vs vanilla's
    ~4.5e-7 at 20k) -- still clearly convergent, just needs more iterations
    here. Phase 8's formal gate uses a 1e-4 bound at whatever iteration
    count it settles on; this test uses a looser, cheaper budget."""
    s = solve(KuhnPoker(), iterations=30_000, variant="cfr+")
    assert s.game_value == pytest.approx(KUHN_VALUE, abs=2e-3)


def test_cfr_plus_game_value_improves_with_more_iterations():
    """Monotonic-in-trend convergence, not just "close at one iteration
    count" -- catches an implementation that happens to cross the true
    value once by coincidence rather than actually converging."""
    s_short = solve(KuhnPoker(), iterations=2_000, variant="cfr+")
    s_long = solve(KuhnPoker(), iterations=50_000, variant="cfr+")
    assert abs(s_long.game_value - KUHN_VALUE) < abs(s_short.game_value - KUHN_VALUE)


# --- Structural correctness: Appendix A.5's frequency rows -----------------


def test_kuhn_equilibrium_frequency_structure():
    """The plan's own warning: a game-value-only test passes a structurally
    wrong solver. Check every row of Appendix A.5's frequency table, not
    just the game value -- including the ALGEBRAIC relationships (K-bet =
    3*alpha, Q-call-after-check = alpha + 1/3), not just the "always/never"
    entries, which are the easy half to get right by accident."""
    s = solve(KuhnPoker(), iterations=60_000, variant="cfr+")
    strat = s.average_strategy

    alpha = _bet_freq(strat, 0, ())  # P1 bets J with probability alpha in [0, 1/3]
    assert 0.0 <= alpha <= 1.0 / 3.0 + 0.02

    assert _bet_freq(strat, 1, ()) == pytest.approx(0.0, abs=0.02)  # P1 never bets Q first
    assert _bet_freq(strat, 2, ()) == pytest.approx(3 * alpha, abs=0.03)  # P1 bets K with 3*alpha

    assert _bet_freq(strat, 0, ("p", "b")) == pytest.approx(0.0, abs=0.02)  # P1 never calls with J
    assert _bet_freq(strat, 1, ("p", "b")) == pytest.approx(alpha + 1.0 / 3.0, abs=0.03)  # P1 calls Q w/ alpha+1/3
    assert _bet_freq(strat, 2, ("p", "b")) == pytest.approx(1.0, abs=0.02)  # P1 always calls with K

    assert _bet_freq(strat, 0, ("b",)) == pytest.approx(0.0, abs=0.02)  # P2 never calls a bet with J
    assert _bet_freq(strat, 1, ("b",)) == pytest.approx(1.0 / 3.0, abs=0.03)  # P2 calls Q with 1/3
    assert _bet_freq(strat, 2, ("b",)) == pytest.approx(1.0, abs=0.02)  # P2 always calls with K

    assert _bet_freq(strat, 0, ("p",)) == pytest.approx(1.0 / 3.0, abs=0.03)  # P2 bets J (bluffs) with 1/3
    assert _bet_freq(strat, 1, ("p",)) == pytest.approx(0.0, abs=0.02)  # P2 never bets Q facing a check
    assert _bet_freq(strat, 2, ("p",)) == pytest.approx(1.0, abs=0.02)  # P2 always bets K facing a check


# --- Mechanics ---------------------------------------------------------------


def test_regret_matching_uniform_when_no_positive_regret():
    uniform = _regret_matching(np.zeros(3))
    assert np.allclose(uniform, [1 / 3, 1 / 3, 1 / 3])
    negative = _regret_matching(np.array([-1.0, -2.0, -0.5]))
    assert np.allclose(negative, [1 / 3, 1 / 3, 1 / 3])


def test_regret_matching_proportional_to_positive_regret():
    probs = _regret_matching(np.array([3.0, 1.0, 0.0]))
    assert np.allclose(probs, [0.75, 0.25, 0.0])


def test_cfr_plus_regrets_never_go_negative():
    s = solve(KuhnPoker(), iterations=1_000, variant="cfr+")
    for r in s.regrets.values():
        assert np.all(r >= 0.0)


def test_average_strategy_sums_to_one_per_infoset():
    s = solve(KuhnPoker(), iterations=5_000, variant="vanilla")
    for probs in s.average_strategy.values():
        assert probs.sum() == pytest.approx(1.0, abs=1e-9)
        assert np.all(probs >= 0.0)


def test_unknown_variant_rejected():
    with pytest.raises(ValueError):
        solve(KuhnPoker(), iterations=10, variant="not_a_real_variant")


# --- Checkpointing ------------------------------------------------------------


def test_checkpoint_round_trip(tmp_path):
    s = solve(KuhnPoker(), iterations=5_000, variant="cfr+")
    path = tmp_path / "kuhn_checkpoint"
    save_state(s, path, meta={"game": "kuhn"})
    loaded = load_state(path)

    assert loaded.iterations == s.iterations
    assert loaded.variant == s.variant
    assert loaded.game_value == s.game_value
    assert set(loaded.average_strategy.keys()) == set(s.average_strategy.keys())
    for key in s.average_strategy:
        assert np.allclose(loaded.average_strategy[key], s.average_strategy[key])


# --- MCCFR (added in Phase 10, once the real preflop tree proved too large for
#     full-tree traversal -- see this module's docstring) ---------------------


def test_mccfr_converges_to_kuhn_value():
    s = solve_mccfr(KuhnPoker(), iterations=300_000, seed=0)
    assert s.game_value == pytest.approx(KUHN_VALUE, abs=5e-3)


def test_mccfr_game_value_improves_with_more_iterations():
    game = KuhnPoker()
    s_short = solve_mccfr(game, iterations=20_000, seed=1)
    s_long = solve_mccfr(game, iterations=300_000, seed=1)
    assert abs(s_long.game_value - KUHN_VALUE) < abs(s_short.game_value - KUHN_VALUE)


def test_mccfr_exploitability_decreases_with_more_iterations():
    from src.poker.exploit import exploitability

    game = KuhnPoker()
    exp_short = exploitability(game, solve_mccfr(game, iterations=20_000, seed=2).average_strategy)
    exp_long = exploitability(game, solve_mccfr(game, iterations=300_000, seed=2).average_strategy)
    assert exp_long < exp_short


def test_mccfr_frequency_structure_within_loose_tolerance():
    """Sampling noise means MCCFR needs a looser tolerance than full-tree
    CFR at a comparable wall-clock budget -- still checking the actual
    STRUCTURE (the plan's own warning), not just the game value."""
    s = solve_mccfr(KuhnPoker(), iterations=300_000, seed=3)
    strat = s.average_strategy
    alpha = strat[(0, ())][1]
    assert 0.0 <= alpha <= 1.0 / 3.0 + 0.05
    assert strat[(2, ())][1] == pytest.approx(3 * alpha, abs=0.08)
    assert strat[(0, ("b",))][1] == pytest.approx(0.0, abs=0.05)
    assert strat[(2, ("b",))][1] == pytest.approx(1.0, abs=0.05)


# --- exact_value=False: the Monte Carlo game-value estimator (added in Phase
#     10, once _expected_value's exact enumeration proved to consume 99.96%
#     of total solve_mccfr() runtime for a game far smaller than the real
#     preflop spec -- see cfr.py's own docstrings) -------------------------


def test_sampled_game_value_agrees_with_exact_on_kuhn():
    """Cross-validate the sampled estimator against the exact one on a game
    small enough for both to run, before trusting it on anything larger."""
    game = KuhnPoker()
    s_exact = solve_mccfr(game, iterations=100_000, seed=5, exact_value=True)
    s_sampled = solve_mccfr(game, iterations=100_000, seed=5, exact_value=False, value_samples=50_000)
    assert s_sampled.game_value_se is not None
    assert s_sampled.game_value_se > 0
    assert abs(s_sampled.game_value - s_exact.game_value) < 4 * s_sampled.game_value_se + 0.01


def test_exact_value_true_never_sets_a_standard_error():
    s = solve_mccfr(KuhnPoker(), iterations=1_000, seed=1, exact_value=True)
    assert s.game_value_se is None


def test_sampled_game_value_standard_error_shrinks_with_more_samples():
    game = KuhnPoker()
    s = solve_mccfr(game, iterations=5_000, seed=1)
    _, se_small = None, None
    from src.poker.cfr import _sampled_expected_value
    import numpy as np

    rng = np.random.default_rng(0)
    _, se_small = _sampled_expected_value(game, s.average_strategy, 200, rng)
    _, se_large = _sampled_expected_value(game, s.average_strategy, 20_000, rng)
    assert se_large < se_small
