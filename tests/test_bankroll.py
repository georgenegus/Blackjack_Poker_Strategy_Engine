"""Phase 9: Kelly bet sizing, the memorisable bet ramp, and the risk-profile
bundle (risk of ruin, N0, hours to double, drawdown percentiles).
"""

import math

import numpy as np
import pytest

from src.bankroll.bet_ramp import build_ramp
from src.bankroll.kelly import clamp_and_round, kelly_bet, kelly_fraction
from src.bankroll.risk import hours_to_double, n_zero, risk_of_ruin, risk_profile, simulate_drawdowns
from src.counting.edge_model import EdgeModel


def _synthetic_model(intercept=-0.005, slope=0.005) -> EdgeModel:
    return EdgeModel(
        ruleset_key="test", system_name="Hi-Lo", use_deviations=True, n_hands=1,
        intercept=intercept, slope=slope, r_squared=1.0, fit_tc_range=(-5, 10), buckets=[],
    )


# --- kelly.py -- exact worked examples from the build plan --------------------------------

def test_kelly_bet_matches_build_plan_worked_example():
    assert kelly_bet(10000, 0.01, 1.3, 0.5, 10, 1000, 5) == pytest.approx(40)


def test_kelly_fraction_floors_at_zero_for_non_positive_edge():
    assert kelly_fraction(0.0, 1.3, 0.5) == 0.0
    assert kelly_fraction(-0.01, 1.3, 0.5) == 0.0


def test_kelly_fraction_formula():
    assert kelly_fraction(0.01, 1.3, 0.5) == pytest.approx(0.5 * 0.01 / 1.3)


def test_clamp_and_round_chip_and_table_limits():
    assert clamp_and_round(38.46, table_min=10, table_max=1000, chip=5) == 40  # rounds to nearest chip
    assert clamp_and_round(2.0, table_min=10, table_max=1000, chip=5) == 10    # floors at table_min
    assert clamp_and_round(5000.0, table_min=10, table_max=1000, chip=5) == 1000  # caps at table_max


# --- risk.py -- exact worked example, plus formula/sanity checks --------------------------

def test_risk_of_ruin_matches_build_plan_worked_example():
    assert risk_of_ruin(bankroll_units=200, edge=0.01, variance=1.3) == pytest.approx(0.0461, abs=0.0001)


def test_risk_of_ruin_is_certain_at_non_positive_edge():
    assert risk_of_ruin(200, 0.0, 1.3) == 1.0
    assert risk_of_ruin(200, -0.01, 1.3) == 1.0


def test_hours_to_double():
    # edge=0.01 units/hand, 60 hands/hour -> 0.6 units/hour; need 200 units -> 333.33 hours
    assert hours_to_double(200, 0.01, hands_per_hour=60) == pytest.approx(200 / 0.01 / 60)
    assert hours_to_double(200, 0.0) == float("inf")
    assert hours_to_double(200, -0.01) == float("inf")


def test_simulate_drawdowns_percentiles_ordered_and_bounded():
    result = simulate_drawdowns(
        bankroll_units=200, edge=0.01, variance=1.3, n_hands=2000, n_trials=2000,
        rng=np.random.default_rng(1),
    )
    assert 0.0 <= result["p50"] <= result["p90"] <= result["p99"] <= 1.0 + 1e-9


def test_simulate_drawdowns_worse_for_negative_edge():
    rng_pos = np.random.default_rng(2)
    rng_neg = np.random.default_rng(2)
    positive = simulate_drawdowns(200, 0.01, 1.3, n_hands=2000, n_trials=2000, rng=rng_pos)
    negative = simulate_drawdowns(200, -0.01, 1.3, n_hands=2000, n_trials=2000, rng=rng_neg)
    assert negative["p50"] >= positive["p50"]
    assert negative["p90"] >= positive["p90"]


def test_risk_profile_bundles_the_component_functions():
    profile = risk_profile(
        bankroll_units=200, edge=0.01, variance=1.3, n_hands=1000, hands_per_hour=60,
        n_trials=500, rng=np.random.default_rng(3),
    )
    assert profile.risk_of_ruin == pytest.approx(risk_of_ruin(200, 0.01, 1.3))
    assert profile.n_zero == pytest.approx(n_zero(0.01, 1.3))
    assert profile.hours_to_double == pytest.approx(hours_to_double(200, 0.01, 60))
    assert 0.0 <= profile.drawdown_p50 <= profile.drawdown_p90 <= profile.drawdown_p99


# --- bet_ramp.py ----------------------------------------------------------------------------

def test_build_ramp_floors_at_table_min_below_breakeven():
    model = _synthetic_model(intercept=-0.005, slope=0.005)  # break-even at TC=+1
    ramp = build_ramp(model, bankroll=10_000, tc_range=range(-5, 1))
    for tc, level in ramp.items():
        assert level.ramp_units == 1
        assert level.ramp_bet == 10  # default table_min


def test_build_ramp_grows_monotonically_and_respects_max_spread():
    model = _synthetic_model(intercept=-0.005, slope=0.005)
    ramp = build_ramp(model, bankroll=10_000, max_spread=12, tc_range=range(-2, 11))
    units = [ramp[tc].ramp_units for tc in sorted(ramp)]
    assert units == sorted(units)  # never decreases as TC rises
    assert max(units) <= 12
    assert units[0] == 1


def test_build_ramp_ev_cost_is_non_negative_when_kelly_already_wants_a_full_unit():
    # Only true once raw_kelly_units >= 1: snapping DOWN from a value already at or
    # above the smallest ramp level can only move fraction-of-bankroll closer to zero,
    # and g(f) = f*edge - 0.5*f^2*variance is strictly increasing below the full-Kelly
    # peak (half-Kelly's own fraction is always below that peak) -- so losing ground
    # there is guaranteed, not just typical.
    model = _synthetic_model(intercept=-0.005, slope=0.005)
    ramp = build_ramp(model, bankroll=10_000, tc_range=range(-5, 11))
    for level in ramp.values():
        if level.raw_kelly_units >= 1:
            assert level.ev_cost >= -1e-12


def test_build_ramp_floor_can_slightly_beat_unconstrained_half_kelly():
    # The one case ev_cost can go slightly NEGATIVE (a tiny gain, not a cost): when raw
    # Kelly wants LESS than 1 unit (edge is small but positive) yet the mandatory floor
    # forces a full unit anyway. That floor bet's fraction-of-bankroll can land CLOSER
    # to the true full-Kelly peak than half-Kelly's own target does, since forcing the
    # bet moves you UP the growth curve rather than down -- found empirically by running
    # build_ramp against the real locked Phase 8 baseline (TC=+1 there), not something to
    # paper over with a false "always non-negative" guarantee.
    model = _synthetic_model(intercept=-0.3257 / 100, slope=0.4793 / 100)  # the actual locked baseline
    ramp = build_ramp(model, bankroll=10_000, tc_range=range(0, 2))
    below_one_unit = [lvl for lvl in ramp.values() if 0 < lvl.raw_kelly_units < 1]
    assert below_one_unit  # confirms this scenario is actually exercised, not vacuously true
    assert any(lvl.ev_cost < 0 for lvl in below_one_unit)
