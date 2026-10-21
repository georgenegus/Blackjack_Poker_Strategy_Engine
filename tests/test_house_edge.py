"""Phase 5, Check 2: house edge under perfect basic strategy vs published anchors.

Two-tier design (see the build plan's Phase 5 Check 2 findings for how this was
arrived at -- the original all-Monte-Carlo version spent most of a build session
chasing what turned out to be pure sampling noise):

  PRIMARY  -- src.strategy.exact_edge.exact_house_edge(rules): a full, zero-noise
  combinatorial enumeration over every possible initial deal, using ev_solver.py's
  functions directly. Deterministic and fast (seconds to ~15 min depending on deck
  count), so its comparison against the published anchor uses a flat tolerance --
  there's no sampling error to account for.

  SECONDARY (sanity check) -- src.simulation.simulator.simulate_house_edge: plays
  real rounds through game.py's mechanics (not the solver's own abstract EVs), so
  it's what catches a bug in game.py's payout/settlement logic that the primary
  check can't see (exact_house_edge never touches game.py at all). It's compared
  against the PRIMARY check's own exact value, not the published anchor -- the
  small, expected gap between our exact figure and a published anchor (composition-
  dependent play is slightly better than the total-dependent chart the anchor
  represents) has nothing to do with whether game.py has a bug, and folding it into
  this comparison would just be re-adding noise to a question that doesn't need it.
  Because the reference side (exact) is noise-free, the tolerance is entirely a
  function of the simulation's OWN standard error (see MC_SE_MULTIPLIER) rather
  than a fixed band -- a fixed absolute tolerance against a noisy point estimate is
  exactly what made correct 4D/6D results intermittently "fail" before this fix.

Usage:
    py tests/test_house_edge.py --hands 2000000 --decks 2 4 6 8
    py tests/test_house_edge.py --hands 2000000 --decks 2 4 6 8 --generate
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
from src.strategy.exact_edge import exact_house_edge

# Published house-edge anchors: S17, DAS, double-any-two, no surrender, 3:2,
# dealer peeks, 75% penetration. See the build plan's Phase 5, Check 2 table.
PUBLISHED_HOUSE_EDGE = {
    2: 0.0019,
    4: 0.0035,
    6: 0.0040,
    8: 0.0043,
}
TOLERANCE = 0.0002       # +/- 0.02%, flat -- only ever compared against noise-free figures
MC_SE_MULTIPLIER = 4     # secondary check: simulated edge must be within this many of its
                         # own standard errors of the exact figure (not a fixed band)

BASELINE_PATH = Path("data/baselines/house_edge_baseline.json")


def ruleset_for_decks(decks: int) -> RuleSet:
    return RuleSet(num_decks=decks, surrender="none")


def run_check(decks: int, n_hands: int) -> dict:
    rules = ruleset_for_decks(decks)
    anchor = PUBLISHED_HOUSE_EDGE[decks]

    t0 = time.perf_counter()
    exact = exact_house_edge(rules)
    exact_seconds = time.perf_counter() - t0
    primary_gap = exact - anchor
    primary_pass = abs(primary_gap) <= TOLERANCE

    t0 = time.perf_counter()
    mean, se = simulate_house_edge(rules, strategy_decide_fn, n_hands=n_hands, bet=1.0, fresh_shoe_per_hand=True)
    mc_seconds = time.perf_counter() - t0
    simulated_edge = -mean
    secondary_tolerance = max(TOLERANCE, MC_SE_MULTIPLIER * se)
    secondary_gap = simulated_edge - exact
    secondary_pass = abs(secondary_gap) <= secondary_tolerance

    return {
        "decks": decks,
        "ruleset_key": rules.key(),
        "published_anchor": anchor,
        "exact_edge": exact,
        "primary_gap": primary_gap,
        "primary_tolerance": TOLERANCE,
        "primary_pass": primary_pass,
        "exact_seconds": exact_seconds,
        "n_hands": n_hands,
        "simulated_edge": simulated_edge,
        "stderr": se,
        "secondary_tolerance": secondary_tolerance,
        "secondary_gap": secondary_gap,
        "secondary_pass": secondary_pass,
        "mc_seconds": mc_seconds,
        "within_tolerance": primary_pass and secondary_pass,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 house-edge validation gate")
    parser.add_argument("--hands", type=int, default=2_000_000)
    parser.add_argument("--decks", type=int, nargs="+", default=[2, 4, 6, 8])
    parser.add_argument("--generate", action="store_true", help="Lock data/baselines/house_edge_baseline.json")
    args = parser.parse_args()

    results = {}
    all_pass = True
    for d in args.decks:
        r = run_check(d, args.hands)
        results[str(d)] = r
        all_pass = all_pass and r["within_tolerance"]
        p_status = "PASS" if r["primary_pass"] else "FAIL"
        s_status = "PASS" if r["secondary_pass"] else "FAIL"
        print(
            f"{d}D ({r['ruleset_key']}): "
            f"exact={r['exact_edge'] * 100:.4f}% vs published={r['published_anchor'] * 100:.4f}% "
            f"(gap={r['primary_gap'] * 100:+.4f}pp) [{p_status}]  ({r['exact_seconds']:.0f}s)\n"
            f"{'':>{len(str(d)) + 1}}   simulated={r['simulated_edge'] * 100:.4f}% +/- {r['stderr'] * 100:.4f}% "
            f"vs exact (gap={r['secondary_gap'] * 100:+.4f}pp, tolerance={r['secondary_tolerance'] * 100:.4f}pp) "
            f"[{s_status}]  ({args.hands:,} hands, {r['mc_seconds']:.0f}s)"
        )

    print(f"\n{'ALL PASS' if all_pass else 'SOME FAILED'}")

    if args.generate:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BASELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Locked baseline -> {BASELINE_PATH}")


if __name__ == "__main__":
    main()
