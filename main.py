"""CLI entry point: solve and print a basic-strategy grid.

    py main.py --decks 6 --s17 --das --surrender late --print-grid
"""

import argparse

from src.engine.rules import RuleSet
from src.strategy.grid_builder import HARD_TOTALS, PAIR_RANKS, SOFT_TOTALS, UPCARD_VALUES, solve_grid_cached


def print_grid(rules: RuleSet) -> None:
    grid = solve_grid_cached(rules)
    print(f"Ruleset: {rules.key()}")

    header = "      " + "  ".join(f"{u:>2}" for u in UPCARD_VALUES)

    print("\nHard Totals")
    print(header)
    for total in HARD_TOTALS:
        cells = [grid["hard"][f"{total}v{u}"].action for u in UPCARD_VALUES]
        print(f"{total:>4}  " + "  ".join(f"{c:>2}" for c in cells))

    print("\nSoft Totals")
    print(header)
    for total in SOFT_TOTALS:
        label = f"A,{total - 11}"
        cells = [grid["soft"][f"{total}v{u}"].action for u in UPCARD_VALUES]
        print(f"{label:>4}  " + "  ".join(f"{c:>2}" for c in cells))

    print("\nPairs")
    print(header)
    for rank in PAIR_RANKS:
        label = f"{rank}{rank}"
        cells = [grid["pairs"][f"{rank}{rank}v{u}"].action for u in UPCARD_VALUES]
        print(f"{label:>4}  " + "  ".join(f"{c:>2}" for c in cells))


def main() -> None:
    parser = argparse.ArgumentParser(description="Blackjack basic-strategy grid solver")
    parser.add_argument("--decks", type=int, default=6, choices=[1, 2, 4, 6, 8])
    parser.add_argument("--s17", action="store_true", help="Dealer stands on soft 17 (default)")
    parser.add_argument("--h17", action="store_true", help="Dealer hits soft 17")
    parser.add_argument("--das", action="store_true", default=True, help="Double after split (default)")
    parser.add_argument("--no-das", action="store_false", dest="das")
    parser.add_argument("--surrender", choices=["late", "early", "none"], default="late")
    parser.add_argument("--no-peek", action="store_true", help="European no-hole-card dealer")
    parser.add_argument("--print-grid", action="store_true")
    args = parser.parse_args()

    rules = RuleSet(
        num_decks=args.decks,
        dealer_hits_soft_17=args.h17,
        double_after_split=args.das,
        surrender=args.surrender,
        dealer_peeks=not args.no_peek,
    )

    if args.print_grid:
        print_grid(rules)


if __name__ == "__main__":
    main()
