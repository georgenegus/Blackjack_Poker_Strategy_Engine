"""Phase 8: BucketStats/metrics/edge_model unit tests (fast, exact, no
simulation needed for the regression math itself), plus a moderate-N
run_battery integration check against Phase 5's exact solver. The full
20M-hand verification battery (matching the solver within its stated SE,
variance in 1.25-1.35, slope in 0.004-0.006, R^2>0.98) is deliberately NOT run
here -- see scripts/run_sim_battery.py, run as its own long background job.
"""

import math

import numpy as np
import pytest

from src.counting.systems import HI_LO
from src.counting.edge_model import BucketFit, EdgeModel, fit_edge_model, is_extrapolating, load_baseline, save_baseline
from src.engine.rules import RuleSet
from src.simulation import metrics
from src.simulation.simulator import BatteryResult, BucketStats, run_battery
from src.strategy.exact_edge import exact_house_edge


# --- BucketStats --------------------------------------------------------------------------

def test_bucket_stats_mean_variance_stderr():
    b = BucketStats()
    for r in (1.0, -1.0, 1.0, -1.0, 0.0):
        b.add(r)
    assert b.n == 5
    assert b.mean == pytest.approx(0.0)
    assert b.variance == pytest.approx(float(np.var([1.0, -1.0, 1.0, -1.0, 0.0])))
    assert b.stderr == pytest.approx(math.sqrt(b.variance / 5))


def test_bucket_stats_empty_is_nan_not_a_crash():
    b = BucketStats()
    assert math.isnan(b.mean)
    assert math.isnan(b.stderr)


# --- metrics.py ----------------------------------------------------------------------------

def test_n_zero():
    assert metrics.n_zero(0.01, 1.3) == pytest.approx(1.3 / 0.0001)
    assert metrics.n_zero(-0.01, 1.3) == float("inf")
    assert metrics.n_zero(0.0, 1.3) == float("inf")


def test_risk_of_ruin():
    assert metrics.risk_of_ruin(200, 0.01, 1.3) == pytest.approx(math.exp(-2 * 200 * 0.01 / 1.3))
    assert metrics.risk_of_ruin(200, -0.01, 1.3) == 1.0
    assert metrics.risk_of_ruin(200, 0.0, 1.3) == 1.0


def test_desirability_index_and_score_relationship():
    di = metrics.desirability_index(0.01, 1.3)
    assert di == pytest.approx(1000 * 0.01 / math.sqrt(1.3))
    assert metrics.score(0.01, 1.3) == pytest.approx(di**2)


def test_win_rate_per_100():
    assert metrics.win_rate_per_100(0.01) == pytest.approx(1.0)  # 1% edge, 1-unit bet -> 1 unit/100 hands


# --- edge_model.py: exact regression math, no simulation noise involved -------------------

def _bucket_with_mean(n: int, mean: float) -> BucketStats:
    b = BucketStats()
    b.n = n
    b.sum_result = mean * n
    b.sum_result_sq = 0.0  # fit_edge_model only reads .n and .mean
    return b


def _fake_result(by_tc: dict) -> BatteryResult:
    return BatteryResult(
        ruleset_key="6d-s17-das-ls-p75", system_name="Hi-Lo", n_hands=sum(b.n for b in by_tc.values()),
        use_deviations=True, other_players=0, overall=BucketStats(), by_true_count=by_tc,
    )


def test_fit_edge_model_recovers_exact_linear_relationship():
    true_intercept, true_slope = -0.005, 0.005
    by_tc = {tc: _bucket_with_mean(10_000, true_intercept + true_slope * tc) for tc in range(-5, 6)}
    model = fit_edge_model(_fake_result(by_tc))
    assert model.intercept == pytest.approx(true_intercept, abs=1e-9)
    assert model.slope == pytest.approx(true_slope, abs=1e-9)
    assert model.r_squared == pytest.approx(1.0, abs=1e-9)
    assert model.fit_tc_range == (-5, 5)


def test_fit_edge_model_excludes_thin_buckets_from_fit_but_reports_them():
    true_intercept, true_slope = -0.005, 0.005
    by_tc = {tc: _bucket_with_mean(10_000, true_intercept + true_slope * tc) for tc in range(-5, 6)}
    by_tc[9] = _bucket_with_mean(3, 5.0)  # wildly-off outlier, but far too few hands to trust
    model = fit_edge_model(_fake_result(by_tc), min_bucket_n=200)
    assert model.intercept == pytest.approx(true_intercept, abs=1e-9)
    assert model.slope == pytest.approx(true_slope, abs=1e-9)
    assert any(b.tc == 9 for b in model.buckets)  # reported for transparency
    assert model.fit_tc_range == (-5, 5)  # but not used in the fit itself


def test_edge_model_baseline_round_trips(tmp_path):
    by_tc = {tc: _bucket_with_mean(10_000, -0.005 + 0.005 * tc) for tc in range(-5, 6)}
    model = fit_edge_model(_fake_result(by_tc))
    path = tmp_path / "edge_model_baseline.json"

    save_baseline(model, path=path)
    loaded = load_baseline(path=path)

    assert loaded == model


def test_is_extrapolating():
    assert not is_extrapolating(0)
    assert not is_extrapolating(6)
    assert not is_extrapolating(-3)
    assert is_extrapolating(7)
    assert is_extrapolating(-4)


# --- run_battery: moderate-N integration check against the exact solver -------------------

def test_run_battery_basic_strategy_matches_exact_house_edge():
    rules = RuleSet(num_decks=6, surrender="none")
    exact = exact_house_edge(rules)  # ~0.4002% -- see Phase 5's findings
    result = run_battery(rules, HI_LO, n_hands=1_000_000, use_deviations=False, rng=np.random.default_rng(42))
    assert abs(result.overall.mean - (-exact)) <= 4 * result.overall.stderr


def test_run_battery_with_deviations_and_other_players_smoke():
    """Not a precision check (see the module docstring) -- just confirms the
    counting/deviation/other-players machinery runs end to end and produces a
    structurally sane result."""
    rules = RuleSet(num_decks=6, surrender="late")
    result = run_battery(
        rules, HI_LO, n_hands=20_000, use_deviations=True, other_players=2, rng=np.random.default_rng(7)
    )
    assert result.n_hands == 20_000
    assert result.overall.n == 20_000
    assert len(result.by_true_count) > 1
    assert result.n_doubled > 0
    assert result.n_split_rounds > 0
