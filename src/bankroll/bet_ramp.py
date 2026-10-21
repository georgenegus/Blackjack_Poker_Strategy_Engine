"""Phase 9: converts the continuous Kelly curve (Phase 8's edge model, swept
across true count) into a small, MEMORISABLE, discrete bet ramp -- see the
build plan's Phase 9 Step 3.

Snaps to the standard doubling progression (1, 2, 4, 8, 16, ...) rather than
rounding to the raw continuous Kelly proportion: memorability at the table is
the whole point of a "ramp" as opposed to just calling kelly_bet() fresh every
hand (which would already be optimal, just impossible to execute reliably by
eye at a live table). The resulting gap versus the unconstrained Kelly curve
is exactly what RampLevel.ev_cost measures -- report it, don't bury it (see
.agents/instructions.md's "No Bare Point Estimates").
"""

from dataclasses import dataclass
from typing import Dict, Iterable

from src.bankroll.kelly import clamp_and_round, kelly_fraction
from src.counting.edge_model import EdgeModel, predict_edge

_RAMP_LEVELS = (1, 2, 4, 8, 16, 32, 64, 128)  # doubling -- the standard memorable convention


def _snap_to_ramp_level(raw_units: float, max_spread: float) -> int:
    """Largest doubling level that does not exceed what Kelly actually
    justifies -- rounds DOWN, never up, matching half-Kelly's own hedge-
    against-overbetting spirit -- capped at max_spread (a cover constraint,
    not a mathematical one)."""
    capped = min(raw_units, max_spread)
    eligible = [lvl for lvl in _RAMP_LEVELS if lvl <= capped]
    return eligible[-1] if eligible else 1


def _growth_rate(fraction_of_bankroll: float, edge: float, variance: float) -> float:
    """g(f) = f*edge - 0.5*f^2*variance -- the standard quadratic approximation
    to expected log-growth (a Taylor expansion of E[log(1+f*X)] around f=0,
    valid for the small per-hand fractions blackjack bets actually are). This
    is the SAME formula kelly_fraction's own e/variance optimum falls out of
    (maximising g(f) over f gives f*=edge/variance at fraction=1.0) -- reusing
    it here for the ramp's EV-cost accounting keeps the two internally
    consistent rather than comparing against a different growth model."""
    return fraction_of_bankroll * edge - 0.5 * fraction_of_bankroll**2 * variance


@dataclass
class RampLevel:
    true_count: int
    edge: float
    raw_kelly_units: float   # unconstrained Kelly bet, in units of table_min
    ramp_units: int          # the memorisable, snapped bet size actually used
    ramp_bet: float          # ramp_units converted to dollars, chip-rounded and table-clamped
    ev_cost: float
    """unconstrained-Kelly growth rate minus the ramp's, at this TC. Usually
    positive (snapping DOWN from raw_kelly_units>=1 strictly costs growth,
    since g(f) is increasing below the full-Kelly peak and half-Kelly's own
    fraction is always below it) -- but can go slightly NEGATIVE (a tiny gain,
    not a cost) in the one case where raw_kelly_units is between 0 and 1: the
    mandatory table_min floor then bets MORE than raw Kelly wants, and that can
    land closer to the true full-Kelly peak than half-Kelly's own target does.
    Confirmed against the real locked Phase 8 baseline, not a hypothetical --
    see tests/test_bankroll.py."""


def build_ramp(
    model: EdgeModel,
    bankroll: float,
    variance: float = 1.3,
    fraction: float = 0.5,
    table_min: float = 10,
    table_max: float = 1000,
    chip: float = 5,
    max_spread: float = 12,
    tc_range: Iterable[int] = range(-5, 11),
) -> Dict[int, RampLevel]:
    """Maps each true count in tc_range to a RampLevel. 1 unit (table_min) at
    or below break-even -- Kelly returns 0 there, and clamp_and_round's own
    floor produces table_min, which is the honest "must bet something anyway"
    cost of playing a game you can't leave, not a special case bolted on here.
    Grows in doubling steps as edge rises, capped at max_spread and table_max.
    """
    ramp: Dict[int, RampLevel] = {}
    for tc in tc_range:
        edge = predict_edge(model, tc)
        unconstrained_fraction = kelly_fraction(edge, variance, fraction)
        raw_bet = unconstrained_fraction * bankroll
        raw_units = raw_bet / table_min

        ramp_units = _snap_to_ramp_level(raw_units, max_spread)
        ramp_bet = clamp_and_round(ramp_units * table_min, table_min, table_max, chip)
        ramp_fraction = ramp_bet / bankroll

        ev_cost = _growth_rate(unconstrained_fraction, edge, variance) - _growth_rate(ramp_fraction, edge, variance)

        ramp[tc] = RampLevel(
            true_count=tc,
            edge=edge,
            raw_kelly_units=raw_units,
            ramp_units=ramp_units,
            ramp_bet=ramp_bet,
            ev_cost=ev_cost,
        )
    return ramp
