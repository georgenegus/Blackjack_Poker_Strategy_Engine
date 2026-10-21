"""Phase 12: THE regression gate -- one command that checks every artifact
this repo actually ships against a fresh recomputation, and either prints
ALL BASELINES PASS or names exactly what moved.

Not a pytest module (like test_house_edge.py, which this script reuses):
most of what it checks isn't "does this function return X" but "does the
artifact this repo COMMITS still match what re-deriving it produces right
now" -- a question pytest's per-test model doesn't fit as naturally as a
single ordered report.

Four checks, in order, each cheap enough for --fast/CI except where noted:
  1. Grid cache freshness (are the committed data/strategy/*.json files still
     valid for the current solver source, or would loading them silently
     trigger a full rebuild?) + the Appendix A cell-for-cell match Phase 5
     already built (reused here, not duplicated).
  2. House edge: a fresh exact_house_edge() recompute vs the locked
     data/baselines/house_edge_baseline.json (deterministic, so any drift at
     all is real) -- plus, outside --fast, the same Monte Carlo secondary
     sanity check test_house_edge.py itself runs.
  3. Count-indexed deviations vs the Illustrious 18 / Fab 4 (fast -- reuses
     Phase 7's own published-value fixtures) for the one ruleset+system
     combo that actually has a pre-built index cache shipped
     (6d-s17-das-ls-p75 / Hi-Lo -- see app.py's own Phase 10 note that this
     is the only one of 32 combos ever pre-built).
  4. Edge model: sanity-checks the locked edge_model_baseline.json loads and
     has a sane (positive) slope, plus, outside --fast, a moderate-hand
     battery cross-check against it (not a full 20M-hand refit -- that stays
     scripts/run_sim_battery.py's job, see the note below).

    py tests/regression_test.py                        # full gate
    py tests/regression_test.py --fast                  # CI mode
    py tests/regression_test.py --generate               # re-lock house_edge_baseline.json (all 4 anchors)
    py tests/regression_test.py --generate-ruleset 6      # re-lock one deck count's entry only

data/baselines/edge_model_baseline.json is a separate, far more expensive
artifact (a 20M-hand battery, ~70 minutes -- see Phase 8's tracking-table
entry) owned by `scripts/run_sim_battery.py --generate`, not by this script;
re-lock it there, not here.
"""

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

# Needed when run as a direct script (py tests/regression_test.py) -- Python only
# puts the invoked script's own directory (tests/) on sys.path, not the project
# root, which `import tests.test_strategy_grid` etc. below both need.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from src.engine.rules import RuleSet, shipped_rulesets
from src.strategy import grid_builder
from src.strategy.exact_edge import exact_house_edge
from src.utils.cache_manager import source_hash

HOUSE_EDGE_BASELINE_PATH = Path("data/baselines/house_edge_baseline.json")
DEVIATION_RULESET = RuleSet(num_decks=6, dealer_hits_soft_17=False, double_after_split=True, surrender="late")
EDGE_MODEL_RULESET_KEY = "6d-s17-das-ls-p75"
EDGE_MODEL_SYSTEM_SLUG = "hi-lo"
MC_SE_MULTIPLIER = 4  # matches test_house_edge.py's own convention


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


# --- Check 1: grid cache freshness + Appendix A ------------------------------------------

