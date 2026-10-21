"""Phase 10: Flask API tests, using Flask's own test client (no real server /
port needed). Covers the plan's exact /api/advise worked example, the other
stateless routes, the server-side game session flow (new/deal/action,
including error paths), and /api/simulate's bounding.
"""

import pytest

import app as app_module

DEFAULT_RULES = "6d-s17-das-ls-p75"


@pytest.fixture()
def client():
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


# --- /api/rules -----------------------------------------------------------------------------

def test_api_rules(client):
    resp = client.get("/api/rules")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["rulesets"]) == 32
    assert {s["slug"] for s in data["systems"]} == {
        "hi-lo", "ko", "hi-opt-i", "hi-opt-ii", "omega-ii", "zen", "red-7",
    }
    assert data["defaults"]["ruleset"] == DEFAULT_RULES
    assert data["defaults"]["system"] == "hi-lo"


# --- /api/grid --------------------------------------------------------------------------------

def test_api_grid_matches_advise(client):
    resp = client.get(f"/api/grid?ruleset={DEFAULT_RULES}")
    assert resp.status_code == 200
    cell = resp.get_json()["hard"]["16v10"]
    assert cell["action"] == "Rh"
    assert cell["ev_by_action"]["R"] == pytest.approx(-0.5)


def test_api_grid_unknown_ruleset(client):
    resp = client.get("/api/grid?ruleset=9d-nonsense")
    assert resp.status_code == 400


# --- /api/advise -- the build plan's own exact worked example --------------------------------

