"""Phase 10: Flask API -- thin, stateless translation over src/, except for
game sessions (held server-side, keyed by session id -- see the build plan's
Phase 10 [!IMPORTANT], never round-tripped through the browser).

    py app.py    # serves on http://127.0.0.1:5000

Registries below mirror T20's MODELS = {} startup pattern: every shipped
grid is solved (from disk cache, ~instant when warm) once at import time.
Indices and edge models are NOT all eagerly loaded the same way -- deriving a
fresh index table takes ~9 minutes (see index_builder.py) and only one
ruleset+system combo has ever been simulated for an edge model -- so those are
loaded lazily/best-effort instead of assumed complete for all 32 rulesets.
"""

import math
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from flask import Flask, jsonify, request, send_from_directory

from src.bankroll.kelly import kelly_bet
from src.bankroll.risk import n_zero, risk_of_ruin
from src.counting.counter import Counter
from src.counting.edge_model import BASELINE_DIR, EdgeModel, is_extrapolating, load_baseline, predict_edge
from src.counting.systems import ALL_SYSTEMS, CountingSystem, HI_LO, system_for_slug
from src.engine.cards import Card
from src.engine.game import (
    Action,
    RoundResult,
    deal_initial,
    play_hands_interactive,
    settle_round,
)
from src.engine.hand import Hand
from src.engine.rules import RuleSet, shipped_rulesets
from src.engine.shoe import Shoe
from src.simulation.simulator import run_battery
from src.strategy import basic_strategy, deviations
from src.strategy.grid_builder import solve_grid_cached
from src.strategy.index_builder import DEFAULT_INDEX_CACHE_DIR
from src.poker.api import poker_bp

app = Flask(__name__, static_folder="static", static_url_path="")
app.register_blueprint(poker_bp)


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/poker")
def poker_index():
    # Phase 13: poker gets its own entry point rather than a sixth tab in
    # the blackjack SPA (see markdowns/poker/poker_build_plan_v1.md Phase
    # 13's own Implementation section) -- neither app's tab bar becomes a
    # mess, and neither JS bundle grows a dependency on the other's files.
    return send_from_directory(app.static_folder, "poker.html")

# --- Startup registries -------------------------------------------------------------------

SHIPPED_RULES: Dict[str, RuleSet] = {r.key(): r for r in shipped_rulesets()}
DEFAULT_RULESET_KEY = RuleSet(num_decks=6, surrender="late").key()  # 6d-s17-das-ls-p75
GRIDS = {key: solve_grid_cached(rules) for key, rules in SHIPPED_RULES.items()}

_ACTION_WORD = {"S": "stand", "H": "hit", "D": "double", "R": "surrender", "P": "split"}
_CODE_DESCRIPTIONS = {
    "H": "Hit", "S": "Stand",
    "D": "Double if allowed, otherwise Hit",
    "Ds": "Double if allowed, otherwise Stand",
    "P": "Split",
    "Ph": "Split if DAS, otherwise Hit",
    "Rh": "Surrender if allowed, otherwise Hit",
    "Rs": "Surrender if allowed, otherwise Stand",
    "Rp": "Surrender if allowed, otherwise Split",
}


def _resolve_ruleset(key: str) -> Optional[RuleSet]:
    """Exact match first; falls back to appending the default penetration
    suffix ("6d-s17-das-ls" -> "6d-s17-das-ls-p75") since every shipped
    ruleset currently uses the same 75% penetration and callers may
    reasonably omit it."""
    if key in SHIPPED_RULES:
        return SHIPPED_RULES[key]
    return SHIPPED_RULES.get(f"{key}-p75")


def _resolve_system(slug: str):
    try:
        return system_for_slug(slug), None
    except ValueError as e:
        return None, str(e)