def check_grid_cache_freshness() -> CheckResult:
    """Reads each committed data/strategy/*.json file directly (never calls
    solve_grid_cached here -- that would silently rebuild a stale one rather
    than reporting it) and compares its recorded _source_hash against the
    CURRENT solver source. A mismatch means someone edited ev_solver.py /
    dealer_probs.py / grid_builder.py without re-running
    scripts/build_all_grids.py before committing -- exactly the drift
    .agents/coding-standards.md's "Cache Validity Has No Grandfather Clause"
    rule exists to catch."""
    current_hash = source_hash(*grid_builder._SOLVER_SOURCE_FILES)
    stale, missing = [], []
    total = 0
    for rules in shipped_rulesets():
        total += 1
        path = grid_builder.DEFAULT_CACHE_DIR / f"{rules.key()}.json"
        if not path.exists():
            missing.append(rules.key())
            continue
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            stale.append(rules.key())
            continue
        if cached.get("_source_hash") != current_hash:
            stale.append(rules.key())

    ok = not stale and not missing
    fresh = total - len(stale) - len(missing)
    detail = f"{fresh}/{total} fresh"
    if missing:
        detail += f"; missing (run scripts/build_all_grids.py): {missing}"
    if stale:
        detail += f"; stale (solver source changed since these were cached): {stale}"
    return CheckResult(f"grid cache freshness ({total} shipped rulesets)", ok, detail)


def check_grid_vs_appendix_a() -> CheckResult:
    from tests.test_strategy_grid import test_multi_deck_grids_match_appendix_a
    try:
        test_multi_deck_grids_match_appendix_a()
        return CheckResult("grid vs Appendix A (4/6/8D x S17/H17)", True, "all cells match published chart (or a documented near-miss)")
    except AssertionError as e:
        return CheckResult("grid vs Appendix A (4/6/8D x S17/H17)", False, str(e))


# --- Check 2: house edge -------------------------------------------------------------------

def check_house_edge(fast: bool, mc_hands: int) -> List[CheckResult]:
    from src.simulation.simulator import simulate_house_edge
    from src.strategy.basic_strategy import strategy_decide_fn
    from tests.test_house_edge import ruleset_for_decks

    results = []
    if not HOUSE_EDGE_BASELINE_PATH.exists():
        return [CheckResult("house edge baseline", False, f"missing {HOUSE_EDGE_BASELINE_PATH} -- run --generate")]
    baseline = json.loads(HOUSE_EDGE_BASELINE_PATH.read_text(encoding="utf-8"))
    deck_counts = sorted(int(k) for k in baseline)

    # exact_house_edge() is deterministic but NOT cheap for high deck counts (8D is
    # ~16 minutes of pure-Python recursion per Phase 5's own timing) -- --fast only
    # recomputes the cheapest deck count as a live canary and trusts the locked
    # file's own recorded pass/fail for the rest, named explicitly as unverified
    # this run rather than silently skipped.
    recompute_decks = {min(deck_counts)} if fast and deck_counts else set(deck_counts)

    for decks in deck_counts:
        deck_str = str(decks)
        locked = baseline[deck_str]
        if decks not in recompute_decks:
            results.append(CheckResult(
                f"{decks}D exact edge vs locked baseline", bool(locked.get("primary_pass", True)),
                f"NOT recomputed in --fast; trusting locked record (primary_pass={locked.get('primary_pass')}) -- run without --fast to verify"
            ))
            continue

        rules = ruleset_for_decks(decks)
        fresh_exact = exact_house_edge(rules)
        gap = fresh_exact - locked["exact_edge"]
        # Deterministic, zero-noise computation -- any drift at all vs the locked
        # figure is a real change in the solver's output, not sampling noise, so
        # this can be far tighter than Phase 5's own +/-0.02% correctness gate.
        ok = abs(gap) <= 1e-6
        results.append(CheckResult(
            f"{decks}D exact edge vs locked baseline", ok,
            f"fresh={fresh_exact:.6%} locked={locked['exact_edge']:.6%} gap={gap:+.2e}"
        ))

        if not fast:
            mean, se = simulate_house_edge(rules, strategy_decide_fn, n_hands=mc_hands, bet=1.0, fresh_shoe_per_hand=True)
            simulated = -mean
            tol = max(0.0002, MC_SE_MULTIPLIER * se)
            gap2 = simulated - fresh_exact
            ok2 = abs(gap2) <= tol
            results.append(CheckResult(
                f"{decks}D Monte Carlo sanity ({mc_hands:,} hands) vs exact", ok2,
                f"simulated={simulated:.4%}+/-{se:.4%} exact={fresh_exact:.4%} gap={gap2:+.4%} tol={tol:.4%}"
            ))
    return results


