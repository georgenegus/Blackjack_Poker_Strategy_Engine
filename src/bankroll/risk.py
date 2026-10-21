"""Phase 9: risk of ruin, N0, expected time-to-double, and drawdown
percentiles for a given (bankroll, edge, variance) -- shown next to every bet
recommendation (build plan Phase 9 Step 4): "a $240 optimal bet" without "and
a 12% chance of losing this bankroll" is not advice.

risk_of_ruin and n_zero are the SAME formulas already built for Phase 8's
metrics.py -- this project's one definition of each, re-exported here rather
than duplicated, so src.bankroll is still a complete, self-contained place to
import risk-related functions from.
"""

import math
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

from src.simulation.metrics import n_zero, risk_of_ruin

__all__ = ["risk_of_ruin", "n_zero", "hours_to_double", "simulate_drawdowns", "RiskProfile", "risk_profile"]


def hours_to_double(bankroll_units: float, edge: float, hands_per_hour: float = 60.0) -> float:
    """Expected hours for the bankroll to double, from the LAW OF LARGE
    NUMBERS expectation (bankroll grows at `edge` units/hand on average) -- an
    EXPECTATION, not a guarantee; see simulate_drawdowns for how much actual
    paths vary around it. `hands_per_hour` has no hardcoded default baked into
    a table assumption -- it depends on seats at the table (Phase 8's
    other_players), so the caller must say what it actually is."""
    if edge <= 0:
        return float("inf")
    hands_needed = bankroll_units / edge
    return hands_needed / hands_per_hour


def simulate_drawdowns(
    bankroll_units: float,
    edge: float,
    variance: float,
    n_hands: int,
    n_trials: int = 10_000,
    rng: Optional[np.random.Generator] = None,
    batch_size: int = 500,
) -> Dict[str, float]:
    """The 50th/90th/99th percentile of MAXIMUM peak-to-trough drawdown (as a
    fraction of the running peak) over n_hands, across n_trials independent
    simulated bankroll paths. Per-hand results are drawn from Normal(edge,
    variance) -- the SAME Brownian-motion approximation risk_of_ruin's own
    closed form already relies on, not a new approximation; Phase 8's real
    20M-hand battery is what validated that edge/variance actually ARE
    ~edge/~variance for real blackjack outcomes, so this doesn't need to
    re-run the full game engine just to study the aggregate SHAPE of
    many-hand bankroll paths.

    Processed in batches of `batch_size` trials (not one (n_trials, n_hands)
    array) to keep peak memory bounded regardless of how large n_hands is --
    see .agents/coding-standards.md's 7.7GB dev-machine caution.
    """
    rng = rng if rng is not None else np.random.default_rng()
    sd = math.sqrt(variance)
    max_drawdowns = np.empty(n_trials)

    done = 0
    while done < n_trials:
        batch = min(batch_size, n_trials - done)
        steps = rng.normal(edge, sd, size=(batch, n_hands))
        paths = bankroll_units + np.cumsum(steps, axis=1)
        paths = np.concatenate([np.full((batch, 1), bankroll_units), paths], axis=1)
        running_peak = np.maximum.accumulate(paths, axis=1)
        drawdown = (running_peak - paths) / running_peak
        max_drawdowns[done : done + batch] = drawdown.max(axis=1)
        done += batch

    return {
        "p50": float(np.percentile(max_drawdowns, 50)),
        "p90": float(np.percentile(max_drawdowns, 90)),
        "p99": float(np.percentile(max_drawdowns, 99)),
    }


@dataclass
class RiskProfile:
    bankroll_units: float
    edge: float
    variance: float
    risk_of_ruin: float
    n_zero: float
    hours_to_double: float
    drawdown_p50: float
    drawdown_p90: float
    drawdown_p99: float


def risk_profile(
    bankroll_units: float,
    edge: float,
    variance: float,
    n_hands: int,
    hands_per_hour: float = 60.0,
    n_trials: int = 10_000,
    rng: Optional[np.random.Generator] = None,
) -> RiskProfile:
    """The full bundle to show next to a bet recommendation -- see the module
    docstring. `n_hands` is the horizon the drawdown percentiles are computed
    over; there's no default because "how many hands of play am I asking
    about" is a caller/UI decision, not something to bury silently."""
    drawdowns = simulate_drawdowns(bankroll_units, edge, variance, n_hands, n_trials, rng)
    return RiskProfile(
        bankroll_units=bankroll_units,
        edge=edge,
        variance=variance,
        risk_of_ruin=risk_of_ruin(bankroll_units, edge, variance),
        n_zero=n_zero(edge, variance),
        hours_to_double=hours_to_double(bankroll_units, edge, hands_per_hour),
        drawdown_p50=drawdowns["p50"],
        drawdown_p90=drawdowns["p90"],
        drawdown_p99=drawdowns["p99"],
    )
