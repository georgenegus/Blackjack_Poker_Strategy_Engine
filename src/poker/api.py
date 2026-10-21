"""Phase 12: Flask Blueprint exposing the poker engine over HTTP. See
markdowns/poker/poker_build_plan_v1.md Phase 12.

The entire poker HTTP surface lives here, under url_prefix="/api/poker" --
app.py's only permitted edit is importing `poker_bp` and registering it (two
lines), so this Blueprint owns every route, every startup registry, and
every error-message convention for the area, exactly as the plan requires.

Two real discrepancies between the plan's own Implementation-section
pseudocode/verification text and what actually exists in this repo, found
while wiring this Blueprint up and resolved in favour of the real, already-
built artifacts rather than the plan's earlier speculation:
  - The plan's verification block curls "/api/blackjack/grid" -- the
    blackjack area's actual routes (app.py, unmodified by this phase) live
    directly under "/api/" (e.g. "/api/grid"), never under "/api/blackjack/".
  - The plan's startup pseudocode loads "preflop_169x169.npy" -- Phase 3
    actually persisted "preflop_169x169.npz" (see
    scripts/poker/build_preflop_equity.py's own tracking-table entry), and
    it is loaded via src.poker.pushfold._load_matrix() (already-existing,
    already-cached), not a second, separate load path here.
  - The plan's startup pseudocode also says the evaluator's "124MB" table is
    loaded lazily on first equity request -- that 124MB figure was Strategy
    B, which Phase 2 never built; the real (Strategy A) table is ~152KB.
    Nothing extra is needed here regardless: src.poker.evaluator._load_tables
    already lazily caches on first real use, via equity_exact/equity_mc.

Every response carrying a Monte-Carlo number includes its standard error in
the SAME JSON object (never a sibling-only field); every response carrying a
solved strategy includes its abstraction_exploitability_mbb and iterations,
per the plan's own [!IMPORTANT] -- so a UI that forgets to render one is an
obvious, visible omission, not an invisible one.
"""
from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, jsonify, request

from src.poker.advisor import advise as advisor_advise
from src.poker.bankroll import (
    recommend_max_buyin,
    required_bankroll_bb,
    risk_of_ruin,
    win_rate_confidence_interval,
)
from src.poker.cards import card_ids
from src.poker.equity import equity as equity_dispatch
from src.poker.equity import equity_distribution, runout_count
from src.poker.icm import bubble_factor, icm_equity
from src.poker.pushfold import solve_pushfold
from src.poker.ranges import Range, range_vs_range_equity
from src.poker.spec import GameSpec

poker_bp = Blueprint("poker", __name__, url_prefix="/api/poker")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STRATEGY_DIR = REPO_ROOT / "data" / "poker" / "strategy"

# --- Startup registries -------------------------------------------------------

# Every spec that's actually been solved and saved, discovered by scanning
# the strategy directory rather than assuming a fixed list -- there is no
# poker-side equivalent yet of the blackjack area's shipped_rulesets()
# registry to enumerate "the specs that are SUPPOSED to exist".
PREFLOP: dict[str, dict] = {}
for _dir in sorted(STRATEGY_DIR.glob("*")) if STRATEGY_DIR.exists() else []:
    _path = _dir / "preflop.json"
    if _path.exists():
        PREFLOP[_dir.name] = json.loads(_path.read_text())

MAX_SOLVE_ITERATIONS = 200_000
MAX_SOLVE_SECONDS = 30.0
MAX_SOLVE_COMBO_PAIRS = 20_000  # see api_solve's [!WARNING]-mandated pre-check


def _parse_spec(key: str) -> GameSpec | None:
    from scripts.poker.solve_preflop import parse_spec_key

    try:
        return parse_spec_key(key)
    except ValueError:
        return None


# --- /api/poker/spec -----------------------------------------------------------


@poker_bp.route("/spec", methods=["GET"])
def api_spec():
    default = GameSpec()
    return jsonify(
        {
            "default_key": default.key(),
            "default": {
                "num_players": default.num_players,
                "stack_bb": default.stack_bb,
                "sb": default.sb,
                "bb": default.bb,
                "rake_pct": default.rake_pct,
                "rake_cap_bb": default.rake_cap_bb,
                "bet_sizes": list(default.bet_sizes),
            },
            "solved_preflop_specs": sorted(PREFLOP.keys()),
        }
    )


# --- /api/poker/equity ----------------------------------------------------------