# --- Check 3: count-indexed deviations --------------------------------------------------

def check_deviation_indices() -> List[CheckResult]:
    from src.counting.systems import HI_LO
    from src.strategy.index_builder import FAB_4, ILLUSTRIOUS_18, insurance_index, solve_indices_cached
    from tests.test_deviations import FAB_4_PUBLISHED, ILLUSTRIOUS_18_PUBLISHED, TOLERANCE

    named = solve_indices_cached(HI_LO, num_decks=6, rules=DEVIATION_RULESET)

    def _derived(idx):
        return idx.positive_index if idx.positive_index is not None else idx.negative_index

    results = []
    failures = []
    for _kind, _upcard, cell_key in ILLUSTRIOUS_18:
        idx = named[f"{cell_key}:primary"]
        derived = _derived(idx)
        published = ILLUSTRIOUS_18_PUBLISHED[cell_key]
        if derived is None or abs(derived - published) > TOLERANCE:
            failures.append(f"{cell_key}: derived={derived} published={published}")
    results.append(CheckResult(
        "Illustrious 18 indices (Hi-Lo, 6d-s17-das-ls-p75)", not failures,
        "all within tolerance" if not failures else "; ".join(failures)
    ))

    failures = []
    for _kind, _upcard, cell_key in FAB_4:
        idx = named[f"{cell_key}:surrender"]
        derived = _derived(idx)
        published = FAB_4_PUBLISHED[cell_key]
        if derived is None or abs(derived - published) > TOLERANCE:
            failures.append(f"{cell_key}: derived={derived} published={published}")
    results.append(CheckResult(
        "Fab 4 surrender indices (Hi-Lo, 6d-s17-das-ls-p75)", not failures,
        "all within tolerance" if not failures else "; ".join(failures)
    ))

    ins = insurance_index(HI_LO, num_decks=6)
    ok = ins is not None and abs(ins - 3) <= TOLERANCE
    results.append(CheckResult("insurance index (Hi-Lo, 6 decks)", ok, f"derived={ins} published=3"))
    return results


# --- Check 4: edge model -------------------------------------------------------------------

def check_edge_model(fast: bool, mc_hands: int) -> List[CheckResult]:
    from src.counting.edge_model import keyed_baseline_path, load_baseline, predict_edge
    from src.counting.systems import HI_LO
    from src.simulation.simulator import run_battery

    path = keyed_baseline_path(EDGE_MODEL_RULESET_KEY, EDGE_MODEL_SYSTEM_SLUG)
    if not path.exists():
        return [CheckResult("edge model baseline present", False, f"missing {path} -- run scripts/run_sim_battery.py --generate")]

    model = load_baseline(path=path)
    results = [CheckResult(
        "edge model baseline loads", True,
        f"slope={model.slope:+.5f}/TC intercept={model.intercept:+.5f} R^2={model.r_squared:.4f} n_hands={model.n_hands:,}"
    )]
    results.append(CheckResult("edge model slope is positive", model.slope > 0, f"slope={model.slope:+.5f}"))

    if not fast:
        rules = RuleSet(num_decks=6, surrender="late")
        result = run_battery(rules, HI_LO, n_hands=mc_hands, use_deviations=True, rng=np.random.default_rng(12345))
        checked, failures = 0, []
        for tc, bucket in sorted(result.by_true_count.items()):
            if bucket.n < 300 or not (-6 <= tc <= 6):
                continue  # too few samples to trust, or outside the model's own trusted range
            predicted = predict_edge(model, tc)
            # Generous floor beyond pure SE: even the locked 20M-hand fit's own R^2 (~0.98)
            # implies real per-bucket scatter around the line, not just sampling noise -- this
            # is a sanity cross-check against a moderate-N battery, not a refit.
            tol = max(0.015, MC_SE_MULTIPLIER * bucket.stderr)
            gap = bucket.mean - predicted
            checked += 1
            if abs(gap) > tol:
                failures.append(f"TC{tc:+d}: battery={bucket.mean:+.4f} predicted={predicted:+.4f} gap={gap:+.4f} tol={tol:.4f}")
        results.append(CheckResult(
            f"edge model vs fresh {mc_hands:,}-hand battery", checked > 0 and not failures,
            (f"{checked} true-count buckets checked" if not failures else "; ".join(failures))
        ))
    return results