def _counter_for(rules: RuleSet, system: CountingSystem, running_count: float, decks_remaining: float) -> Counter:
    """A throwaway Counter reflecting caller-supplied running_count/
    decks_remaining directly -- for /api/advise's stateless "what if" queries,
    NOT the live per-session counter (see GameSession for that). `dealt` is
    back-derived so Counter.decks_remaining reproduces the given value exactly
    for any half-deck-resolution input."""
    counter = Counter(system, rules.num_decks)
    counter.dealt = int(round((rules.num_decks - decks_remaining) * 52))
    counter.running_count = running_count
    return counter


def _load_edge_model(ruleset_key: str, system_slug: str) -> Optional[EdgeModel]:
    """Best-effort: only whatever's actually been generated via
    scripts/run_sim_battery.py --generate exists on disk (see edge_model.py's
    keyed_baseline_path) -- there is no registry of all 32 assumed complete."""
    path = BASELINE_DIR / f"edge_model__{ruleset_key}__{system_slug}.json"
    if not path.exists():
        return None
    return load_baseline(path=path)


# --- /api/rules -----------------------------------------------------------------------------

@app.route("/api/rules", methods=["GET"])
def api_rules():
    return jsonify({
        "rulesets": [
            {
                "key": key,
                "num_decks": r.num_decks,
                "dealer_hits_soft_17": r.dealer_hits_soft_17,
                "double_after_split": r.double_after_split,
                "surrender": r.surrender,
                "penetration": r.penetration,
            }
            for key, r in SHIPPED_RULES.items()
        ],
        "deck_options": [2, 4, 6, 8],
        "systems": [
            {
                "slug": s.slug, "name": s.name, "level": s.level, "balanced": s.balanced,
                "betting_correlation": s.betting_correlation, "playing_efficiency": s.playing_efficiency,
                "needs_ace_side_count": s.needs_ace_side_count,
            }
            for s in ALL_SYSTEMS
        ],
        "defaults": {"ruleset": DEFAULT_RULESET_KEY, "system": HI_LO.slug, "kelly_fraction": 0.5},
    })


# --- /api/grid --------------------------------------------------------------------------------

@app.route("/api/grid", methods=["GET"])
def api_grid():
    key = request.args.get("ruleset", DEFAULT_RULESET_KEY)
    rules = _resolve_ruleset(key)
    if rules is None:
        return jsonify({"error": f"Unknown ruleset {key!r}"}), 400
    grid = GRIDS[rules.key()]
    return jsonify({
        section: {
            cell_key: {"action": cell.action, "ev_by_action": cell.ev_by_action, "margin": cell.margin}
            for cell_key, cell in cells.items()
        }
        for section, cells in grid.items()
    })


# --- /api/advise ------------------------------------------------------------------------------

@app.route("/api/advise", methods=["POST"])
def api_advise():
    data = request.get_json(force=True)
    rules = _resolve_ruleset(data.get("rules", DEFAULT_RULESET_KEY))
    if rules is None:
        return jsonify({"error": f"Unknown ruleset {data.get('rules')!r}"}), 400
    system, err = _resolve_system(data.get("system", "hi-lo"))
    if err:
        return jsonify({"error": err}), 400

    hand = Hand(data["player_cards"])
    upcard = Card(rank=data["dealer_up"], suit=None)
    running_count = data.get("running_count", 0)
    decks_remaining = data.get("decks_remaining", rules.num_decks)

    basic = basic_strategy.advise(hand, upcard, rules)
    counter = _counter_for(rules, system, running_count, decks_remaining)
    deviation = deviations.advise(hand, upcard, counter, rules)

    response = {
        "action": basic.code,
        "reason": _CODE_DESCRIPTIONS.get(basic.code, basic.code),
        "ev": {_ACTION_WORD[k]: v for k, v in basic.ev_by_action.items()},
        "margin": basic.margin,
        "true_count": deviation.true_count,
        "is_deviation": deviation.is_deviation,
    }
    if deviation.is_deviation:
        response["deviation_action"] = deviation.action.name.lower()
        response["deviation_reason"] = deviation.deviation_reason
        response["ev_gain"] = deviation.ev_gain
    return jsonify(response)


