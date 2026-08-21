"""Phase 5, Check 2: simulated house edge under perfect basic strategy vs
published anchors. Runs real rounds through game.py's mechanics (not the
solver's own abstract EVs) via strategy_decide_fn -- this is what makes it an
INDEPENDENT check on Check 1: a bug in game.py's payout logic would corrupt
this number even though ev_solver.py/grid_builder.py are never touched by it.
See src/simulation/simulator.py's module docstring.

Anchors are for S17, DAS, double-any-two, NO surrender, 3:2, dealer peeks --
i.e. RuleSet(num_decks=d, surrender="none"), matching the build plan's
Appendix/Phase 5 anchor table exactly. Simulated with fresh_shoe_per_hand=True:
published house-edge figures assume no depletion/counting effects (that
asymmetry is what card counting exploits, out of scope here), and realistic
penetration measurably biases the result high -- confirmed empirically at
n=30M (2D: 0.259% vs published 0.190%, over 3 standard errors) before this
was understood; see simulate_house_edge's docstring.

Every simulated figure carries its own Monte Carlo standard error and is
reported with it -- never as a bare point estimate (see .agents/coding-
standards.md's "No Bare Point Estimates from Monte Carlo").

Usage (matches the build plan's example invocation):
    py tests/test_house_edge.py --hands 30000000 --decks 2 4 6 8
    py tests/test_house_edge.py --hands 30000000 --decks 2 4 6 8 --generate
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Needed when run as a direct script (py tests/test_house_edge.py ...) -- Python
# only puts the invoked script's own directory on sys.path, not the project root.
# Harmless (and unnecessary but not incorrect) when pytest imports this module instead.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.rules import RuleSet
from src.simulation.simulator import simulate_house_edge
from src.strategy.basic_strategy import strategy_decide_fn

# Published house-edge anchors: S17, DAS, double-any-two, no surrender, 3:2,
# dealer peeks, 75% penetration. See the build plan's Phase 5, Check 2 table.
PUBLISHED_HOUSE_EDGE = {
    2: 0.0019,
    4: 0.0035,
    6: 0.0040,
    8: 0.0043,
}
TOLERANCE = 0.0002  # +/- 0.02%, per the build plan

BASELINE_PATH = Path("data/baselines/house_edge_baseline.json")


def ruleset_for_decks(decks: int) -> RuleSet:
    return RuleSet(num_decks=decks, surrender="none")


def run_check(decks: int, n_hands: int) -> dict:
    rules = ruleset_for_decks(decks)
    t0 = time.perf_counter()
    mean, se = simulate_house_edge(rules, strategy_decide_fn, n_hands=n_hands, bet=1.0, fresh_shoe_per_hand=True)
    elapsed = time.perf_counter() - t0
    edge = -mean
    anchor = PUBLISHED_HOUSE_EDGE[decks]
    return {
        "decks": decks,
        "ruleset_key": rules.key(),
        "n_hands": n_hands,
        "simulated_edge": edge,
        "stderr": se,
        "published_anchor": anchor,
        "tolerance": TOLERANCE,
        "within_tolerance": abs(edge - anchor) <= TOLERANCE,
        "seconds": elapsed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 house-edge validation gate")
    parser.add_argument("--hands", type=int, default=30_000_000)
    parser.add_argument("--decks", type=int, nargs="+", default=[2, 4, 6, 8])
    parser.add_argument("--generate", action="store_true", help="Lock data/baselines/house_edge_baseline.json")
    args = parser.parse_args()

    results = {}
    all_pass = True
    for d in args.decks:
        r = run_check(d, args.hands)
        results[str(d)] = r
        status = "PASS" if r["within_tolerance"] else "FAIL"
        all_pass = all_pass and r["within_tolerance"]
        print(
            f"{d}D ({r['ruleset_key']}): simulated={r['simulated_edge'] * 100:.4f}% "
            f"+/- {r['stderr'] * 100:.4f}%  published={r['published_anchor'] * 100:.4f}%  "
            f"[{status}]  ({r['seconds']:.0f}s, {args.hands:,} hands)"
        )

    print(f"\n{'ALL PASS' if all_pass else 'SOME FAILED'}")

    if args.generate:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BASELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Locked baseline -> {BASELINE_PATH}")


if __name__ == "__main__":
    main()
