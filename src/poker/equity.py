"""Phase 3: exact equity by full runout enumeration where the runout count is
tractable, falling back to Monte Carlo -- always paired with a standard error
-- otherwise. See markdowns/poker/poker_build_plan_v1.md Phase 3 and
.agents/skills/poker_evaluator_conventions/SKILL.md.

Equity is the probability of winning at showdown given the currently known
cards, counting ties as fractional wins. It is NOT expected value -- EV also
depends on fold equity and the ability to realise equity through future
betting. Every function here returns equity only; naming that distinction
correctly at every call site is a discipline problem the plan calls out
explicitly, not a computational one.
"""
from __future__ import annotations

from itertools import combinations, islice
from math import comb

import numpy as np

from src.poker.evaluator import evaluate_batch

EXACT_LIMIT = 5_000_000  # enumerate below this many runouts; sample above it


def runout_count(n_known_cards: int, n_needed: int) -> int:
    """How many distinct ways the remaining `n_needed` board cards can come
    from the 52 - n_known_cards cards not yet accounted for."""
    return comb(52 - n_known_cards, n_needed)


def _chunked_combinations(pool, r, chunk_size):
    """Yield combinations(pool, r) in batches of up to chunk_size, so a large
    enumeration is never materialised as one array in memory at once (the
    build plan's WARNING about the 7.7GB dev machine)."""
    it = combinations(pool, r)
    while True:
        batch = list(islice(it, chunk_size))
        if not batch:
            return
        yield batch


def _player_values(hole_arrs: list[np.ndarray], full_boards: np.ndarray) -> np.ndarray:
    """hole_arrs: one (2,) array of hole-card ids per player; full_boards:
    (M, 5) array of complete boards. -> (M, n_players) int32 evaluate_batch
    results, lower = stronger."""
    m = full_boards.shape[0]
    values = np.empty((m, len(hole_arrs)), dtype=np.int32)
    for p, hole in enumerate(hole_arrs):
        seven = np.concatenate([np.tile(hole, (m, 1)), full_boards], axis=1)
        values[:, p] = evaluate_batch(seven)
    return values


def _known_and_remaining(hands, board):
    known = set(board)
    for h in hands:
        known.update(h)
    remaining = [c for c in range(52) if c not in known]
    return known, remaining


def _enumerate_shares(hands, board, chunk_size: int = 200_000):
    """Yield (M, n_players) float64 per-runout equity shares (1/n_winners for
    each winner, 0 for everyone else -- a full pot split shows up as multiple
    fractional winners) across every runout of the missing board cards, in
    chunks. The one enumeration loop shared by equity_exact (reduces to the
    mean) and equity_distribution (reduces to a histogram) -- kept as a single
    implementation so the two can never quietly disagree."""
    _, remaining = _known_and_remaining(hands, board)
    n_needed = 5 - len(board)
    board_arr = np.asarray(board, dtype=np.int64)
    hole_arrs = [np.asarray(h, dtype=np.int64) for h in hands]

    for batch in _chunked_combinations(remaining, n_needed, chunk_size):
        chunk = np.asarray(batch, dtype=np.int64)
        m = chunk.shape[0]
        full_boards = np.concatenate([np.tile(board_arr, (m, 1)), chunk], axis=1) if len(board_arr) else chunk
        values = _player_values(hole_arrs, full_boards)
        best = values.min(axis=1, keepdims=True)
        wins = values == best
        n_winners = wins.sum(axis=1, keepdims=True)
        yield wins / n_winners


def equity_exact(hands, board, spec=None) -> np.ndarray:
    """Exact equity for len(hands) players via full enumeration of every
    possible runout of the missing board cards. hands[i] is player i's two
    hole cards; board is the 0/3/4/5 already-known board cards. Returns an
    array of length len(hands) summing to exactly 1.0; ties split the pot
    fractionally. `spec` is accepted but currently unused -- reserved so this
    signature stays stable for callers (Phase 12's API) that may need to pass
    one for reasons unrelated to the equity computation itself.
    """
    n_players = len(hands)
    total = np.zeros(n_players, dtype=np.float64)
    n_runouts = 0
    for shares in _enumerate_shares(hands, board):
        total += shares.sum(axis=0)
        n_runouts += shares.shape[0]
    return total / n_runouts


