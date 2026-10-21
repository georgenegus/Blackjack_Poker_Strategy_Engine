"""Phase 8: run a full Monte Carlo battery, fit the edge model, print the
standard advantage-play metrics, and (optionally) lock
data/baselines/edge_model_baseline.json.

    py scripts/run_sim_battery.py --decks 6 --das --surrender late --system hi-lo --hands 20000000
    py scripts/run_sim_battery.py --decks 6 --das --surrender late --system hi-lo --hands 2000000 --spread 1-12
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.counting.edge_model import TRUSTED_TC_RANGE, fit_edge_model, keyed_baseline_path, save_baseline
from src.counting.systems import system_for_slug
from src.engine.rules import RuleSet
from src.simulation import metrics
from src.simulation.simulator import flat_bet_fn, run_battery


def _spread_bet_fn(spread: str):
    """"1-12" -> a simple linear ramp from `lo` units at TC<=0 to `hi` units at
    TC>=10. A stand-in for Phase 9's real Kelly-derived bet_ramp -- exercises
    the simulator's bet-spread path, not intended as the final betting
    strategy (no table-max/chip-denomination rounding, no risk-of-cover framing)."""
    lo_s, hi_s = spread.split("-")
    lo, hi = float(lo_s), float(hi_s)

    def bet_fn(tc: float) -> float:
        if tc <= 0:
            return lo
        frac = min(tc, 10) / 10.0
        return lo + frac * (hi - lo)

    return bet_fn


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 8 Monte Carlo battery")
    parser.add_argument("--decks", type=int, default=6, choices=[1, 2, 4, 6, 8])
    parser.add_argument("--h17", action="store_true", help="Dealer hits soft 17")
    parser.add_argument("--das", action="store_true", default=True)
    parser.add_argument("--no-das", action="store_false", dest="das")
    parser.add_argument("--surrender", choices=["late", "early", "none"], default="late")
    parser.add_argument("--system", default="hi-lo")
    parser.add_argument("--hands", type=int, default=2_000_000)
    parser.add_argument("--spread", default=None, help='e.g. "1-12"; default flat 1 unit')
    parser.add_argument("--no-deviations", action="store_true", help="Basic strategy only, no index play")
    parser.add_argument("--other-players", type=int, default=0)
    parser.add_argument("--bankroll", type=float, default=200.0, help="Bankroll in units, for risk of ruin")
    parser.add_argument("--generate", action="store_true", help="Lock data/baselines/edge_model_baseline.json")
    args = parser.parse_args()

    try:
        system = system_for_slug(args.system)
    except ValueError as e:
        raise SystemExit(str(e))
    rules = RuleSet(
        num_decks=args.decks, dealer_hits_soft_17=args.h17,
        double_after_split=args.das, surrender=args.surrender,
    )
    bet_fn = _spread_bet_fn(args.spread) if args.spread else flat_bet_fn

    print(
        f"Running {args.hands:,} hands: {rules.key()} / {system.name} / "
        f"{'basic strategy only' if args.no_deviations else 'with index play'} / "
        f"{'flat 1 unit' if not args.spread else 'spread ' + args.spread} / "
        f"{args.other_players} other player(s)..."
    )

    t0 = time.perf_counter()
    result = run_battery(
        rules, system, args.hands, bet_fn=bet_fn,
        use_deviations=not args.no_deviations, other_players=args.other_players,
    )
    elapsed = time.perf_counter() - t0

    print(f"\nDone in {elapsed:.0f}s ({result.n_hands / elapsed:.0f} hands/sec)")
    print(
        f"Overall: mean={result.overall.mean * 100:+.4f}% +/- {result.overall.stderr * 100:.4f}%  "
        f"variance={result.overall.variance:.4f}"
    )
    print(f"Doubled hands: {result.n_doubled:,}   Split rounds: {result.n_split_rounds:,}")

    model = fit_edge_model(result)
    print(
        f"\nEdge model: intercept={model.intercept * 100:+.4f}%  slope={model.slope * 100:+.4f}%/TC  "
        f"R^2={model.r_squared:.4f}  (fit over TC {model.fit_tc_range[0]:+d}..{model.fit_tc_range[1]:+d})"
    )
    print(f"{'TC':>4} {'n':>12} {'edge':>9} {'se':>8}")
    lo, hi = TRUSTED_TC_RANGE
    for b in model.buckets:
        flag = "  (thin / extrapolated range)" if (b.tc < lo or b.tc > hi) else ""
        print(f"{b.tc:+4d} {b.n:12,} {b.edge * 100:+8.4f}% {b.stderr * 100:7.4f}%{flag}")

    edge, var = result.overall.mean, result.overall.variance
    print(f"\nWin rate/100 hands: {metrics.win_rate_per_100(edge) * 100:+.4f}%")
    print(f"N0: {metrics.n_zero(edge, var):,.0f} hands")
    print(f"Risk of ruin at {args.bankroll:.0f} units: {metrics.risk_of_ruin(args.bankroll, edge, var) * 100:.2f}%")
    print(f"SCORE: {metrics.score(edge, var):.3f}   DI: {metrics.desirability_index(edge, var):.3f}")

    if args.generate:
        path = keyed_baseline_path(model.ruleset_key, system.slug)
        save_baseline(model, path=path)
        print(f"\nLocked baseline -> {path}")


if __name__ == "__main__":
    main()