@poker_bp.route("/equity", methods=["POST"])
def api_equity():
    data = request.get_json(force=True)
    try:
        hands = [card_ids(h) for h in data["hands"]]
        board = card_ids(data.get("board", ""))
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"invalid hands/board: {e}"}), 400

    n_samples = int(data.get("n_samples", 100_000))
    seed = data.get("seed")
    equities, se = equity_dispatch(hands, board, n_samples=n_samples, seed=seed)

    n_known = len(board) + sum(len(h) for h in hands)
    response = {
        "equities": [float(e) for e in equities],
        "method": "exact" if se is None else "mc",
        "runouts": runout_count(n_known, 5 - len(board)),
    }
    if se is not None:
        response["standard_error"] = [float(e) for e in se]
    else:
        # Phase 13's Equity tab headline chart is the per-player equity
        # DISTRIBUTION (win/tie/lose shares across runouts), not just the
        # mean -- "the picture that explains why a 55% hand can be a
        # check-fold" (its own equity is often bimodal: usually way ahead
        # or way behind, rarely near 55%, per the plan's own framing).
        # equity_distribution is exact-enumeration-only (no MC fallback),
        # so it's only attached on the exact path -- which, per the
        # always-exact finding documented in this module's docstring and
        # tests/poker/test_api.py, is every real Hold'em spot this route
        # can ever be asked about anyway.
        distribution = equity_distribution(hands, board)
        response["distribution"] = [{str(v): p for v, p in d.items()} for d in distribution]
    return jsonify(response)


# --- /api/poker/range/parse, /api/poker/range/equity ---------------------------


@poker_bp.route("/range/parse", methods=["POST"])
def api_range_parse():
    data = request.get_json(force=True)
    try:
        rng = Range(data["notation"])
    except (ValueError, KeyError) as e:
        return jsonify({"error": f"invalid range notation: {e}"}), 400

    from src.poker.cards import id_to_str

    return jsonify(
        {
            "combos": {id_to_str(c[0]) + id_to_str(c[1]): w for c, w in rng.combos().items()},
            "n_combos": rng.n_combos(),
            "percent_of_hands": rng.percent_of_hands(),
        }
    )


@poker_bp.route("/range/equity", methods=["POST"])
def api_range_equity():
    data = request.get_json(force=True)
    try:
        range_a = Range(data["range_a"])
        range_b = Range(data["range_b"])
        board = card_ids(data.get("board", ""))
    except (ValueError, KeyError) as e:
        return jsonify({"error": f"invalid range/board: {e}"}), 400

    try:
        eq_a, eq_b = range_vs_range_equity(range_a, range_b, board)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"equity_a": eq_a, "equity_b": eq_b})


# --- /api/poker/preflop ----------------------------------------------------------


@poker_bp.route("/preflop", methods=["GET"])
def api_preflop():
    key = request.args.get("spec", GameSpec().key())
    solved = PREFLOP.get(key)
    if solved is None:
        return jsonify(
            {
                "error": f"No solved preflop strategy for {key!r} -- run "
                f"`py scripts/poker/solve_preflop.py --spec {key}` first"
            }
        ), 400
    return jsonify(solved)


# --- /api/poker/advise -----------------------------------------------------------


@poker_bp.route("/advise", methods=["POST"])
def api_advise():
    data = request.get_json(force=True)
    spec = _parse_spec(data.get("spec", GameSpec().key()))
    if spec is None:
        return jsonify({"error": f"unrecognised spec key {data.get('spec')!r}"}), 400

    try:
        advice = advisor_advise(data["hand"], data["position"], data.get("history", []), spec)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError as e:
        return jsonify({"error": str(e).strip("'\"")}), 400

    return jsonify({"action_frequencies": advice.action_frequencies, "is_close": advice.is_close})


# --- /api/poker/pushfold ---------------------------------------------------------

PUSHFOLD_ITERATIONS = 200  # matches Phase 9's own finding: stable to ~0.3-1pp by 200-300 iterations


@poker_bp.route("/pushfold", methods=["GET"])
def api_pushfold():
    try:
        stack_bb = float(request.args.get("stack", 15.0))
    except ValueError:
        return jsonify({"error": "stack must be a number"}), 400
    if not (0.5 <= stack_bb <= 25.0):
        return jsonify({"error": "stack must be between 0.5 and 25.0 bb -- push/fold is only well-defined at short effective stacks"}), 400

    result = solve_pushfold(GameSpec(stack_bb=stack_bb), iterations=PUSHFOLD_ITERATIONS)
    return jsonify(
        {
            "stack_bb": stack_bb,
            "jam_pct": result.jam_pct,
            "call_pct": result.call_pct,
            "jam": {label: w for label, w in result.jam.items() if w > 1e-3},
            "call": {label: w for label, w in result.call.items() if w > 1e-3},
            "iterations": result.iterations,
        }
    )


# --- /api/poker/icm --------------------------------------------------------------


