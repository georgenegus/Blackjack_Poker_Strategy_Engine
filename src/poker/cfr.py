"""Phase 7: Counterfactual Regret Minimisation. See
markdowns/poker/poker_build_plan_v1.md Phase 7 and
.agents/skills/poker_solver_conventions/SKILL.md.

CFR finds a Nash equilibrium of a two-player zero-sum extensive-form game by
self-play: at every information set, track each action's counterfactual
regret, play proportionally to positive regret (regret matching), and
average the strategy over iterations. The AVERAGE strategy is what's proven
to converge -- the CURRENT strategy oscillates and can be arbitrarily far
from equilibrium at any single iteration. Every solve() result reports its
average strategy, never the current one.

Three variants share one traversal (_traverse below), differing only in how
regrets/strategy-sums are weighted and which player(s) update each
iteration:
  - "vanilla": both players update every iteration, uniform strategy-sum
    weighting. Slow, but simple enough to read end-to-end and check by hand
    -- the reference the other two are checked against.
  - "cfr+" (the shipped default): regrets floored at zero after every
    update (never allowed to go negative and "remember" a bad action),
    strategy-sum weighted linearly by iteration number, and only ONE player
    updates per iteration (alternating).
  - "dcfr": both players update every iteration; existing regrets and the
    strategy sum are discounted at the START of each iteration (positive
    regret by t^alpha/(t^alpha+1), negative regret by t^beta/(t^beta+1),
    strategy sum by (t/(t+1))^gamma) rather than floored/linearly-weighted.

A `game` is any object implementing the small extensive-form interface
src.poker.toy.KuhnPoker does (is_chance/is_terminal/current_player/
legal_actions/chance_outcomes/next_history/infoset_key/utility) -- this
module never assumes it's poker specifically.

External-sampling MCCFR (solve_mccfr, added in Phase 10) is the escalation
the plan itself calls out ("needed once postflop abstraction enters the
picture") -- deferred at Phase 7 as "unnecessary for preflop and toy games"
turned out to be premature: the REAL preflop game (169 canonical starting
hands per player, not a 3-card toy deck) times the real 100bb betting tree
(23,869 nodes for the plan's own example spec) is ~680M node-visits for one
full-tree traversal, hopelessly large for the vanilla/cfr+/dcfr approach
above -- discovered empirically at the start of Phase 10, not anticipated at
Phase 7. MCCFR samples chance's and the opponent's actions (one path each,
not every branch) and only fully explores the UPDATING player's own
actions each iteration, converging to the same equilibrium in expectation
at a fraction of the per-iteration cost.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

InfosetKey = tuple
Strategy = dict  # InfosetKey -> np.ndarray of per-legal-action probabilities


def _regret_matching(regret_arr: np.ndarray) -> np.ndarray:
    """Play proportionally to positive regret; uniform if no action has any."""
    positive = np.maximum(regret_arr, 0.0)
    total = positive.sum()
    if total > 1e-12:
        return positive / total
    return np.full(regret_arr.shape[0], 1.0 / regret_arr.shape[0])


def _traverse(
    game,
    history: tuple,
    reach: list[float],
    regrets: dict[InfosetKey, np.ndarray],
    strat_sums: dict[InfosetKey, np.ndarray],
    update_players: set[int],
    strategy_weight: float,
    floor_regrets: bool,
) -> float:
    """One recursive pass, returning player 0's expected value from `history`
    given both players' current regret-matching strategies. Player 1's value
    is always -this (zero-sum). Updates regrets/strategy-sums in place for
    every player in `update_players` encountered along the way -- both
    players' VALUES are always computed (needed for correctness downstream
    regardless of who's updating), only the UPDATE is gated.
    """
    if game.is_terminal(history):
        return game.utility(history, 0)

    if game.is_chance(history):
        value = 0.0
        for next_history, prob in game.chance_outcomes(history):
            value += prob * _traverse(
                game, next_history, reach, regrets, strat_sums, update_players, strategy_weight, floor_regrets
            )
        return value

    player = game.current_player(history)
    infoset = game.infoset_key(history, player)
    actions = game.legal_actions(history)
    n = len(actions)

    regret_arr = regrets.setdefault(infoset, np.zeros(n))
    strategy = _regret_matching(regret_arr)

    action_values = np.empty(n)
    for i, a in enumerate(actions):
        new_reach = list(reach)
        new_reach[player] *= strategy[i]
        action_values[i] = _traverse(
            game, game.next_history(history, a), new_reach, regrets, strat_sums, update_players, strategy_weight, floor_regrets
        )

    node_value = float(np.dot(strategy, action_values))

    if player in update_players:
        cf_reach = 1.0
        for i, r in enumerate(reach):
            if i != player:
                cf_reach *= r
        sign = 1.0 if player == 0 else -1.0
        increment = cf_reach * (sign * action_values - sign * node_value)
        if floor_regrets:
            regret_arr[:] = np.maximum(regret_arr + increment, 0.0)
        else:
            regret_arr += increment

        strat_sum = strat_sums.setdefault(infoset, np.zeros(n))
        strat_sum += strategy_weight * reach[player] * strategy

    return node_value


def _apply_dcfr_discount(
    regrets: dict[InfosetKey, np.ndarray],
    strat_sums: dict[InfosetKey, np.ndarray],
    t: int,
    alpha: float,
    beta: float,
    gamma: float,
) -> None:
    pos_factor = (t**alpha) / (t**alpha + 1)
    neg_factor = (t**beta) / (t**beta + 1)
    strat_factor = (t / (t + 1)) ** gamma
    for r in regrets.values():
        np.multiply(r, np.where(r > 0, pos_factor, neg_factor), out=r)
    for s in strat_sums.values():
        s *= strat_factor


def _expected_value(game, strategy: Strategy, history: tuple) -> float:
    """Player 0's EXACT expected value under a fixed strategy profile -- a
    clean deterministic traversal, not the noisy per-iteration values CFR
    accumulates during solving. This is what solve()'s reported game_value
    uses, evaluated against the final AVERAGE strategy."""
    if game.is_terminal(history):
        return game.utility(history, 0)
    if game.is_chance(history):
        return sum(p * _expected_value(game, strategy, h) for h, p in game.chance_outcomes(history))

    player = game.current_player(history)
    infoset = game.infoset_key(history, player)
    actions = game.legal_actions(history)
    probs = strategy.get(infoset)
    if probs is None:
        probs = np.full(len(actions), 1.0 / len(actions))
    return sum(
        probs[i] * _expected_value(game, strategy, game.next_history(history, a)) for i, a in enumerate(actions)
    )


def _sampled_expected_value(
    game, strategy: Strategy, n_samples: int, rng: np.random.Generator
) -> tuple[float, float]:
    """Player 0's MONTE CARLO estimated expected value under a fixed
    strategy profile, WITH a standard error -- the tractable alternative to
    _expected_value's exact-but-exponential full enumeration, needed for any
    game too large to enumerate fully (see solve_mccfr's `exact_value`
    parameter and this module's docstring on why the real preflop game is
    exactly such a case: _expected_value's full enumeration over its 28,561
    deals measured at 99.96% of total solve_mccfr() runtime in profiling --
    NOT the actual MCCFR sampling loop -- for a spec far smaller than the
    plan's own example). Per this repo's "no bare point estimates from
    Monte Carlo" rule (.agents/instructions.md), this is never returned
    without its companion standard error.
    """
    values = np.empty(n_samples)
    for k in range(n_samples):
        history = ()
        while not game.is_terminal(history):
            if game.is_chance(history):
                outcomes = game.chance_outcomes(history)
                probs = np.array([p for _, p in outcomes])
                idx = rng.choice(len(outcomes), p=probs / probs.sum())
                history = outcomes[idx][0]
                continue
            player = game.current_player(history)
            infoset = game.infoset_key(history, player)
            actions = game.legal_actions(history)
            probs = strategy.get(infoset)
            if probs is None:
                probs = np.full(len(actions), 1.0 / len(actions))
            idx = rng.choice(len(actions), p=probs)
            history = game.next_history(history, actions[idx])
        values[k] = game.utility(history, 0)

    mean = float(values.mean())
    se = float(values.std(ddof=1) / np.sqrt(n_samples)) if n_samples > 1 else 0.0
    return mean, se


def _average_strategy(strat_sums: dict[InfosetKey, np.ndarray]) -> Strategy:
    avg: Strategy = {}
    for infoset, ssum in strat_sums.items():
        total = ssum.sum()
        avg[infoset] = ssum / total if total > 1e-12 else np.full(ssum.shape[0], 1.0 / ssum.shape[0])
    return avg


@dataclass
class SolveResult:
    average_strategy: Strategy
    game_value: float
    iterations: int
    variant: str
    regrets: dict = field(repr=False)
    strategy_sums: dict = field(repr=False)
    game_value_se: float | None = None  # set only when game_value came from _sampled_expected_value


def solve(
    game,
    iterations: int,
    variant: str = "cfr+",
    alpha: float = 1.5,
    beta: float = 0.0,
    gamma: float = 2.0,
) -> SolveResult:
    """Run `iterations` iterations of the requested variant
    ("vanilla" | "cfr+" | "dcfr") and return the AVERAGE strategy plus
    player 0's exact game value under it. `game` implements the extensive-
    form interface documented in this module's docstring (see
    src.poker.toy.KuhnPoker for a minimal example)."""
    if variant not in ("vanilla", "cfr+", "dcfr"):
        raise ValueError(f"unknown CFR variant: {variant!r}")

    regrets: dict[InfosetKey, np.ndarray] = {}
    strat_sums: dict[InfosetKey, np.ndarray] = {}

    for t in range(1, iterations + 1):
        if variant == "vanilla":
            _traverse(game, (), [1.0, 1.0], regrets, strat_sums, {0, 1}, strategy_weight=1.0, floor_regrets=False)
        elif variant == "cfr+":
            update_players = {(t - 1) % 2}
            _traverse(
                game, (), [1.0, 1.0], regrets, strat_sums, update_players, strategy_weight=float(t), floor_regrets=True
            )
        else:  # dcfr
            _apply_dcfr_discount(regrets, strat_sums, t, alpha, beta, gamma)
            _traverse(game, (), [1.0, 1.0], regrets, strat_sums, {0, 1}, strategy_weight=1.0, floor_regrets=False)

    avg_strategy = _average_strategy(strat_sums)
    game_value = _expected_value(game, avg_strategy, ())

    return SolveResult(avg_strategy, game_value, iterations, variant, regrets, strat_sums)


def _cached_probs(outcomes: list, cache: dict[int, np.ndarray]) -> np.ndarray:
    """Extracting and normalising a probability array from a chance node's
    (history, prob) list costs O(n); for a chance node visited every
    iteration with a large, STABLE outcome list (e.g. PreflopGame's 28,561-
    outcome deal, Phase 10), redoing this every single traversal dominated
    total solve time in early testing -- measured at 3.2ms/iteration on a
    game with only 12 betting infosets, almost all of it this extraction.
    Cached by the outcomes list's object identity, which is stable across
    iterations for any game that (like PreflopGame) builds its chance-
    outcome list once and returns the same object each call; games that
    rebuild a fresh list per call (Kuhn, Leduc) simply get no cache hit,
    harmless since their outcome counts are tiny anyway."""
    key = id(outcomes)
    cached = cache.get(key)
    if cached is None:
        probs = np.array([p for _, p in outcomes])
        cached = probs / probs.sum()
        cache[key] = cached
    return cached


def _traverse_mccfr(
    game,
    history: tuple,
    update_player: int,
    regrets: dict[InfosetKey, np.ndarray],
    strat_sums: dict[InfosetKey, np.ndarray],
    rng: np.random.Generator,
    strategy_weight: float,
    probs_cache: dict[int, np.ndarray],
) -> float:
    """One external-sampling MCCFR pass for `update_player`. Chance and the
    OTHER player's nodes each sample ONE action (weighted by their
    probability / current strategy) and recurse into only that branch;
    `update_player`'s own nodes fully explore every action, exactly as
    vanilla CFR does. Regret and strategy-sum updates at update_player's
    nodes use NO explicit reach-probability multiplier -- unlike
    _traverse's cf_reach term -- because the sampling process already makes
    each visit an unbiased estimate of the true counterfactual value (the
    standard external-sampling result, Lanctot et al. 2009); multiplying by
    reach again would double-count it.
    """
    if game.is_terminal(history):
        return game.utility(history, update_player)

    if game.is_chance(history):
        outcomes = game.chance_outcomes(history)
        probs = _cached_probs(outcomes, probs_cache)
        idx = rng.choice(len(outcomes), p=probs)
        return _traverse_mccfr(
            game, outcomes[idx][0], update_player, regrets, strat_sums, rng, strategy_weight, probs_cache
        )

    player = game.current_player(history)
    infoset = game.infoset_key(history, player)
    actions = game.legal_actions(history)
    n = len(actions)
    regret_arr = regrets.setdefault(infoset, np.zeros(n))
    strategy = _regret_matching(regret_arr)

    if player == update_player:
        action_values = np.empty(n)
        for i, a in enumerate(actions):
            action_values[i] = _traverse_mccfr(
                game,
                game.next_history(history, a),
                update_player,
                regrets,
                strat_sums,
                rng,
                strategy_weight,
                probs_cache,
            )
        node_value = float(np.dot(strategy, action_values))
        regret_arr[:] = np.maximum(regret_arr + (action_values - node_value), 0.0)
        strat_sum = strat_sums.setdefault(infoset, np.zeros(n))
        strat_sum += strategy_weight * strategy
        return node_value

    idx = int(rng.choice(n, p=strategy))
    return _traverse_mccfr(
        game,
        game.next_history(history, actions[idx]),
        update_player,
        regrets,
        strat_sums,
        rng,
        strategy_weight,
        probs_cache,
    )


def solve_mccfr(
    game,
    iterations: int,
    seed: int | None = None,
    exact_value: bool = True,
    value_samples: int = 20_000,
) -> SolveResult:
    """External-sampling MCCFR, alternating which player updates each
    iteration (matching CFR+'s alternation) with CFR+-style regret flooring
    and linear strategy-sum averaging -- the only variant that scales to
    trees too large to traverse in full (see this module's docstring for
    why the real preflop game needs this, not just "postflop").

    `exact_value` controls how the FINAL reported game_value is computed --
    NOT the regret/strategy-sum accumulation during solving, which is always
    sampled regardless. exact_value=True (the default, matching solve()'s
    behaviour, appropriate for Kuhn/Leduc-scale games) uses
    _expected_value()'s full, non-sampled enumeration. exact_value=False
    uses _sampled_expected_value() (Monte Carlo, `value_samples` playouts,
    WITH a standard error in the returned SolveResult.game_value_se) --
    required for any game too large to enumerate: profiling showed
    _expected_value's exact enumeration consuming 99.96% of total runtime
    on a spec with only 28,561 chance outcomes, for a game where the actual
    MCCFR sampling loop itself was fast -- using the exact evaluator here
    would silently defeat the entire point of choosing MCCFR in the first
    place. Callers solving anything with a large chance-outcome count (the
    real preflop game, Phase 10) MUST pass exact_value=False.
    """
    rng = np.random.default_rng(seed)
    regrets: dict[InfosetKey, np.ndarray] = {}
    strat_sums: dict[InfosetKey, np.ndarray] = {}
    probs_cache: dict[int, np.ndarray] = {}

    for t in range(1, iterations + 1):
        update_player = (t - 1) % 2
        _traverse_mccfr(
            game, (), update_player, regrets, strat_sums, rng, strategy_weight=float(t), probs_cache=probs_cache
        )

    avg_strategy = _average_strategy(strat_sums)
    if exact_value:
        game_value = _expected_value(game, avg_strategy, ())
        game_value_se = None
    else:
        game_value, game_value_se = _sampled_expected_value(game, avg_strategy, value_samples, rng)

    return SolveResult(avg_strategy, game_value, iterations, "mccfr", regrets, strat_sums, game_value_se)


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------


def save_state(result: SolveResult, path: str | Path, meta: dict | None = None) -> None:
    """Persist regrets + strategy sums (the full solver state, not just the
    averaged output -- resuming a solve needs both) plus iteration count and
    variant. Infoset keys are arbitrary hashable tuples; encoded as repr()
    strings for JSON, decoded with ast.literal_eval on load (safe: only
    literal tuples/ints/strings/bools ever appear as infoset keys, never
    arbitrary code)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    regret_keys = list(result.regrets.keys())
    strat_keys = list(result.strategy_sums.keys())
    np.savez(
        path.with_suffix(".npz"),
        regret_values=np.array([result.regrets[k] for k in regret_keys], dtype=object),
        strat_values=np.array([result.strategy_sums[k] for k in strat_keys], dtype=object),
        allow_pickle=True,
    )
    manifest = {
        "iterations": result.iterations,
        "variant": result.variant,
        "game_value": result.game_value,
        "regret_keys": [repr(k) for k in regret_keys],
        "strat_keys": [repr(k) for k in strat_keys],
        "meta": meta or {},
    }
    path.with_suffix(".json").write_text(json.dumps(manifest, indent=2))


def load_state(path: str | Path) -> SolveResult:
    path = Path(path)
    manifest = json.loads(path.with_suffix(".json").read_text())
    data = np.load(path.with_suffix(".npz"), allow_pickle=True)

    regret_keys = [ast.literal_eval(k) for k in manifest["regret_keys"]]
    strat_keys = [ast.literal_eval(k) for k in manifest["strat_keys"]]
    regrets = dict(zip(regret_keys, data["regret_values"]))
    strat_sums = dict(zip(strat_keys, data["strat_values"]))

    avg_strategy = _average_strategy(strat_sums)
    return SolveResult(
        avg_strategy, manifest["game_value"], manifest["iterations"], manifest["variant"], regrets, strat_sums
    )