def equity_distribution(hands, board, spec=None) -> list[dict]:
    """The distribution of each player's per-runout equity share (1.0 win,
    0.0 loss, a fraction for a multiway tie) -- not just its mean. Exact
    enumeration only, reusing the same runout loop as equity_exact, so it is
    only appropriate at the same scale equity_exact is (heads-up/3-way at any
    street is always well under EXACT_LIMIT). Returns one {value: probability}
    dict per player. A range's own distribution against a hand is a
    combo-weighted mixture of single-combo distributions like this one --
    that composition belongs to src.poker.ranges.Range once Phase 4 lands,
    not here, so this module carries no dependency on it.
    """
    n_players = len(hands)
    counts: list[dict] = [{} for _ in range(n_players)]
    n_runouts = 0
    for shares in _enumerate_shares(hands, board):
        n_runouts += shares.shape[0]
        for p in range(n_players):
            vals, cnts = np.unique(shares[:, p], return_counts=True)
            d = counts[p]
            for v, c in zip(vals.tolist(), cnts.tolist()):
                d[v] = d.get(v, 0) + c
    return [{v: c / n_runouts for v, c in d.items()} for d in counts]


def equity_mc(hands, board, n: int = 100_000, seed: int | None = None, chunk_size: int = 200_000):
    """Monte Carlo equity via random sampling of runouts (without
    replacement, vectorised per chunk). Returns (equities, standard_errors)
    -- there is deliberately no single-value convenience wrapper, per this
    repo's "no bare point estimates from Monte Carlo" rule
    (.agents/instructions.md), applied here unmodified. The standard error
    comes from the empirical variance of each player's own per-runout equity
    share (which is 0/1 for a clean win/loss but fractional on a tie), not
    the p(1-p)/n binomial approximation -- ties are common enough on some
    boards that the approximation would understate the true variance there.
    """
    rng = np.random.default_rng(seed)
    n_players = len(hands)
    _, remaining = _known_and_remaining(hands, board)
    remaining_arr = np.asarray(remaining, dtype=np.int64)
    n_needed = 5 - len(board)
    board_arr = np.asarray(board, dtype=np.int64)
    hole_arrs = [np.asarray(h, dtype=np.int64) for h in hands]

    total = np.zeros(n_players, dtype=np.float64)
    total_sq = np.zeros(n_players, dtype=np.float64)
    done = 0
    while done < n:
        m = min(chunk_size, n - done)
        if n_needed > 0:
            order = np.argsort(rng.random((m, len(remaining_arr))), axis=1)
            chosen = remaining_arr[order[:, :n_needed]]
            full_boards = np.concatenate([np.tile(board_arr, (m, 1)), chosen], axis=1) if len(board_arr) else chosen
        else:
            full_boards = np.tile(board_arr, (m, 1))
        values = _player_values(hole_arrs, full_boards)
        best = values.min(axis=1, keepdims=True)
        wins = values == best
        n_winners = wins.sum(axis=1, keepdims=True)
        shares = wins / n_winners
        total += shares.sum(axis=0)
        total_sq += (shares**2).sum(axis=0)
        done += m

    mean = total / n
    if n > 1:
        var = np.clip((total_sq - n * mean**2) / (n - 1), 0.0, None)
        se = np.sqrt(var / n)
    else:
        se = np.zeros(n_players)
    return mean, se


def equity(hands, board, spec=None, *, n_samples: int = 100_000, seed: int | None = None):
    """Dispatch to equity_exact when the runout count is at or below
    EXACT_LIMIT, else to equity_mc -- never samples a spot that could have
    been enumerated exactly. Returns (equities, standard_errors);
    standard_errors is None on the exact path, since there is no sampling
    error to report there.
    """
    n_known = len(board) + sum(len(h) for h in hands)
    n_needed = 5 - len(board)
    if runout_count(n_known, n_needed) <= EXACT_LIMIT:
        return equity_exact(hands, board, spec), None
    return equity_mc(hands, board, n=n_samples, seed=seed)