# --- --generate ------------------------------------------------------------------------

def _generate(deck_arg: str, mc_hands: int) -> None:
    from tests.test_house_edge import PUBLISHED_HOUSE_EDGE, run_check

    existing = {}
    if HOUSE_EDGE_BASELINE_PATH.exists():
        existing = json.loads(HOUSE_EDGE_BASELINE_PATH.read_text(encoding="utf-8"))

    if deck_arg is None:
        decks_to_run = sorted(PUBLISHED_HOUSE_EDGE)
    else:
        m = re.match(r"(\d+)", deck_arg)
        decks = int(m.group(1)) if m else None
        if decks not in PUBLISHED_HOUSE_EDGE:
            print(f"Unknown deck count {deck_arg!r}; known: {sorted(PUBLISHED_HOUSE_EDGE)}")
            sys.exit(1)
        decks_to_run = [decks]

    for d in decks_to_run:
        print(f"Re-locking {d}D ({mc_hands:,} hands)...")
        existing[str(d)] = run_check(d, mc_hands)

    HOUSE_EDGE_BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOUSE_EDGE_BASELINE_PATH.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Locked -> {HOUSE_EDGE_BASELINE_PATH}")
    print(
        "Note: data/baselines/edge_model_baseline.json is a separate, ~70-minute artifact "
        "owned by scripts/run_sim_battery.py --generate, not this script."
    )


# --- report + entry point -------------------------------------------------------------------

def _print_report(results: List[CheckResult], elapsed: float, fast: bool) -> bool:
    name_width = max(len(r.name) for r in results)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.name:<{name_width}}  {r.detail}")

    n_pass = sum(r.passed for r in results)
    mode = " (fast mode)" if fast else ""
    print(f"\n{n_pass}/{len(results)} checks passed{mode}  ({elapsed:.1f}s)")
    all_pass = n_pass == len(results)
    print("ALL BASELINES PASS" if all_pass else "SOME CHECKS FAILED -- see [FAIL] lines above")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 12 regression gate")
    parser.add_argument("--fast", action="store_true", help="CI mode: skip the slow Monte Carlo sanity checks")
    parser.add_argument("--generate", action="store_true", help="Re-lock house_edge_baseline.json (all 4 anchors)")
    parser.add_argument("--generate-ruleset", metavar="DECKS", help="Re-lock one deck count's house-edge entry only (2, 4, 6, or 8)")
    parser.add_argument("--mc-hands", type=int, default=2_000_000, help="Hands for the house-edge secondary MC check (full mode)")
    parser.add_argument("--edge-model-hands", type=int, default=300_000, help="Hands for the edge-model sanity battery (full mode)")
    args = parser.parse_args()

    if args.generate or args.generate_ruleset:
        _generate(args.generate_ruleset, args.mc_hands)
        return

    t0 = time.perf_counter()
    results: List[CheckResult] = []
    results.append(check_grid_cache_freshness())
    results.append(check_grid_vs_appendix_a())
    results.extend(check_house_edge(args.fast, args.mc_hands))
    results.extend(check_deviation_indices())
    results.extend(check_edge_model(args.fast, args.edge_model_hands))

    all_pass = _print_report(results, time.perf_counter() - t0, args.fast)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
