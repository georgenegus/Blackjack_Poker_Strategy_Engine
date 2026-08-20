"""Exact dealer outcome distribution via recursive enumeration over the shoe.

This is the foundation the whole solver sits on -- see the module docstring's
warning in ev_solver_conventions/SKILL.md about peek conditioning being the
single most common blackjack-solver bug.
"""

from typing import Dict, Optional, Tuple

import numpy as np

from src.engine.cards import NUM_BUCKETS, RANK_INDEX, advance_total
from src.engine.rules import RuleSet

OUTCOME_LABELS = ["17", "18", "19", "20", "21", "BUST"]
_ACE = RANK_INDEX["A"]
_TEN = RANK_INDEX["T"]

# Unbounded for now -- Phase 3 scope is correctness, not memory management. Grid
# pre-solving (Phase 4) caches finished grids to disk instead of relying on this
# process-lifetime memo, so this is not expected to need eviction in practice.
_recurse_memo: Dict[tuple, np.ndarray] = {}


def _bucket_for_value(value: int) -> int:
    """Convert an upcard's point value (2-11, 11=Ace) to its rank bucket index."""
    if value == 11:
        return _ACE
    if value == 10:
        return _TEN
    return value - 2


def _recurse(total: int, is_soft: bool, comp: Tuple[int, ...], hits_soft_17: bool) -> np.ndarray:
    key = (total, is_soft, comp, hits_soft_17)
    cached = _recurse_memo.get(key)
    if cached is not None:
        return cached

    if total > 21:
        result = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 1.0])
    elif total >= 17 and not (total == 17 and is_soft and hits_soft_17):
        result = np.zeros(6)
        result[total - 17] = 1.0
    else:
        remaining = sum(comp)
        result = np.zeros(6)
        comp_list = list(comp)
        for r in range(NUM_BUCKETS):
            n = comp_list[r]
            if n == 0:
                continue
            p = n / remaining
            comp_list[r] -= 1
            new_total, new_soft = advance_total(total, is_soft, r)
            result = result + p * _recurse(new_total, new_soft, tuple(comp_list), hits_soft_17)
            comp_list[r] += 1

    _recurse_memo[key] = result
    return result


def dealer_distribution(
    upcard: int, comp: np.ndarray, rules: RuleSet, peek_conditioned: Optional[bool] = None
) -> np.ndarray:
    """P over [17, 18, 19, 20, 21, BUST] for the dealer's final total.

    `upcard` is the up card's point value (2-11, 11=Ace) -- not a rank bucket index.
    `comp` is the shoe composition remaining AFTER removing the upcard itself; the
    caller is responsible for that removal.

    When `peek_conditioned` is left as None (the default), it is auto-determined as
    `rules.dealer_peeks and upcard in (10, 11)` -- the two upcards where a dealer
    blackjack is possible. Conditioning affects only the hole card's own identity
    (the one card the peek rules out); every card drawn afterwards -- every dealer
    hit -- still draws from the full, unconditioned composition, since the peek says
    nothing about them. Applying the exclusion to the whole recursion instead of just
    the hole card is the classic peek-conditioning bug -- see ev_solver_conventions.
    """
    comp = np.asarray(comp, dtype=np.int64)
    if peek_conditioned is None:
        peek_conditioned = rules.dealer_peeks and upcard in (10, 11)

    total0, soft0 = advance_total(0, False, _bucket_for_value(upcard))

    if not peek_conditioned:
        return _recurse(total0, soft0, tuple(int(x) for x in comp), rules.dealer_hits_soft_17)

    excluded_bucket = _ACE if upcard == 10 else _TEN
    remaining = int(comp.sum())
    conditioned_remaining = remaining - int(comp[excluded_bucket])
    result = np.zeros(6)
    for r in range(NUM_BUCKETS):
        if r == excluded_bucket or comp[r] == 0:
            continue
        p = comp[r] / conditioned_remaining
        new_total, new_soft = advance_total(total0, soft0, r)
        new_comp = comp.copy()
        new_comp[r] -= 1
        result = result + p * _recurse(
            new_total, new_soft, tuple(int(x) for x in new_comp), rules.dealer_hits_soft_17
        )
    return result
