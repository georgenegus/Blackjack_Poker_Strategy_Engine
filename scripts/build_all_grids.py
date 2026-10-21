"""Pre-solve every shipped ruleset's basic-strategy grid to data/strategy/.

Solving one ruleset's full grid is expensive in pure Python (~110s on this dev
machine for the default 6D/S17/DAS ruleset -- see the Phase 4 tracking-table
entry). This script exists so the Flask app (Phase 10) and CLI (main.py) never
solve on demand, only ever load an already-cached grid via solve_grid_cached().

    py scripts/build_all_grids.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.engine.rules import shipped_rulesets
from src.strategy.grid_builder import solve_grid_cached


def main() -> None:
    rulesets = list(shipped_rulesets())
    print(f"Pre-solving {len(rulesets)} shipped rulesets...")
    for i, rules in enumerate(rulesets, 1):
        t0 = time.perf_counter()
        solve_grid_cached(rules)
        t1 = time.perf_counter()
        print(f"[{i}/{len(rulesets)}] {rules.key()}: {t1 - t0:.1f}s")


if __name__ == "__main__":
    main()
