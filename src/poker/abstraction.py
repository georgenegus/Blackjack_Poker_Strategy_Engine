"""Phase 6: card abstraction. See markdowns/poker/poker_build_plan_v1.md
Phase 6 and .agents/skills/poker_solver_conventions/SKILL.md.

Preflop needs no abstraction at all -- the 169 canonical classes (Phase 1's
suit-isomorphism collapse, exposed here via src.poker.ranges) are already a
LOSSLESS grouping, not an approximation. Flop and later streets do need real
abstraction (there is no lossless finite grouping once the board is dealt),
built here as: cluster hole-card combos by expected hand strength vs a
random opponent (Monte Carlo), via k-means.

Scope note: the build plan describes a two-step feature progression --
"start with expected hand strength squared, E[HS^2], then move to
potential-aware equity-distribution histograms" clustered by earth-mover
distance. This module ships the first step (a single scalar feature per
combo, k-means, Euclidean distance) -- the histogram/EMD refinement is
deferred, since nothing downstream consumes it yet (Phase 7's CFR hasn't
landed) and it is a substantially larger undertaking than this version.
Bucket count `k` is a GameSpec-adjacent parameter: a solve at k=200 and one
at k=5,000 are answers to different abstracted games and must not collide on
the same cache key once Phase 7 starts persisting solves.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
from scipy.cluster.vq import kmeans2

from src.poker.evaluator import evaluate_batch
from src.poker.ranges import Combo, hand_classes


def preflop_buckets() -> list[int]:
    """The lossless preflop card abstraction: one bucket id per concrete
    starting-hand combo (ordered by itertools.combinations(range(52), 2)),
    where each of the 169 canonical classes IS exactly one bucket -- no
    information is thrown away, unlike every later street's abstraction.
    len(set(preflop_buckets())) == 169."""
    labels, groups = hand_classes()
    bucket_of: dict[Combo, int] = {}
    for i, combos in enumerate(groups):
        for c in combos:
            bucket_of[c] = i
    return [bucket_of[c] for c in combinations(range(52), 2)]


def hand_strength_feature(hole: Combo, board: tuple[int, ...], n_samples: int = 2000, seed: int | None = None) -> float:
    """Monte Carlo estimate of `hole`'s equity against a uniformly random
    valid opponent hand, with any remaining board cards dealt randomly too.
    The clustering feature flop_buckets() uses."""
    rng = np.random.default_rng(seed)
    known = set(board) | set(hole)
    remaining = np.array([c for c in range(52) if c not in known], dtype=np.int64)
    n_board_needed = 5 - len(board)
    n_needed = 2 + n_board_needed  # opponent's hole cards + the rest of the board

    order = np.argsort(rng.random((n_samples, len(remaining))), axis=1)
    dealt = remaining[order[:, :n_needed]]
    opp = dealt[:, :2]
    rest_board = dealt[:, 2:]
    board_arr = np.asarray(board, dtype=np.int64)
    full_board = (
        np.concatenate([np.tile(board_arr, (n_samples, 1)), rest_board], axis=1) if len(board_arr) else rest_board
    )

    hole_arr = np.asarray(hole, dtype=np.int64)
    hero_hand = np.concatenate([np.tile(hole_arr, (n_samples, 1)), full_board], axis=1)
    opp_hand = np.concatenate([opp, full_board], axis=1)
    hero_val = evaluate_batch(hero_hand)
    opp_val = evaluate_batch(opp_hand)

    win = (hero_val < opp_val).astype(np.float64)
    tie = (hero_val == opp_val).astype(np.float64) * 0.5
    return float((win + tie).mean())


def flop_buckets(board: tuple[int, ...], k: int, n_samples: int = 2000, seed: int | None = None) -> dict[Combo, int]:
    """Cluster every hole-card combo compatible with `board` into `k`
    buckets by expected hand strength vs a random opponent (Monte Carlo
    feature, k-means clustering). Works for any 3/4/5-card board (flop,
    turn, or river), despite the name -- "flop" names the use case (the
    first street that needs abstraction at all), not a length restriction.
    """
    board_set = set(board)
    combos = [c for c in combinations(range(52), 2) if not (set(c) & board_set)]
    features = np.array(
        [
            hand_strength_feature(c, board, n_samples=n_samples, seed=None if seed is None else seed + i)
            for i, c in enumerate(combos)
        ]
    )
    k_eff = min(k, len(combos))
    _, labels = kmeans2(features.reshape(-1, 1), k_eff, seed=seed, minit="++")
    return {c: int(lbl) for c, lbl in zip(combos, labels)}
