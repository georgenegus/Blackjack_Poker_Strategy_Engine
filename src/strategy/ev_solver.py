"""Exact EV of every player action, by recursive enumeration over the shoe.

EV(action | player_hand, dealer_upcard, shoe_composition, rules) for
action in {stand, hit, double, split, surrender}. This is the one component
the whole project depends on: the strategy grid (Phase 4) is its argmax, the
count indices (Phase 7) are the true counts where that argmax flips, and the
Kelly bet (Phase 9) is a function of its value. See ev_solver_conventions/SKILL.md.
"""

from typing import Dict, List, Tuple

import numpy as np

from src.engine.cards import NUM_BUCKETS, advance_total
from src.engine.rules import RuleSet
from src.strategy.dealer_probs import dealer_distribution

# Unbounded for now, same rationale as dealer_probs.py -- Phase 4 caches finished
# grids to disk rather than relying on these process-lifetime memos.
_ev_hit_memo: Dict[tuple, float] = {}
_ev_split_memo: Dict[tuple, float] = {}


def _compare(player_total: int, dealer_total: int) -> float:
    if player_total > dealer_total:
        return 1.0
    if player_total < dealer_total:
        return -1.0
    return 0.0


def ev_stand(total: int, upcard: int, comp: Tuple[int, ...], rules: RuleSet) -> float:
    """EV of standing on `total` right now. `comp` excludes the player's own cards
    and the dealer's upcard, but includes the dealer's (unseen) hole card."""
    dist = dealer_distribution(upcard, np.asarray(comp, dtype=np.int64), rules)
    payoff = np.array([_compare(total, d) for d in (17, 18, 19, 20, 21)] + [1.0])
    return float(np.dot(dist, payoff))


def ev_hit(total: int, is_soft: bool, upcard: int, comp: Tuple[int, ...], rules: RuleSet) -> float:
    """EV of hitting exactly once now, then playing optimally (best of stand/hit)
    from whatever state results. The max() over the next state's stand/hit values
    is what makes this optimal-play EV rather than fixed-strategy EV."""
    key = (total, is_soft, upcard, comp, rules)
    cached = _ev_hit_memo.get(key)
    if cached is not None:
        return cached

    remaining = sum(comp)
    comp_list = list(comp)
    result = 0.0
    for r in range(NUM_BUCKETS):
        n = comp_list[r]
        if n == 0:
            continue
        p = n / remaining
        comp_list[r] -= 1
        new_total, new_soft = advance_total(total, is_soft, r)
        new_comp = tuple(comp_list)
        if new_total > 21:
            branch_ev = -1.0
        else:
            branch_ev = max(
                ev_stand(new_total, upcard, new_comp, rules),
                ev_hit(new_total, new_soft, upcard, new_comp, rules),
            )
        result += p * branch_ev
        comp_list[r] += 1

    _ev_hit_memo[key] = result
    return result


def ev_double(total: int, is_soft: bool, upcard: int, comp: Tuple[int, ...], rules: RuleSet) -> float:
    """EV of doubling: exactly one more card, bet doubled, then forced to stand."""
    remaining = sum(comp)
    comp_list = list(comp)
    inner = 0.0
    for r in range(NUM_BUCKETS):
        n = comp_list[r]
        if n == 0:
            continue
        p = n / remaining
        comp_list[r] -= 1
        new_total, _ = advance_total(total, is_soft, r)
        branch_ev = -1.0 if new_total > 21 else ev_stand(new_total, upcard, tuple(comp_list), rules)
        inner += p * branch_ev
        comp_list[r] += 1
    return 2.0 * inner


def ev_surrender() -> float:
    """EV of surrendering: lose exactly half the bet, unconditionally. Legality
    (first action only, rules.surrender != 'none') is the caller's responsibility --
    every ev_* function here computes 'what if', not 'is this legal'."""
    return -0.5


