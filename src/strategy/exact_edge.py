"""Exact (non-simulated) house edge under perfect basic strategy: a full
combinatorial weighted enumeration over every possible initial deal, using
ev_solver.py's functions directly on the SPECIFIC composition-dependent shoe
for each deal rather than the grid's total-dependent cached values. Zero
sampling noise -- built as a diagnostic when Phase 5's Monte Carlo house-edge
check (test_house_edge.py) showed a persistent, multi-standard-error gap from
published anchors that survived a fresh_shoe_per_hand fix, to isolate whether
the cause is in the solver/grid layer or the game.py/simulation integration
layer. Also usable for the build plan's deferred Check 3 (rule-effect deltas),
since it's fast (seconds, not tens of minutes) and exact.

Currently assumes rules.dealer_peeks=True and rules.surrender in comparisons
it makes -- sufficient for the Phase 5 anchor rulesets (S17, DAS, no
surrender, 3:2, peek), not yet generalised to no-peek/OBBO settlement.
"""

from typing import Tuple

from src.engine.cards import HARD_VALUE, NUM_BUCKETS, RANK_INDEX, advance_total
from src.engine.rules import RuleSet, double_allowed
from src.engine.shoe import Shoe
from src.strategy.ev_solver import ev_double, ev_hit, ev_split, ev_stand, ev_surrender

_ACE = RANK_INDEX["A"]
_TEN = RANK_INDEX["T"]


def _best_action_ev(total: int, is_soft: bool, is_pair: bool, pair_bucket: int, upcard: int, comp: Tuple[int, ...], rules: RuleSet) -> float:
    candidates = [ev_stand(total, upcard, comp, rules), ev_hit(total, is_soft, upcard, comp, rules)]
    if double_allowed(rules, total, is_soft):
        candidates.append(ev_double(total, is_soft, upcard, comp, rules))
    if rules.surrender != "none":
        candidates.append(ev_surrender())
    if is_pair:
        is_aces = pair_bucket == _ACE
        candidates.append(ev_split(pair_bucket, upcard, comp, rules, is_aces=is_aces))
    return max(candidates)


def exact_house_edge(rules: RuleSet) -> float:
    """Exact house edge (positive = house advantage) under perfect basic
    strategy, weighted over every possible (player card 1, player card 2,
    dealer upcard) deal from a fresh shoe. Assumes rules.dealer_peeks=True."""
    assert rules.dealer_peeks, "exact_house_edge currently assumes dealer_peeks=True"

    full = Shoe(rules.num_decks).composition
    total_weight = 0.0
    total_ev = 0.0

    for b1 in range(NUM_BUCKETS):
        n1 = full[b1]
        if n1 == 0:
            continue
        after1 = full.copy()
        after1[b1] -= 1
        for b2 in range(NUM_BUCKETS):
            n2 = after1[b2]
            if n2 == 0:
                continue
            after2 = after1.copy()
            after2[b2] -= 1
            for bd in range(NUM_BUCKETS):
                n3 = after2[bd]
                if n3 == 0:
                    continue
                weight = float(n1) * float(n2) * float(n3)
                comp = after2.copy()
                comp[bd] -= 1
                comp_t = tuple(int(x) for x in comp)

                t1, s1 = advance_total(0, False, b1)
                total, is_soft = advance_total(t1, s1, b2)
                is_pair = b1 == b2
                is_player_bj = (total == 21) and is_soft and not is_pair

                upcard_value = HARD_VALUE[bd]
                remaining = comp.sum()

                if upcard_value in (10, 11):
                    excluded_bucket = _ACE if upcard_value == 10 else _TEN
                    p_dealer_bj = float(comp[excluded_bucket]) / float(remaining)
                else:
                    p_dealer_bj = 0.0

                if is_player_bj:
                    cell_ev = p_dealer_bj * 0.0 + (1.0 - p_dealer_bj) * float(rules.blackjack_payout)
                else:
                    if p_dealer_bj > 0.0:
                        best_ev = _best_action_ev(total, is_soft, is_pair, b1, upcard_value, comp_t, rules)
                        cell_ev = p_dealer_bj * (-1.0) + (1.0 - p_dealer_bj) * best_ev
                    else:
                        cell_ev = _best_action_ev(total, is_soft, is_pair, b1, upcard_value, comp_t, rules)

                total_weight += weight
                total_ev += weight * cell_ev

    return -(total_ev / total_weight)
