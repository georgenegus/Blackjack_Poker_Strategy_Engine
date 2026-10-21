"""Phase 11: bankroll, variance, and risk of ruin. See
markdowns/poker/poker_build_plan_v1.md Phase 11. The poker-shaped analogue
of the blackjack area's Kelly and risk-of-ruin layer, but with the units
and formulas poker actually uses.

Units, fixed throughout this module and never assumed anywhere else: win
rate `w` and standard deviation `s` in bb/100 hands (the standard poker
convention -- NOT per-hand), bankroll/downswing/buy-in in bb (or any other
currency-like unit, as long as it's the SAME unit as win_rate_bb100/
stdev_bb100 were measured in). The bb/100 <-> per-hand conversion cancels
inside risk_of_ruin's own compact closed form, which is why it's correct as
written and must never be "fixed" by reintroducing a hands-based
normalisation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def risk_of_ruin(bankroll_bb: float, win_rate_bb100: float, stdev_bb100: float) -> float:
    """P(a bankroll of bankroll_bb is EVER entirely lost), for a random walk
    with per-hand drift win_rate_bb100/100 and per-hand variance
    (stdev_bb100/100)**2 -- the classical closed-form ruin probability for a
    Brownian-motion approximation to a bankroll random walk with positive
    drift: exp(-2*B*w/s**2). A non-positive win rate has no such closed
    form (a walk without positive drift is certain to hit any fixed lower
    barrier eventually, given infinite time) -- returns 1.0 (certain ruin)
    rather than evaluating the formula into a wrong answer or raising."""
    if bankroll_bb <= 0.0:
        return 1.0
    if win_rate_bb100 <= 0.0:
        return 1.0
    return math.exp(-2.0 * bankroll_bb * win_rate_bb100 / (stdev_bb100**2))


def probability_of_downswing(depth_bb: float, win_rate_bb100: float, stdev_bb100: float) -> float:
    """P(a downswing of AT LEAST depth_bb is EVER experienced, relative to
    a running bankroll peak) -- the plan's own emphasis: "the number that
    actually stops people playing." Mathematically identical first-passage
    problem to risk_of_ruin (falling depth_bb below the current peak is the
    same random walk hitting the same kind of barrier as losing a bankroll
    of that size outright), so this is deliberately the same closed form,
    not a separate derivation to keep in sync."""
    return risk_of_ruin(depth_bb, win_rate_bb100, stdev_bb100)


def required_bankroll_bb(win_rate_bb100: float, stdev_bb100: float, target_ror: float) -> float:
    """The closed-form inverse of risk_of_ruin: how many bb of bankroll are
    needed to hold risk of ruin AT OR UNDER target_ror, for this win
    rate/stdev. Solving exp(-2*B*w/s**2) = target_ror for B directly
    (log-linear in B), not a numeric search -- the formula is invertible in
    closed form."""
    if not (0.0 < target_ror < 1.0):
        raise ValueError("target_ror must be in (0, 1)")
    if win_rate_bb100 <= 0.0:
        raise ValueError("required_bankroll_bb needs a positive win rate -- a non-winning player has no bankroll that bounds ruin below certainty")
    return -math.log(target_ror) * (stdev_bb100**2) / (2.0 * win_rate_bb100)


def win_rate_standard_error(stdev_bb100: float, n_hands: float) -> float:
    """SE of an OBSERVED win rate over n_hands, in bb/100: s / sqrt(n/100)."""
    if n_hands <= 0.0:
        raise ValueError("n_hands must be positive")
    return stdev_bb100 / math.sqrt(n_hands / 100.0)


def win_rate_confidence_interval(
    observed_bb100: float, stdev_bb100: float, n_hands: float, z: float = 1.96
) -> tuple[float, float]:
    """(low, high) bb/100 confidence bounds at the given z-score (default
    1.96, ~95%). The single most useful number this module produces, per
    the plan's own emphasis: "your win rate: 5.2 bb/100" from a 20k-hand
    sample without its +/-14 is not reporting a measurement -- most winning
    players' TRUE win rates live inside a 1,000,000-hand sample's own +/-2
    bb/100 interval end to end."""
    half_width = z * win_rate_standard_error(stdev_bb100, n_hands)
    return observed_bb100 - half_width, observed_bb100 + half_width


@dataclass
class StakeRecommendation:
    total_bankroll: float
    target_ror: float
    safety_factor: float
    effective_target_ror: float
    required_bankroll_bb: float
    max_buyin: float  # largest 100bb buy-in size, in the SAME units as total_bankroll


def recommend_max_buyin(
    total_bankroll: float,
    win_rate_bb100: float,
    stdev_bb100: float,
    target_ror: float,
    safety_factor: float = 0.5,
) -> StakeRecommendation:
    """The largest 100bb buy-in size (in whatever currency-like unit
    total_bankroll is denominated in -- dollars, chips, anything) a player
    can choose while keeping risk of ruin at or under
    safety_factor * target_ror. Defaults to HALF the user's stated risk
    tolerance -- the poker-shaped analogue of the blackjack area's
    half-Kelly default: the bet size here isn't continuously scalable (you
    pick a stake, not a fraction of bankroll per hand), so the equivalent
    conservatism is applied to the RISK TARGET instead, buffering against
    the fact that win_rate_bb100/stdev_bb100 are themselves only ever
    ESTIMATES (see win_rate_confidence_interval) and a skilled player's edge
    as a FRACTION of the stake is only APPROXIMATELY stable across nearby
    stakes, not exactly. Larger buy-ins mean FEWER bb of bankroll for a
    fixed total_bankroll, which risk_of_ruin makes strictly WORSE -- so the
    max safe buy-in corresponds to exactly the MINIMUM bankroll_bb that
    still clears the safety-adjusted target, found via
    required_bankroll_bb's closed-form inversion."""
    if total_bankroll <= 0.0:
        raise ValueError("total_bankroll must be positive")
    effective_target = safety_factor * target_ror
    min_bankroll_bb = required_bankroll_bb(win_rate_bb100, stdev_bb100, effective_target)
    max_buyin = total_bankroll / (min_bankroll_bb / 100.0)
    return StakeRecommendation(total_bankroll, target_ror, safety_factor, effective_target, min_bankroll_bb, max_buyin)
