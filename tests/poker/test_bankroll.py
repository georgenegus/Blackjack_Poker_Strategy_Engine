"""Phase 11: bankroll, variance, and risk of ruin. See
markdowns/poker/poker_build_plan_v1.md Phase 11, whose own risk-of-ruin and
win-rate-standard-error tables are reproduced here as regression anchors.
"""

import math

import pytest

from src.poker.bankroll import (
    StakeRecommendation,
    probability_of_downswing,
    recommend_max_buyin,
    required_bankroll_bb,
    risk_of_ruin,
    win_rate_confidence_interval,
    win_rate_standard_error,
)


# --- risk_of_ruin: the plan's own table, reproduced exactly ------------------


@pytest.mark.parametrize(
    "bankroll_bb,win_rate,expected_pct",
    [
        (1000, 5, 36.8),
        (2000, 5, 13.5),
        (5000, 5, 0.67),
        (1000, 2, 67.0),
        (2000, 2, 44.9),
        (5000, 2, 13.5),
    ],
)
def test_risk_of_ruin_matches_the_plans_table(bankroll_bb, win_rate, expected_pct):
    ror = risk_of_ruin(bankroll_bb, win_rate, stdev_bb100=100)
    assert ror * 100.0 == pytest.approx(expected_pct, abs=0.05)


def test_risk_of_ruin_decreases_with_bankroll():
    values = [risk_of_ruin(b, 5, 100) for b in (500, 1000, 2000, 5000, 10000)]
    assert values == sorted(values, reverse=True)


def test_risk_of_ruin_decreases_with_win_rate():
    values = [risk_of_ruin(2000, w, 100) for w in (1, 2, 5, 10)]
    assert values == sorted(values, reverse=True)


def test_risk_of_ruin_is_certain_for_a_non_positive_win_rate():
    assert risk_of_ruin(5000, 0.0, 100) == 1.0
    assert risk_of_ruin(5000, -3.0, 100) == 1.0


def test_risk_of_ruin_is_certain_for_a_nonpositive_bankroll():
    assert risk_of_ruin(0.0, 5.0, 100) == 1.0
    assert risk_of_ruin(-100.0, 5.0, 100) == 1.0


def test_risk_of_ruin_bounded_in_zero_one():
    for b in (1, 100, 1000, 100000):
        for w in (0.5, 5, 20):
            assert 0.0 < risk_of_ruin(b, w, 100) <= 1.0


# --- probability_of_downswing: same closed form, different name ------------


def test_probability_of_downswing_matches_risk_of_ruin_directly():
    """Mathematically the same first-passage problem -- a depth-D downswing
    below a running peak is the identical random walk as losing a D-sized
    bankroll outright, per this module's own docstring."""
    assert probability_of_downswing(2000, 5, 100) == risk_of_ruin(2000, 5, 100)


# --- required_bankroll_bb: closed-form inverse of risk_of_ruin -------------


def test_required_bankroll_bb_round_trips_through_risk_of_ruin():
    for w, s, target in [(5, 100, 0.05), (2, 120, 0.10), (10, 80, 0.01)]:
        b = required_bankroll_bb(w, s, target)
        assert risk_of_ruin(b, w, s) == pytest.approx(target, rel=1e-9)


def test_required_bankroll_bb_matches_the_plans_1000bb_anchor():
    """The plan's table says 1000bb gives 36.8% RoR at w=5/s=100 -- the
    inverse must recover ~1000bb when asked for a 36.8% target."""
    b = required_bankroll_bb(5, 100, 0.368)
    assert b == pytest.approx(1000.0, abs=2.0)


def test_required_bankroll_bb_rejects_invalid_targets():
    with pytest.raises(ValueError):
        required_bankroll_bb(5, 100, 0.0)
    with pytest.raises(ValueError):
        required_bankroll_bb(5, 100, 1.0)
    with pytest.raises(ValueError):
        required_bankroll_bb(5, 100, 1.5)


def test_required_bankroll_bb_rejects_a_non_positive_win_rate():
    with pytest.raises(ValueError):
        required_bankroll_bb(0.0, 100, 0.05)
    with pytest.raises(ValueError):
        required_bankroll_bb(-1.0, 100, 0.05)


# --- win_rate_standard_error / confidence interval: the plan's own table ----


@pytest.mark.parametrize(
    "n_hands,expected_se",
    [
        (10_000, 10.0),
        (100_000, 3.16),
        (1_000_000, 1.00),
    ],
)
def test_win_rate_standard_error_matches_the_plans_table(n_hands, expected_se):
    se = win_rate_standard_error(stdev_bb100=100, n_hands=n_hands)
    assert se == pytest.approx(expected_se, abs=0.01)


@pytest.mark.parametrize(
    "n_hands,expected_half_width",
    [
        (10_000, 19.6),
        (100_000, 6.2),
        (1_000_000, 2.0),
    ],
)
def test_win_rate_confidence_interval_matches_the_plans_table(n_hands, expected_half_width):
    lo, hi = win_rate_confidence_interval(observed_bb100=5.0, stdev_bb100=100, n_hands=n_hands)
    assert (hi - lo) / 2.0 == pytest.approx(expected_half_width, abs=0.05)
    assert (lo + hi) / 2.0 == pytest.approx(5.0)  # centered on the observed rate


def test_win_rate_standard_error_shrinks_with_more_hands():
    values = [win_rate_standard_error(100, n) for n in (1_000, 10_000, 100_000, 1_000_000)]
    assert values == sorted(values, reverse=True)


def test_win_rate_standard_error_rejects_nonpositive_hands():
    with pytest.raises(ValueError):
        win_rate_standard_error(100, 0)
    with pytest.raises(ValueError):
        win_rate_standard_error(100, -5)


# --- recommend_max_buyin ------------------------------------------------------


def test_recommend_max_buyin_achieves_exactly_the_safety_adjusted_target():
    rec = recommend_max_buyin(total_bankroll=10_000.0, win_rate_bb100=5, stdev_bb100=100, target_ror=0.05)
    assert isinstance(rec, StakeRecommendation)
    assert rec.effective_target_ror == pytest.approx(0.025)  # default safety_factor=0.5

    implied_bankroll_bb = rec.total_bankroll / (rec.max_buyin / 100.0)
    assert implied_bankroll_bb == pytest.approx(rec.required_bankroll_bb, rel=1e-9)
    assert risk_of_ruin(implied_bankroll_bb, 5, 100) == pytest.approx(rec.effective_target_ror, rel=1e-9)


def test_recommend_max_buyin_grows_with_total_bankroll():
    small = recommend_max_buyin(5_000.0, 5, 100, 0.05)
    large = recommend_max_buyin(50_000.0, 5, 100, 0.05)
    assert large.max_buyin > small.max_buyin
    # both still hold the SAME safety-adjusted risk target -- only the buy-in size differs
    assert small.effective_target_ror == pytest.approx(large.effective_target_ror)


def test_recommend_max_buyin_defaults_to_half_the_stated_risk_tolerance():
    rec = recommend_max_buyin(10_000.0, 5, 100, target_ror=0.10)
    assert rec.effective_target_ror == pytest.approx(0.05)
    # a LOOSER (higher) target_ror allows a smaller required bankroll_bb, i.e. a LARGER buy-in
    looser = recommend_max_buyin(10_000.0, 5, 100, target_ror=0.10, safety_factor=1.0)
    assert looser.max_buyin > rec.max_buyin


def test_recommend_max_buyin_rejects_nonpositive_total_bankroll():
    with pytest.raises(ValueError):
        recommend_max_buyin(0.0, 5, 100, 0.05)
