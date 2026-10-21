"""Phase 2: build src/poker/evaluator.py's lookup tables from a full, direct
enumeration of all C(52,5) = 2,598,960 five-card hands, and persist them to
data/poker/evaluator/tables.npz (gitignored -- deterministically regenerable
in well under a minute, see .gitignore). Run this once before using
src.poker.evaluator for real.

    py scripts/poker/build_evaluator_tables.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

from src.poker.evaluator import TABLE_PATH, build_tables


def main() -> None:
    t0 = time.perf_counter()
    tables = build_tables()
    t1 = time.perf_counter()
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez(TABLE_PATH, **tables)
    t2 = time.perf_counter()
    n_classes = len(tables["class_to_category"])
    print(f"Classified all C(52,5) hands into {n_classes} rank classes in {t1 - t0:.1f}s")
    print(f"Saved to {TABLE_PATH} in {t2 - t1:.1f}s")


if __name__ == "__main__":
    main()