@poker_bp.route("/icm", methods=["POST"])
def api_icm():
    data = request.get_json(force=True)
    stacks = data.get("stacks")
    payouts = data.get("payouts")
    if not stacks or not payouts:
        return jsonify({"error": "stacks and payouts are both required"}), 400

    equities = icm_equity(stacks, payouts)
    response = {"equities": equities}

    if "player" in data and "opponent" in data and "risk_amount" in data:
        response["bubble_factor"] = bubble_factor(
            stacks, payouts, int(data["player"]), int(data["opponent"]), float(data["risk_amount"])
        )
    return jsonify(response)


# --- /api/poker/solve (bounded -- see the build plan's [!WARNING]) -------------


@poker_bp.route("/solve", methods=["POST"])
def api_solve():
    from scripts.poker.solve_spot import SpotGame, format_strategy, solve_spot
    from src.poker.exploit import sampled_exploitability

    data = request.get_json(force=True)
    try:
        board = tuple(card_ids(data["board"]))
        hero_range = Range(data["hero_range"])
        villain_range = Range(data["villain_range"])
    except (KeyError, ValueError) as e:
        return jsonify({"error": f"invalid board/range: {e}"}), 400

    # Reject an oversized tree BEFORE construction, per the plan's own
    # [!WARNING] -- an unbounded solve endpoint on a 7.7GB machine is a
    # self-inflicted denial of service, the same constraint api_simulate
    # (app.py, blackjack side) already lives under. n_combos() is a cheap
    # upper bound on the real (card-removal-filtered) pair count, computed
    # without ever building the full deal list SpotGame's constructor would.
    estimated_pairs = hero_range.n_combos() * villain_range.n_combos()
    if estimated_pairs > MAX_SOLVE_COMBO_PAIRS:
        return jsonify(
            {
                "error": f"hero_range x villain_range is too wide ({estimated_pairs:g} combo pairs, "
                f"max {MAX_SOLVE_COMBO_PAIRS}) -- narrow one or both ranges"
            }
        ), 400

    try:
        pot_bb = float(data["pot"])
        stack_bb = float(data["stack"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "pot and stack are both required numbers"}), 400

    iterations = min(int(data.get("iterations", 50_000)), MAX_SOLVE_ITERATIONS)
    max_seconds = min(float(data.get("max_seconds", 15.0)), MAX_SOLVE_SECONDS)

    try:
        game = SpotGame(board=board, hero_range=hero_range, villain_range=villain_range, pot_bb=pot_bb, stack_bb=stack_bb)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    result, n_iters, elapsed = solve_spot(game, iterations=iterations, max_seconds=max_seconds, seed=data.get("seed", 0))
    exp_mean, exp_se = sampled_exploitability(game, result.average_strategy, n_deals=min(100, len(game._deal_outcomes)), n_trials=3)

    return jsonify(
        {
            "iterations": n_iters,
            "elapsed_seconds": elapsed,
            "game_value_bb": result.game_value,
            "game_value_se_bb": result.game_value_se,
            "abstraction_exploitability_mbb": exp_mean * 1000.0,
            "abstraction_exploitability_se_mbb": exp_se * 1000.0,
            "strategy": format_strategy(result.average_strategy, game),
        }
    )


# --- /api/poker/bankroll ---------------------------------------------------------


@poker_bp.route("/bankroll", methods=["POST"])
def api_bankroll():
    data = request.get_json(force=True)
    try:
        win_rate = float(data["wr"])
        stdev = float(data["sd"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "wr and sd (both bb/100) are required numbers"}), 400

    response: dict = {}

    bankroll_bb = data.get("bankroll")
    if bankroll_bb is not None:
        response["risk_of_ruin"] = risk_of_ruin(float(bankroll_bb), win_rate, stdev)

    response["downswing_quantiles"] = {}
    for p in (0.5, 0.1, 0.05, 0.01):
        try:
            depth = required_bankroll_bb(win_rate, stdev, p)
            response["downswing_quantiles"][f"p{p:g}"] = depth
        except ValueError:
            response["downswing_quantiles"][f"p{p:g}"] = None

    n_hands = data.get("n_hands")
    observed = data.get("observed_wr")
    if n_hands is not None and observed is not None:
        lo, hi = win_rate_confidence_interval(float(observed), stdev, float(n_hands))
        response["confidence_interval"] = {"low": lo, "high": hi}

    total_bankroll = data.get("total_bankroll")
    target_ror = data.get("target_ror")
    if total_bankroll is not None and target_ror is not None:
        try:
            rec = recommend_max_buyin(float(total_bankroll), win_rate, stdev, float(target_ror))
            response["stake_advice"] = {
                "max_buyin": rec.max_buyin,
                "effective_target_ror": rec.effective_target_ror,
                "required_bankroll_bb": rec.required_bankroll_bb,
            }
        except ValueError as e:
            response["stake_advice_error"] = str(e)

    return jsonify(response)