def ev_split_hand(
    split_rank: int,
    upcard: int,
    comp: Tuple[int, ...],
    rules: RuleSet,
    hands_so_far: int,
    is_aces: bool,
) -> float:
    """EV of ONE hand resulting from splitting `split_rank`, given a shoe composition
    with the pair's two original cards already removed. `hands_so_far` counts hands
    along THIS hand's own resplit lineage only (starting at 2, since splitting the
    original hand always takes the round from 1 hand to 2) -- it does not coordinate
    with the sibling hand's own resplit count. That is consistent with, not an
    additional approximation beyond, the plan's documented 2x-independent-hands
    treatment of ev_split itself: since the two post-split hands are already treated
    as statistically independent, there is no true shared state to track between them.

    Mirrors game.py's split/resplit/split-aces mechanics exactly (same short-circuit
    for is_aces and not rules.hit_split_aces), so the solved grid matches how a round
    actually plays.
    """
    key = (split_rank, upcard, comp, rules, hands_so_far, is_aces)
    cached = _ev_split_memo.get(key)
    if cached is not None:
        return cached

    t1, s1 = advance_total(0, False, split_rank)
    remaining = sum(comp)
    comp_list = list(comp)
    result = 0.0
    for r2 in range(NUM_BUCKETS):
        n = comp_list[r2]
        if n == 0:
            continue
        p = n / remaining
        comp_list[r2] -= 1
        new_comp = tuple(comp_list)
        total, is_soft = advance_total(t1, s1, r2)

        if is_aces and not rules.hit_split_aces:
            # The one card split aces receive was this r2 draw. Normally no further
            # action -- UNLESS r2 is itself another ace and resplit_aces is allowed,
            # in which case RESPLITTING (only, not hitting) is still offered.
            # "Resplit aces" and "hit split aces" are independent casino rule
            # toggles in standard terminology, not one gating the other.
            can_resplit_aces = r2 == split_rank and rules.resplit_aces and hands_so_far < rules.resplit_to
            if can_resplit_aces:
                branch_ev = max(
                    ev_stand(total, upcard, new_comp, rules),
                    2.0 * ev_split_hand(split_rank, upcard, new_comp, rules, hands_so_far + 1, is_aces),
                )
            else:
                branch_ev = ev_stand(total, upcard, new_comp, rules)
        else:
            candidates: List[float] = [
                ev_stand(total, upcard, new_comp, rules),
                ev_hit(total, is_soft, upcard, new_comp, rules),
            ]
            if rules.double_after_split:
                candidates.append(ev_double(total, is_soft, upcard, new_comp, rules))
            can_resplit = (
                r2 == split_rank
                and hands_so_far < rules.resplit_to
                and not (is_aces and not rules.resplit_aces)
            )
            if can_resplit:
                # Resplitting turns THIS one hand (1 unit, the scale every other
                # candidate here is on) into two new hands -- the same 2x the
                # top-level ev_split() applies to the original pair, just recursed.
                # Omitting this factor undervalues every resplit opportunity by half.
                candidates.append(
                    2.0 * ev_split_hand(split_rank, upcard, new_comp, rules, hands_so_far + 1, is_aces)
                )
            branch_ev = max(candidates)

        result += p * branch_ev
        comp_list[r2] += 1

    _ev_split_memo[key] = result
    return result


def ev_split(split_rank: int, upcard: int, comp: Tuple[int, ...], rules: RuleSet, is_aces: bool) -> float:
    """EV of splitting a pair of `split_rank`. `comp` must have BOTH cards of the
    pair already removed (they are known, not drawn from the shoe). Treats the two
    resulting hands as independent -- see ev_split_hand's docstring and
    ev_solver_conventions/SKILL.md's "Split EV Treatment" -- required to match the
    published charts in the build plan's Appendix A, not a bug to fix into full
    joint two-hand enumeration."""
    return 2.0 * ev_split_hand(split_rank, upcard, comp, rules, hands_so_far=2, is_aces=is_aces)