# --- /api/count -------------------------------------------------------------------------------

def _counter_json(counter: Counter) -> dict:
    result = {
        "running_count": counter.running_count,
        "decks_remaining": counter.decks_remaining,
        "dealt": counter.dealt,
    }
    if counter.system.balanced:
        result["true_count_betting"] = counter.true_count(rounding="floor")  # floor: conservative, for bet sizing
        result["true_count_playing"] = counter.true_count(rounding="nearest")  # nearest: for play deviations
    if counter.system.needs_ace_side_count:
        result["aces_seen"] = counter.aces_seen
    return result


@app.route("/api/count", methods=["POST"])
def api_count():
    data = request.get_json(force=True)
    num_decks = data.get("num_decks", 6)
    cards = [Card(rank=r, suit=None) for r in data["cards"]]

    if "betting_system" in data or "playing_system" in data:
        betting_sys, err1 = _resolve_system(data.get("betting_system", "hi-lo"))
        playing_sys, err2 = _resolve_system(data.get("playing_system", "hi-lo"))
        if err1 or err2:
            return jsonify({"error": err1 or err2}), 400
        betting, playing = Counter.paired(betting_sys, playing_sys, num_decks)
        for c in cards:
            betting.see(c)
            playing.see(c)
        return jsonify({"betting": _counter_json(betting), "playing": _counter_json(playing)})

    system, err = _resolve_system(data.get("system", "hi-lo"))
    if err:
        return jsonify({"error": err}), 400
    counter = Counter(system, num_decks)
    for c in cards:
        counter.see(c)
    return jsonify(_counter_json(counter))


# --- /api/stake -------------------------------------------------------------------------------

@app.route("/api/stake", methods=["POST"])
def api_stake():
    data = request.get_json(force=True)
    rules = _resolve_ruleset(data.get("rules", DEFAULT_RULESET_KEY))
    if rules is None:
        return jsonify({"error": f"Unknown ruleset {data.get('rules')!r}"}), 400
    system_slug = data.get("system", "hi-lo")

    model = _load_edge_model(rules.key(), system_slug)
    if model is None:
        return jsonify({
            "error": f"No locked edge model for {rules.key()}/{system_slug} -- "
                     f"run scripts/run_sim_battery.py --generate first"
        }), 400

    true_count = data["true_count"]
    bankroll = data["bankroll"]
    fraction = data.get("kelly_fraction", 0.5)
    limits = data.get("table_limits", {})
    table_min, table_max, chip = limits.get("min", 10), limits.get("max", 1000), limits.get("chip", 5)
    variance = data.get("variance", 1.3)

    edge = predict_edge(model, true_count)
    bet = kelly_bet(bankroll, edge, variance, fraction, table_min, table_max, chip)
    n0 = n_zero(edge, variance)

    return jsonify({
        "bet": bet,
        "edge": edge,
        "is_extrapolating": is_extrapolating(true_count),
        "risk_of_ruin": risk_of_ruin(bankroll / table_min, edge, variance),
        # n_zero is +inf at edge <= 0 (metrics.n_zero's documented contract) -- Python's
        # json.dumps happily emits the literal token `Infinity`, which is NOT valid JSON
        # and silently breaks strict JSON.parse() callers (this API's own web UI included:
        # a null-edge true count in the Bankroll tab's bet ramp made every subsequent bar
        # in that batch fail to render, since the whole array failed to parse). None ->
        # JSON `null`; the client already renders that as "∞".
        "n_zero": n0 if math.isfinite(n0) else None,
    })


# --- /api/simulate (bounded -- see the build plan's [!WARNING]) ---------------------------

MAX_SIMULATE_HANDS = 200_000


