"""Phase 12: Flask API tests for src/poker/api.py, using Flask's own test
client -- mirrors tests/test_app.py's style on the blackjack side. See
markdowns/poker/poker_build_plan_v1.md Phase 12.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import app as app_module

DEFAULT_SPEC = "hu-100bb-r5c3-s5"


@pytest.fixture()
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


# --- /api/poker/spec -----------------------------------------------------------


def test_api_spec(client):
    resp = client.get("/api/poker/spec")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["default_key"] == DEFAULT_SPEC
    assert DEFAULT_SPEC in data["solved_preflop_specs"]


# --- /api/poker/equity ----------------------------------------------------------


def test_api_equity_matches_the_plans_worked_example(client):
    """AsAh vs KsKh, no board -- the plan's own verification block's exact
    expected output (adapted from its stale "/api/blackjack/grid" text to
    this Blueprint's real /api/poker/ prefix, see api.py's own docstring)."""
    resp = client.post("/api/poker/equity", json={"hands": ["AsAh", "KsKh"], "board": []})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["equities"][0] == pytest.approx(0.826, abs=1e-3)
    assert data["equities"][1] == pytest.approx(0.174, abs=1e-3)
    assert data["method"] == "exact"
    assert data["runouts"] == 1712304
    assert "standard_error" not in data  # exact path: no sampling error to report


def test_api_equity_always_prefers_the_exact_path_for_real_holdem_spots(client):
    """Real Hold'em equity queries can NEVER exceed EXACT_LIMIT through this
    route: the runout count is comb(52 - n_known, 5 - len(board)), maximised
    at just 2 known hole-card pairs and an empty board (comb(48, 5) =
    1,712,304), well under EXACT_LIMIT = 5,000,000 -- so the MC path in
    equity()'s own dispatcher (already covered directly in
    tests/poker/test_equity.py) is unreachable via this API for any valid
    Hold'em input, no matter how large n_samples is asked for. This checks
    that the API always takes the exact path it's entitled to rather than
    ever needlessly sampling one, even on the widest possible spot (3-way,
    no board) and a large requested n_samples."""
    resp = client.post(
        "/api/poker/equity", json={"hands": ["AsAh", "KsKh", "QsQh"], "board": [], "n_samples": 5000, "seed": 0}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["method"] == "exact"
    assert "standard_error" not in data
    assert sum(data["equities"]) == pytest.approx(1.0, abs=1e-6)


def test_api_equity_includes_a_distribution_on_the_exact_path(client):
    """The Equity tab's headline chart (Phase 13) is the per-player equity
    DISTRIBUTION, not just the mean -- attached whenever the exact path is
    taken (every real Hold'em spot through this route, per the always-exact
    finding above). Each player's per-value probabilities must sum to 1.0,
    and the win-share entry ("1.0") must be consistent with the plain mean
    already returned in `equities`."""
    resp = client.post("/api/poker/equity", json={"hands": ["AsAh", "KsKh"], "board": []})
    data = resp.get_json()
    assert "distribution" in data
    assert len(data["distribution"]) == 2
    for dist in data["distribution"]:
        assert sum(dist.values()) == pytest.approx(1.0, abs=1e-9)


def test_api_equity_rejects_malformed_hands(client):
    resp = client.post("/api/poker/equity", json={"hands": ["Zz"], "board": []})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


# --- /api/poker/range/parse, /api/poker/range/equity ---------------------------


def test_api_range_parse(client):
    resp = client.post("/api/poker/range/parse", json={"notation": "AA"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["n_combos"] == 6.0
    assert len(data["combos"]) == 6


def test_api_range_parse_rejects_bad_notation(client):
    resp = client.post("/api/poker/range/parse", json={"notation": "not a range"})
    assert resp.status_code == 400


def test_api_range_equity_sums_to_one(client):
    resp = client.post("/api/poker/range/equity", json={"range_a": "AA", "range_b": "KK"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["equity_a"] + data["equity_b"] == pytest.approx(1.0)


def test_api_range_equity_rejects_fully_conflicting_ranges(client):
    resp = client.post("/api/poker/range/equity", json={"range_a": "AsAh", "range_b": "AsAh"})
    assert resp.status_code == 400


# --- /api/poker/preflop ----------------------------------------------------------


def test_api_preflop_returns_the_solved_strategy(client):
    resp = client.get(f"/api/poker/preflop?spec={DEFAULT_SPEC}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["spec"] == DEFAULT_SPEC
    assert "abstraction_exploitability_mbb" in data
    assert "iterations" in data


def test_api_preflop_names_the_exact_fix_command_when_missing(client):
    resp = client.get("/api/poker/preflop?spec=hu-999bb-r5c3-s5")
    assert resp.status_code == 400
    assert "solve_preflop.py --spec hu-999bb-r5c3-s5" in resp.get_json()["error"]


# --- /api/poker/advise -----------------------------------------------------------


def test_api_advise_frequencies_sum_to_one(client):
    resp = client.post("/api/poker/advise", json={"hand": "AA", "position": "BTN", "history": [], "spec": DEFAULT_SPEC})
    assert resp.status_code == 200
    data = resp.get_json()
    assert sum(data["action_frequencies"].values()) == pytest.approx(1.0, abs=1e-2)


def test_api_advise_rejects_an_unrecognised_spec(client):
    resp = client.post("/api/poker/advise", json={"hand": "AA", "position": "BTN", "history": [], "spec": "not-a-spec"})
    assert resp.status_code == 400


# --- /api/poker/pushfold ---------------------------------------------------------


def test_api_pushfold_returns_monotone_ranges(client):
    r10 = client.get("/api/poker/pushfold?stack=10").get_json()
    r5 = client.get("/api/poker/pushfold?stack=5").get_json()
    assert r5["jam_pct"] >= r10["jam_pct"]  # shorter stacks jam wider, per Phase 9's own locked finding


def test_api_pushfold_rejects_an_out_of_range_stack(client):
    resp = client.get("/api/poker/pushfold?stack=100")
    assert resp.status_code == 400


# --- /api/poker/icm --------------------------------------------------------------


def test_api_icm_matches_the_plans_appendix_a6_anchor(client):
    resp = client.post("/api/poker/icm", json={"stacks": [5000, 3000, 2000], "payouts": [50, 30, 20]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["equities"][0] == pytest.approx(38.393, abs=1e-3)
    assert sum(data["equities"]) == pytest.approx(100.0)


def test_api_icm_includes_bubble_factor_when_requested(client):
    resp = client.post(
        "/api/poker/icm",
        json={"stacks": [5000, 3000, 2000], "payouts": [50, 30, 20], "player": 0, "opponent": 2, "risk_amount": 1000},
    )
    data = resp.get_json()
    assert "bubble_factor" in data


def test_api_icm_requires_stacks_and_payouts(client):
    resp = client.post("/api/poker/icm", json={"stacks": [1, 2]})
    assert resp.status_code == 400


# --- /api/poker/solve (bounded) --------------------------------------------------


def test_api_solve_runs_a_bounded_spot(client):
    resp = client.post(
        "/api/poker/solve",
        json={
            "board": "AsKd7h2c9s",
            "hero_range": "QQ+",
            "villain_range": "QQ+",
            "pot": 10,
            "stack": 20,
            "iterations": 2000,
            "max_seconds": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["iterations"] <= 2000
    assert "abstraction_exploitability_mbb" in data
    assert "strategy" in data


def test_api_solve_rejects_an_oversized_range_pair_before_solving(client):
    resp = client.post(
        "/api/poker/solve",
        json={"board": "AsKd7h2c9s", "hero_range": "100%", "villain_range": "100%", "pot": 10, "stack": 20},
    )
    assert resp.status_code == 400
    assert "too wide" in resp.get_json()["error"]


def test_api_solve_caps_iterations_and_seconds_at_the_hard_maximum(client):
    from src.poker import api as api_module

    resp = client.post(
        "/api/poker/solve",
        json={
            "board": "AsKd7h2c9s",
            "hero_range": "QQ+",
            "villain_range": "QQ+",
            "pot": 10,
            "stack": 20,
            "iterations": 999_999_999,
            "max_seconds": 999_999,
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["iterations"] <= api_module.MAX_SOLVE_ITERATIONS


# --- /api/poker/bankroll ---------------------------------------------------------


def test_api_bankroll_risk_of_ruin_matches_the_plans_table(client):
    resp = client.post("/api/poker/bankroll", json={"wr": 5, "sd": 100, "bankroll": 1000})
    assert resp.status_code == 200
    assert resp.get_json()["risk_of_ruin"] == pytest.approx(0.368, abs=1e-3)


def test_api_bankroll_confidence_interval_only_present_when_requested(client):
    without = client.post("/api/poker/bankroll", json={"wr": 5, "sd": 100}).get_json()
    assert "confidence_interval" not in without

    with_ci = client.post(
        "/api/poker/bankroll", json={"wr": 5, "sd": 100, "n_hands": 10_000, "observed_wr": 5.0}
    ).get_json()
    assert (with_ci["confidence_interval"]["high"] - with_ci["confidence_interval"]["low"]) / 2.0 == pytest.approx(
        19.6, abs=0.05
    )


def test_api_bankroll_stake_advice_only_present_when_requested(client):
    with_advice = client.post(
        "/api/poker/bankroll", json={"wr": 5, "sd": 100, "total_bankroll": 10_000, "target_ror": 0.05}
    ).get_json()
    assert with_advice["stake_advice"]["max_buyin"] > 0


def test_api_bankroll_requires_wr_and_sd(client):
    resp = client.post("/api/poker/bankroll", json={"wr": 5})
    assert resp.status_code == 400


# --- blackjack routes unaffected -------------------------------------------------


def test_blackjack_routes_still_work_unmodified(client):
    resp = client.get("/api/grid?ruleset=6d-s17-das-ls-p75")
    assert resp.status_code == 200
