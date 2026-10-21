"""Phase 3: build the 169x169 preflop equity matrix (data/poker/equity/
preflop_169x169.npy, committed -- see markdowns/poker/poker_build_plan_v1.md
Phase 3, step 4).

For each ordered pair of the 169 canonical starting-hand classes, hero's
equity depends on more than just the two classes: whether the two hands
SHARE any suits changes it by up to ~1.4pp (see Appendix A.4, computed in
this phase). This script computes each class pair's equity as the correctly
combo-weighted average across every distinct suit CONFIGURATION consistent
with that pair, not a single representative -- averaging the equity for one
arbitrarily-picked concrete matchup per class pair would silently corrupt the
committed matrix by up to that same ~1.4pp, which is exactly the same class
of bug as computing range-vs-range equity without joint card removal
(.agents/skills/poker_range_conventions/SKILL.md).

For a fixed pair of classes, the raw C(combos_i, combos_j) concrete matchups
collapse (via cards.canonical()) into a handful of distinct suit "shapes" --
sampled at ~3.4 on average, up to 7 for offsuit-vs-offsuit pairs -- so only
one equity_exact() enumeration is needed per shape, not per raw combo pair.

    py scripts/poker/build_preflop_equity.py [--limit N] [--out PATH]

Runtime: ~1.7s per shape (measured with the numba-accelerated evaluator),
~3.4 shapes/pair average, 14,365 unordered class pairs (169 choose 2, plus
the 169 self-matchups) -> on the order of a day for the full matrix. Use
--limit to build and time a small prefix for a quick correctness/ETA check
without committing to the full run.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

from src.poker.equity import equity_exact
from src.poker.ranges import _ordered_shape, hand_classes

OUT_PATH_DEFAULT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "poker",
    "equity",
    "preflop_169x169.npy",
)


def shapes_for_pair(combos_i, combos_j):
    """-> list of (representative_combo_i, representative_combo_j, weight).
    Groups every non-card-conflicting (combo_a, combo_b) raw pair by its
    order-sensitive suit-isomorphism shape (src.poker.ranges._ordered_shape,
    with an empty board -- this script never has one), so only one
    equity_exact() call is needed per distinct shape; `weight` is how many
    raw combo pairs share that shape (the correct combo-weighting for the
    aggregate average). Was previously a local, independent implementation
    of the same shape-collision bug now documented on _ordered_shape's
    docstring in ranges.py (Phase 4) -- relocated there as the single
    definition once Phase 4 needed the identical logic generalised to
    arbitrary ranges and a possibly-nonempty board."""
    weight: dict = {}
    rep: dict = {}
    for a in combos_i:
        for b in combos_j:
            if set(a) & set(b):
                continue
            key = _ordered_shape(a, b, ())
            weight[key] = weight.get(key, 0) + 1
            rep.setdefault(key, (a, b))
    return [(rep[k][0], rep[k][1], w) for k, w in weight.items()]


def build_matrix(labels, combo_groups, limit: int | None = None, progress_every: int = 25):
    """Build the (169, 169) hero-equity matrix. matrix[i, j] is class i's
    equity against class j; matrix[j, i] = 1 - matrix[i, j] by construction
    (equity_exact's own two-player output already sums to 1.0, so this needs
    no separate enforcement). matrix[i, i] must be exactly 0.5 for every i --
    a class matched against itself is symmetric under any suit permutation
    that swaps hero's and villain's suits pairwise, which is always
    achievable between two combos of the *same* class; that symmetry is
    asserted below as a strong correctness check on the shape/weighting
    logic, not merely a nice-to-have."""
    n = len(labels)
    matrix = np.full((n, n), np.nan, dtype=np.float64)
    pairs = [(i, j) for i in range(n) for j in range(i, n)]
    if limit is not None:
        pairs = pairs[:limit]

    t0 = time.perf_counter()
    n_shapes_total = 0
    for done, (i, j) in enumerate(pairs, 1):
        shapes = shapes_for_pair(combo_groups[i], combo_groups[j])
        total_weight = sum(w for _, _, w in shapes)
        acc = 0.0
        for a, b, w in shapes:
            eq = equity_exact([list(a), list(b)], [], None)
            acc += float(eq[0]) * w
        eq_i = acc / total_weight
        matrix[i, j] = eq_i
        matrix[j, i] = 1.0 - eq_i
        n_shapes_total += len(shapes)

        if i == j:
            assert abs(eq_i - 0.5) < 1e-9, f"self-matchup {labels[i]} vs {labels[i]} != 0.5 (got {eq_i})"

        if done % progress_every == 0 or done == len(pairs):
            elapsed = time.perf_counter() - t0
            rate = done / elapsed
            eta_s = (len(pairs) - done) / rate if rate > 0 else float("nan")
            print(
                f"[{done}/{len(pairs)}] {labels[i]} vs {labels[j]}: {eq_i * 100:.3f}% "
                f"| {n_shapes_total} shapes so far, {elapsed:.0f}s elapsed, ETA {eta_s / 3600:.2f}h"
            )
    return matrix


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="build only the first N class pairs (for a quick check)")
    ap.add_argument("--out", type=str, default=OUT_PATH_DEFAULT)
    args = ap.parse_args()

    labels, combo_groups = hand_classes()
    print(f"{len(labels)} canonical starting-hand classes, {len(labels) * (len(labels) + 1) // 2} unordered pairs")

    matrix = build_matrix(labels, combo_groups, limit=args.limit)

    if args.limit is None:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        np.savez(args.out.replace(".npy", ".npz"), matrix=matrix, labels=np.array(labels))
        print(f"Saved to {args.out.replace('.npy', '.npz')}")
    else:
        print(f"--limit {args.limit} given: not saving (this was a correctness/ETA check, not a full build)")


if __name__ == "__main__":
    main()