@app.route("/api/simulate", methods=["POST"])
def api_simulate():
    data = request.get_json(force=True)
    rules = _resolve_ruleset(data.get("rules", DEFAULT_RULESET_KEY))
    if rules is None:
        return jsonify({"error": f"Unknown ruleset {data.get('rules')!r}"}), 400
    system, err = _resolve_system(data.get("system", "hi-lo"))
    if err:
        return jsonify({"error": err}), 400

    use_deviations = bool(data.get("use_deviations", True))
    if use_deviations:
        idx_path = DEFAULT_INDEX_CACHE_DIR / f"{rules.key()}__{system.slug}.json"
        if not idx_path.exists():
            return jsonify({
                "error": f"No pre-built index cache for {rules.key()}/{system.slug} -- deriving one takes "
                         f"~9 minutes; run scripts/build_all_indices.py for this ruleset+system first, or "
                         f"pass use_deviations=false for basic-strategy-only simulation"
            }), 400

    n_hands = min(int(data.get("n_hands", 20_000)), MAX_SIMULATE_HANDS)
    other_players = int(data.get("other_players", 0))

    result = run_battery(rules, system, n_hands, use_deviations=use_deviations, other_players=other_players)
    return jsonify({
        "n_hands": result.n_hands,
        "mean": result.overall.mean,
        "stderr": result.overall.stderr,
        "variance": result.overall.variance,
        "n_doubled": result.n_doubled,
        "n_split_rounds": result.n_split_rounds,
        "seconds": result.seconds,
    })


# --- /api/game/* -- server-side session state, never the shoe itself to the client --------

@dataclass
class GameSession:
    rules: RuleSet
    system: CountingSystem
    shoe: Shoe
    counter: Counter
    round_gen: Optional[object] = None   # the play_hands_interactive generator, mid-round
    dealer_hand: Optional[Hand] = None
    dealer_up: Optional[Card] = None
    bet: Optional[float] = None
    insurance_payout: Optional[float] = None
    current_hand: Optional[Hand] = None
    current_legal: Optional[frozenset] = None


SESSIONS: Dict[str, GameSession] = {}


def _record_round(session: GameSession, result: RoundResult) -> None:
    """Feeds every card from a just-CONCLUDED round to the session counter --
    dealer hand and every player hand, including the hole card even when
    play_dealer never ran (see simulator.py's own identical comment: a
    multi-seat table would reveal it via some other seat almost always
    anyway). The counter deliberately lags one round behind what the UI shows
    (see api_game_deal/api_game_action) -- consistent with Phase 8's simulator
    convention, not a separate approximation: index play only ever applies to
    a round's OWN first decision anyway, which is checked before this round's
    own cards join the count, exactly like a real player would size next
    round's bet only after this one's cards are all out."""
    for card in result.dealer_hand.cards:
        session.counter.see(card)
    for ph in result.player_hands:
        for card in ph.hand.cards:
            session.counter.see(card)


def _round_result_json(result: RoundResult) -> dict:
    return {
        "dealer_hand": [c.rank for c in result.dealer_hand.cards],
        "dealer_total": result.dealer_hand.total,
        "hands": [
            {
                "cards": [c.rank for c in ph.hand.cards],
                "total": ph.hand.total,
                "surrendered": ph.surrendered,
                "doubled": ph.doubled,
                "bet": ph.bet,
            }
            for ph in result.player_hands
        ],
        "payouts": result.payouts,
        "insurance_payout": result.insurance_payout,
        "dealer_blackjack": result.dealer_blackjack,
        "net": sum(result.payouts) + (result.insurance_payout or 0.0),
    }


