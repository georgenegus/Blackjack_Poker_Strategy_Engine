"""Pre-solve count-indexed deviations (Illustrious 18 + Fab 4 + insurance) to
data/indices/. See src/strategy/index_builder.py's module docstring for why this
must be pre-solved rather than derived on demand -- each ruleset+system
combination takes several minutes (each swept true count is a genuinely distinct
composition, unlike a single neutral-shoe grid solve), not seconds.

    py scripts/build_all_indices.py --decks 6 --s17 --das --surrender late --system hi-lo
    py scripts/build_all_indices.py                # all 32 shipped rulesets x Hi-Lo (hours)
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.counting.systems import system_for_slug
from src.engine.rules import RuleSet, shipped_rulesets
from src.strategy.index_builder import solve_indices_cached


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 7 count-index pre-solver")
    parser.add_argument("--decks", type=int, choices=[1, 2, 4, 6, 8], help="Solve one ruleset only")
    parser.add_argument("--h17", action="store_true", help="Dealer hits soft 17")
    parser.add_argument("--das", action="store_true", default=True)
    parser.add_argument("--no-das", action="store_false", dest="das")
    parser.add_argument("--surrender", choices=["late", "early", "none"], default="late")
    parser.add_argument("--system", default="hi-lo", help="Counting system slug (default: hi-lo)")
    args = parser.parse_args()

    try:
        system = system_for_slug(args.system)
    except ValueError as e:
        raise SystemExit(str(e))
    if args.decks is not None:
        rulesets = [RuleSet(
            num_decks=args.decks, dealer_hits_soft_17=args.h17,
            double_after_split=args.das, surrender=args.surrender,
        )]
    else:
        rulesets = list(shipped_rulesets())

    print(f"Pre-solving {len(rulesets)} ruleset(s) x system={system.name}...")
    for i, rules in enumerate(rulesets, 1):
        t0 = time.perf_counter()
        solve_indices_cached(system, rules.num_decks, rules)
        t1 = time.perf_counter()
        print(f"[{i}/{len(rulesets)}] {rules.key()}__{system.slug}: {t1 - t0:.1f}s")


if __name__ == "__main__":
    main()