def test_api_advise_matches_build_plan_worked_example(client):
    resp = client.post("/api/advise", json={
        "player_cards": ["T", "6"], "dealer_up": "T",
        "running_count": 0, "decks_remaining": 4, "rules": "6d-s17-das-ls",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["action"] == "Rh"
    assert data["ev"]["stand"] == pytest.approx(-0.54, abs=0.01)
    assert data["ev"]["hit"] == pytest.approx(-0.53, abs=0.01)
    assert data["ev"]["surrender"] == pytest.approx(-0.50, abs=0.01)
    assert not data["is_deviation"]


def test_api_advise_flags_a_real_deviation(client):
    # 16 vs 10 stays surrender-optimal (see deviations.py's own docstring on this),
    # so use 12 vs 3 instead -- clean of that confound, same as test_bankroll.py.
    resp = client.post("/api/advise", json={
        "player_cards": ["9", "3"], "dealer_up": "3",
        "running_count": 30, "decks_remaining": 6, "rules": DEFAULT_RULES,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["is_deviation"]
    assert data["deviation_action"] == "stand"
    assert data["ev_gain"] > 0


def test_api_advise_unknown_ruleset(client):
    resp = client.post("/api/advise", json={"player_cards": ["T", "6"], "dealer_up": "T", "rules": "9d-nonsense"})
    assert resp.status_code == 400


# --- /api/count -------------------------------------------------------------------------------

def test_api_count_single_system(client):
    resp = client.post("/api/count", json={"cards": ["2", "3", "4", "5", "6"], "num_decks": 6, "system": "hi-lo"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["running_count"] == 5.0
    assert data["decks_remaining"] == 5.5
    assert data["true_count_betting"] == 0
    assert data["true_count_playing"] == 1


def test_api_count_dual_system_mode(client):
    resp = client.post("/api/count", json={
        "cards": ["2", "3", "4"], "num_decks": 6, "betting_system": "hi-lo", "playing_system": "omega-ii",
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert "betting" in data and "playing" in data
    assert data["betting"]["running_count"] == 3.0    # Hi-Lo: +1 each
    assert data["playing"]["running_count"] == 4.0    # Omega II: 2,3 = +1 each, 4 = +2


# --- /api/stake -------------------------------------------------------------------------------

def test_api_stake_uses_locked_edge_model(client):
    resp = client.post("/api/stake", json={
        "rules": DEFAULT_RULES, "system": "hi-lo", "true_count": 3, "bankroll": 10000,
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["bet"] > 10  # above table_min at a positive count
    assert data["edge"] > 0
    assert 0 <= data["risk_of_ruin"] <= 1


def test_api_stake_no_locked_model_is_a_clean_error(client):
    resp = client.post("/api/stake", json={
        "rules": DEFAULT_RULES, "system": "red-7", "true_count": 3, "bankroll": 10000,
    })
    assert resp.status_code == 400
    assert "run scripts/run_sim_battery.py" in resp.get_json()["error"]


# --- /api/simulate -- bounded, and refuses to trigger a ~9-min index build -------------------

def test_api_simulate_is_bounded(client):
    resp = client.post("/api/simulate", json={
        "rules": DEFAULT_RULES, "system": "hi-lo", "n_hands": 10_000_000, "use_deviations": False,
    })
    assert resp.status_code == 200
    assert resp.get_json()["n_hands"] == app_module.MAX_SIMULATE_HANDS


def test_api_simulate_refuses_uncached_deviations_combo(client):
    # "zen" has no pre-built index cache -- must error instantly, not hang for ~9 minutes.
    resp = client.post("/api/simulate", json={
        "rules": DEFAULT_RULES, "system": "zen", "n_hands": 1000, "use_deviations": True,
    })
    assert resp.status_code == 400
    assert "build_all_indices" in resp.get_json()["error"]


# --- /api/game/* ------------------------------------------------------------------------------

def test_game_session_full_round_flow(client):
    new_resp = client.post("/api/game/new", json={"rules": DEFAULT_RULES, "system": "hi-lo"})
    assert new_resp.status_code == 200
    session_id = new_resp.get_json()["session_id"]

    # A fresh deal can itself resolve instantly as a blackjack -- see
    # test_game_session_deal_can_resolve_instantly_as_blackjack for that path.
    # Retry so THIS test deterministically exercises the "deal, then act" flow.
    for _ in range(50):
        deal_resp = client.post("/api/game/deal", json={"session_id": session_id, "bet": 10})
        assert deal_resp.status_code == 200
        state = deal_resp.get_json()["state"]
        if state["round_active"]:
            break
        session_id = client.post("/api/game/new", json={"rules": DEFAULT_RULES, "system": "hi-lo"}).get_json()["session_id"]
    else:
        pytest.fail("couldn't get an active round in 50 tries")

    assert len(state["hand"]) == 2
    assert "stand" in state["legal_actions"] and "hit" in state["legal_actions"]
    pre_action_decks_remaining = state["decks_remaining"]

    # Stand -- resolves the round in one action from a fresh 2-card hand (no re-hit loop needed).
    action_resp = client.post("/api/game/action", json={"session_id": session_id, "action": "stand"})
    assert action_resp.status_code == 200
    body = action_resp.get_json()
    assert "round_result" in body
    assert body["state"]["round_active"] is False
    # The count only catches up with THIS round's own cards once it resolves (Phase
    # 8's convention -- see _record_round's docstring). decks_remaining, unlike
    # running_count, is GUARANTEED to drop (cards were definitely dealt) regardless
    # of whether this round's specific cards happened to sum to a net-zero tag total.
    assert body["state"]["decks_remaining"] < pre_action_decks_remaining


def test_game_session_deal_can_resolve_instantly_as_blackjack(client):
    """The other branch of api_game_deal: a player/dealer blackjack settles
    immediately, with no round left to act on at all."""
    for _ in range(200):
        session_id = client.post("/api/game/new", json={}).get_json()["session_id"]
        deal_body = client.post("/api/game/deal", json={"session_id": session_id, "bet": 10}).get_json()
        if not deal_body["state"]["round_active"] and "round_result" in deal_body:
            assert "hand" not in deal_body["state"]
            # Acting on it now must fail cleanly, not desync or crash.
            resp = client.post("/api/game/action", json={"session_id": session_id, "action": "hit"})
            assert resp.status_code == 400
            return
    pytest.fail("no instant-blackjack deal in 200 tries -- suspiciously low for ~a few % of hands")


def test_game_session_rejects_illegal_action(client):
    # A fresh deal can itself resolve instantly (player/dealer blackjack, ~ a few
    # percent of hands) -- when it does, there's no round left to act on at all,
    # a DIFFERENT error path than "action illegal for this hand". Retry until we
    # land on an active, non-pair round so this test exercises the right one
    # deterministically rather than being flaky depending on the random deal.
    session_id = None
    for _ in range(50):
        session_id = client.post("/api/game/new", json={}).get_json()["session_id"]
        deal_body = client.post("/api/game/deal", json={"session_id": session_id, "bet": 10}).get_json()
        state = deal_body["state"]
        if state["round_active"] and "split" not in state["legal_actions"]:
            break
    else:
        pytest.fail("couldn't get an active non-pair round in 50 tries")

    resp = client.post("/api/game/action", json={"session_id": session_id, "action": "split"})
    assert resp.status_code == 400
    assert "legal_actions" in resp.get_json()


def test_game_session_no_round_in_progress(client):
    new_resp = client.post("/api/game/new", json={})
    session_id = new_resp.get_json()["session_id"]
    resp = client.post("/api/game/action", json={"session_id": session_id, "action": "hit"})
    assert resp.status_code == 400


def test_game_session_unknown_session_id(client):
    resp = client.post("/api/game/deal", json={"session_id": "does-not-exist", "bet": 10})
    assert resp.status_code == 404


def test_game_session_cannot_deal_twice(client):
    # Only true while a round is genuinely in progress -- an instant-blackjack first
    # deal already concluded, so a second deal is legitimately allowed then. Retry
    # for an active round so this deterministically tests the right scenario.
    for _ in range(50):
        session_id = client.post("/api/game/new", json={}).get_json()["session_id"]
        first = client.post("/api/game/deal", json={"session_id": session_id, "bet": 10})
        if first.get_json()["state"]["round_active"]:
            break
    else:
        pytest.fail("couldn't get an active round in 50 tries")

    resp = client.post("/api/game/deal", json={"session_id": session_id, "bet": 10})
    assert resp.status_code == 400


def test_game_sessions_are_isolated():
    """Two sessions' shoes/counters must never interfere with each other --
    the whole point of keying state server-side by session id."""
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        s1 = client.post("/api/game/new", json={}).get_json()["session_id"]
        s2 = client.post("/api/game/new", json={}).get_json()["session_id"]
        assert s1 != s2

        client.post("/api/game/deal", json={"session_id": s1, "bet": 10})
        # s2 has no round dealt yet -- acting on it must fail regardless of s1's state.
        resp = client.post("/api/game/action", json={"session_id": s2, "action": "hit"})
        assert resp.status_code == 400