def _session_state_json(session: GameSession) -> dict:
    """The client's redacted view -- NEVER the shoe composition (build plan's
    Phase 10 [!IMPORTANT]): just the session id's public state."""
    state = {
        "running_count": session.counter.running_count,
        "decks_remaining": session.counter.decks_remaining,
        "round_active": session.round_gen is not None,
    }
    if session.system.balanced:
        state["true_count"] = session.counter.true_count(rounding="nearest")
    if session.dealer_up is not None and session.round_gen is not None:
        state["dealer_up"] = session.dealer_up.rank
    if session.current_hand is not None:
        state["hand"] = [c.rank for c in session.current_hand.cards]
        state["total"] = session.current_hand.total
        state["is_soft"] = session.current_hand.is_soft
        state["legal_actions"] = sorted(a.name.lower() for a in session.current_legal)
    return state


@app.route("/api/game/new", methods=["POST"])
def api_game_new():
    data = request.get_json(force=True) or {}
    rules = _resolve_ruleset(data.get("rules", DEFAULT_RULESET_KEY))
    if rules is None:
        return jsonify({"error": f"Unknown ruleset {data.get('rules')!r}"}), 400
    system, err = _resolve_system(data.get("system", "hi-lo"))
    if err:
        return jsonify({"error": err}), 400

    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = GameSession(
        rules=rules, system=system,
        shoe=Shoe(rules.num_decks, rules.penetration),
        counter=Counter(system, rules.num_decks),
    )
    return jsonify({"session_id": session_id, "ruleset": rules.key(), "system": system.slug})


@app.route("/api/game/deal", methods=["POST"])
def api_game_deal():
    data = request.get_json(force=True)
    session = SESSIONS.get(data.get("session_id", ""))
    if session is None:
        return jsonify({"error": "Unknown or expired session_id"}), 404
    if session.round_gen is not None:
        return jsonify({"error": "A round is already in progress -- finish it via /api/game/action first"}), 400

    bet = data["bet"]
    if session.shoe.cut_card_reached:
        session.shoe.reset()
        session.counter.reset()

    dealt = deal_initial(
        session.shoe, session.rules, bet,
        insurance_fn=lambda *_: deviations.should_take_insurance(session.counter),
    )
    if isinstance(dealt, RoundResult):
        _record_round(session, dealt)
        return jsonify({"round_result": _round_result_json(dealt), "state": _session_state_json(session)})

    session.dealer_hand = dealt.dealer_hand
    session.dealer_up = dealt.dealer_up
    session.bet = dealt.bet
    session.insurance_payout = dealt.insurance_payout
    session.round_gen = play_hands_interactive(dealt.player_hand, bet, dealt.dealer_up, session.shoe, session.rules)
    session.current_hand, session.current_legal = next(session.round_gen)

    return jsonify({"state": _session_state_json(session)})


_ACTION_FROM_NAME = {a.name: a for a in Action}


@app.route("/api/game/action", methods=["POST"])
def api_game_action():
    data = request.get_json(force=True)
    session = SESSIONS.get(data.get("session_id", ""))
    if session is None:
        return jsonify({"error": "Unknown or expired session_id"}), 404
    if session.round_gen is None:
        return jsonify({"error": "No round in progress -- call /api/game/deal first"}), 400

    action_name = str(data.get("action", "")).upper()
    action = _ACTION_FROM_NAME.get(action_name)
    if action is None:
        return jsonify({"error": f"Unknown action {data.get('action')!r}"}), 400
    if action not in session.current_legal:
        return jsonify({"error": f"{action.name} is not legal here", "legal_actions": sorted(
            a.name.lower() for a in session.current_legal)}), 400

    try:
        session.current_hand, session.current_legal = session.round_gen.send(action)
        return jsonify({"state": _session_state_json(session)})
    except StopIteration as stop:
        player_hands = stop.value
        result = settle_round(
            session.dealer_hand, player_hands, session.shoe, session.rules, session.bet, session.insurance_payout
        )
        _record_round(session, result)
        session.round_gen = None
        session.current_hand = None
        session.current_legal = None
        return jsonify({"round_result": _round_result_json(result), "state": _session_state_json(session)})


if __name__ == "__main__":
    app.run(debug=True)
