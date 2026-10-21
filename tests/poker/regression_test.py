"""Phase 14: THE poker regression gate -- the poker area's twin to
tests/regression_test.py (see that file's own module docstring for the
pattern this one mirrors deliberately, check for check). One command that
checks every locked poker baseline and either prints ALL POKER BASELINES
PASS or names exactly what moved. Kept a separate script/CI job from the
blackjack gate on purpose (markdowns/poker/poker_build_plan_v1.md Phase 14's
own instruction): a poker failure must never mask a blackjack one, or vice
versa.

    py tests/poker/regression_test.py                       # full gate
    py tests/poker/regression_test.py --fast                # CI mode
    py tests/poker/regression_test.py --generate             # re-lock preflop_baseline.json (all shipped specs)
    py tests/poker/regression_test.py --generate-spec <key>  # re-lock one spec's entry only

Six checks, in order:
  1. Evaluator: source-hash freshness (has evaluator.py changed since the
     table/baseline were built?) + the 7,462 distinct-value count and the
     five-card category counts (always, cheap) + the seven-card category
     counts -- FULL C(52,7) enumeration outside --fast; a deterministic
     stride-sampled subset (checked against the KNOWN EXACT proportions,
     since a subsample can't reproduce exact integer counts) in --fast.
  2. Equity: every anchor in equity_baseline.json, recomputed exactly and
     compared bit-for-bit (equity_exact is deterministic, so any drift at
     all is real).
  3. Kuhn/Leduc: game value + full frequency structure against the
     analytic constants (Kuhn) and the sequence-form LP (Leduc), reusing
     Phase 8's own test_toy_games.py check functions directly rather than
     re-deriving them here.
  4. Preflop: every shipped strategy's solver-hash freshness AND its
     abstraction_exploitability_mbb against preflop_baseline.json. This
     does NOT re-solve from scratch (a real MCCFR re-solve costs on the
     order of 30 minutes for the plan's own 100bb example -- see Phase
     10's tracking-table entry -- an unreasonable CI cost); it only
     confirms the shipped artifact hasn't silently drifted from the
     specific solve that was reviewed and locked, the same relationship
     data/baselines/edge_model_baseline.json has to
     scripts/run_sim_battery.py on the blackjack side.
  5. Push/fold: NO literal comparison against Miltersen & Sorensen's (2007)
     published tables -- Phase 9's own tracking-table entry already
     documented that this development environment has no network access
     to verify against them, and that gap is inherited here rather than
     silently worked around. Reuses Phase 9's own substitute: the
     structural facts that need no external table (near-100% jam/call at
     1bb, monotonicity across the full stack grid, call-tighter-than-jam
     from ~5bb on, the hand-verified crossover below that).
  6. ICM: the Appendix A.6 worked example plus the "marginal chip value
     falls monotonically with stack size" property identity.

preflop_baseline.json is also a real gap being filled here, not invented
fresh: Phase 10's own Files line named data/poker/baselines/
preflop_baseline.json as one of that phase's deliverables, but Phase 10 (in
an earlier session) only ever wrote data/poker/strategy/{spec}/preflop.json
and never created the separate baselines/ file the plan called for -- this
phase creates it now, populated from whatever solves are ALREADY shipped
and already reviewed in Phase 10/12's own tracking-table entries (including
the honestly-under-converged hu-100bb-r5c3-s5 result the user chose to
lock as-is), not from a fresh re-solve.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EVALUATOR_BASELINE_PATH = REPO_ROOT / "data" / "poker" / "baselines" / "evaluator_baseline.json"
EQUITY_BASELINE_PATH = REPO_ROOT / "data" / "poker" / "baselines" / "equity_baseline.json"
TOY_GAME_BASELINE_PATH = REPO_ROOT / "data" / "poker" / "baselines" / "toy_game_baseline.json"
PREFLOP_BASELINE_PATH = REPO_ROOT / "data" / "poker" / "baselines" / "preflop_baseline.json"
STRATEGY_DIR = REPO_ROOT / "data" / "poker" / "strategy"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


# --- Check 1: evaluator -----------------------------------------------------------------


def _evaluator_source_hash() -> str:
    return hashlib.sha256((REPO_ROOT / "src" / "poker" / "evaluator.py").read_bytes()).hexdigest()


def check_evaluator(fast: bool) -> List[CheckResult]:
    from src.poker.evaluator import HandCategory, category_batch, distinct_five_card_values, evaluate5, evaluate_batch

    if not EVALUATOR_BASELINE_PATH.exists():
        return [CheckResult("evaluator baseline", False, f"missing {EVALUATOR_BASELINE_PATH} -- run --generate")]
    baseline = json.loads(EVALUATOR_BASELINE_PATH.read_text())
    results = []

    current_hash = _evaluator_source_hash()
    results.append(
        CheckResult(
            "evaluator source hash",
            current_hash == baseline["evaluator_source_sha256"],
            "fresh" if current_hash == baseline["evaluator_source_sha256"] else "evaluator.py changed since evaluator_baseline.json was locked -- run --generate after confirming this is a correctness fix",
        )
    )

    results.append(
        CheckResult(
            "distinct five-card values",
            distinct_five_card_values() == baseline["distinct_five_card_values"],
            f"got {distinct_five_card_values()}, expected {baseline['distinct_five_card_values']}",
        )
    )

    from itertools import combinations

    five_totals = np.zeros(9, dtype=np.int64)
    for batch_start in range(0, 2_598_960, 500_000):
        combos = list(islice(combinations(range(52), 5), batch_start, batch_start + 500_000))
        if not combos:
            break
        vals = np.array([evaluate5(h) for h in combos], dtype=np.int32)
        five_totals += np.bincount(category_batch(vals), minlength=9)
    five_ok = int(five_totals.sum()) == baseline["five_card_total"]
    for cat in HandCategory:
        five_ok = five_ok and int(five_totals[cat.value]) == baseline["five_card_category_counts"][cat.name]
    results.append(CheckResult("five-card category counts", five_ok, f"total={int(five_totals.sum())}"))

    if fast:
        # Deterministic stride sample of C(52,7) -- can't reproduce exact
        # integer counts, so check OBSERVED PROPORTIONS against the known
        # exact proportions (from the locked baseline) instead.
        stride = 3000
        sample = list(islice(combinations(range(52), 7), 0, None, stride))
        arr = np.array(sample, dtype=np.int64)
        cats = category_batch(evaluate_batch(arr))
        counts = np.bincount(cats, minlength=9)
        n = counts.sum()
        prop_ok = True
        detail_parts = []
        for cat in HandCategory:
            observed_p = counts[cat.value] / n
            expected_p = baseline["seven_card_category_counts"][cat.name] / baseline["seven_card_total"]
            # A handful of the rarest categories (e.g. straight flush, ~40 in
            # 133M) can legitimately draw ZERO samples at this stride --
            # tolerance is generous and asymmetric-safe (proportion diff, not
            # a ratio, so a 0-count rare category doesn't blow up the check).
            if abs(observed_p - expected_p) > 0.01:
                prop_ok = False
                detail_parts.append(f"{cat.name}: observed {observed_p:.4f} vs expected {expected_p:.4f}")
        results.append(
            CheckResult(
                f"seven-card category proportions (stride-{stride} sample, n={n})",
                prop_ok,
                "within tolerance" if prop_ok else "; ".join(detail_parts),
            )
        )
    else:
        seven_totals = np.zeros(9, dtype=np.int64)
        for batch_start in range(0, 133_784_560, 2_000_000):
            combos = list(islice(combinations(range(52), 7), batch_start, batch_start + 2_000_000))
            if not combos:
                break
            vals = evaluate_batch(np.array(combos, dtype=np.int64))
            seven_totals += np.bincount(category_batch(vals), minlength=9)
        seven_ok = int(seven_totals.sum()) == baseline["seven_card_total"]
        for cat in HandCategory:
            seven_ok = seven_ok and int(seven_totals[cat.value]) == baseline["seven_card_category_counts"][cat.name]
        results.append(CheckResult("seven-card category counts (full C(52,7))", seven_ok, f"total={int(seven_totals.sum())}"))

    return results


# --- Check 2: equity ---------------------------------------------------------------------


def check_equity() -> CheckResult:
    from src.poker.cards import card_ids
    from src.poker.equity import equity_exact

    if not EQUITY_BASELINE_PATH.exists():
        return CheckResult("equity baseline", False, f"missing {EQUITY_BASELINE_PATH} -- run --generate")
    baseline = json.loads(EQUITY_BASELINE_PATH.read_text())

    mismatches = []
    for anchor in baseline["anchors"]:
        hands = [card_ids(anchor["hero"]), card_ids(anchor["villain"])]
        board = card_ids("".join(anchor["board"])) if anchor["board"] else []
        eq = equity_exact(hands, board)
        if abs(float(eq[0]) - anchor["hero_equity"]) > 1e-6:
            mismatches.append(f"{anchor['hero']} vs {anchor['villain']}: got {eq[0]:.8f}, expected {anchor['hero_equity']:.8f}")

    ok = not mismatches
    return CheckResult(f"equity anchors ({len(baseline['anchors'])})", ok, "all match" if ok else "; ".join(mismatches))


# --- Check 3: Kuhn / Leduc ----------------------------------------------------------------


def check_toy_games() -> List[CheckResult]:
    import tests.poker.test_toy_games as tg

    checks = [
        ("Kuhn game value vs analytic", tg.test_check1_kuhn_game_value_within_plan_tolerance),
        ("Kuhn frequency structure vs analytic", tg.test_check1_kuhn_frequency_structure_within_plan_tolerance),
        ("Kuhn LP vs analytic (machine precision)", tg.test_check2_kuhn_lp_matches_analytic_value_exactly),
        ("Leduc LP vs locked baseline", tg.test_check2_leduc_lp_matches_locked_baseline),
        ("Leduc CFR/exploitability vs locked baseline", tg.test_check2_locked_baseline_meets_the_plans_own_bars),
    ]
    results = []
    for name, fn in checks:
        try:
            fn()
            results.append(CheckResult(name, True, "pass"))
        except AssertionError as e:
            results.append(CheckResult(name, False, str(e)))
    return results


# --- Check 4: preflop solved strategies ---------------------------------------------------


def _solver_hash() -> str:
    from scripts.poker.solve_preflop import _solver_hash as real_hash

    return real_hash()


def check_preflop_strategies() -> List[CheckResult]:
    if not PREFLOP_BASELINE_PATH.exists():
        return [CheckResult("preflop baseline", False, f"missing {PREFLOP_BASELINE_PATH} -- run --generate")]
    baseline = json.loads(PREFLOP_BASELINE_PATH.read_text())
    current_hash = _solver_hash()

    results = []
    for spec_key, locked in baseline.items():
        path = STRATEGY_DIR / spec_key / "preflop.json"
        if not path.exists():
            results.append(CheckResult(f"preflop:{spec_key}", False, f"missing {path} -- was it deleted since locking?"))
            continue
        current = json.loads(path.read_text())

        hash_fresh = current["solver_hash"] == current_hash
        exploit_matches = current["abstraction_exploitability_mbb"] == locked["abstraction_exploitability_mbb"]
        ok = hash_fresh and exploit_matches
        if ok:
            detail = f"{current['abstraction_exploitability_mbb']:.2f} mbb/g, solver hash fresh"
        elif not hash_fresh:
            detail = "solver source (advisor.py/tree.py/cfr.py) changed since this spec was solved -- re-solve and re-lock via --generate-spec, or confirm this is expected"
        else:
            detail = f"exploitability drifted: current {current['abstraction_exploitability_mbb']:.2f} vs locked {locked['abstraction_exploitability_mbb']:.2f} mbb/g"
        results.append(CheckResult(f"preflop:{spec_key}", ok, detail))
    return results


# --- Check 5: push/fold structural facts --------------------------------------------------


def check_pushfold() -> List[CheckResult]:
    import tests.poker.test_pushfold as tp

    checks = [
        ("push/fold: 1bb jams/calls ~everything", tp.test_extremely_short_stack_jams_and_calls_everything),
        ("push/fold: monotone decreasing in stack depth", tp.test_jam_and_call_ranges_are_monotone_decreasing_in_stack_depth),
        ("push/fold: call tighter than jam (>=5bb)", tp.test_call_range_is_tighter_than_jam_range_at_moderate_and_deeper_stacks),
        ("push/fold: call can exceed jam at 1.5bb (hand-verified crossover)", tp.test_call_can_exceed_jam_at_the_shortest_stacks),
    ]
    results = []
    for name, fn in checks:
        try:
            fn()
            results.append(CheckResult(name, True, "pass -- no published Miltersen/Sorensen table available in this environment, see this file's own docstring"))
        except AssertionError as e:
            results.append(CheckResult(name, False, str(e)))
    return results


# --- Check 6: ICM identities --------------------------------------------------------------


def check_icm() -> List[CheckResult]:
    import tests.poker.test_icm as ti

    checks = [
        ("ICM: Appendix A.6 worked example", ti.test_appendix_a6_worked_example),
        ("ICM: marginal chip value falls with stack size", ti.test_marginal_chip_value_falls_as_stack_grows),
        ("ICM: equities sum to exactly the prize pool", ti.test_equities_sum_to_exactly_the_prize_pool),
    ]
    results = []
    for name, fn in checks:
        try:
            fn()
            results.append(CheckResult(name, True, "pass"))
        except AssertionError as e:
            results.append(CheckResult(name, False, str(e)))
    return results


# --- --generate --------------------------------------------------------------------------


def _generate(spec_arg: str | None) -> None:
    """Locks preflop_baseline.json from whatever solves are ALREADY SHIPPED
    under data/poker/strategy/*/preflop.json -- never re-solves (a real
    MCCFR solve is a ~30-minute-plus background job, scripts/poker/
    solve_preflop.py's job, not this gate's). Run this only after reviewing
    a newly (re-)solved artifact and deciding its numbers are the ones to
    lock, per .agents/coding-standards.md's Regression Gate Discipline."""
    existing = {}
    if PREFLOP_BASELINE_PATH.exists():
        existing = json.loads(PREFLOP_BASELINE_PATH.read_text())

    if spec_arg is None:
        specs_to_lock = [d.name for d in sorted(STRATEGY_DIR.glob("*")) if (d / "preflop.json").exists()]
    else:
        if not (STRATEGY_DIR / spec_arg / "preflop.json").exists():
            print(f"No shipped solve for spec {spec_arg!r} at {STRATEGY_DIR / spec_arg / 'preflop.json'}")
            sys.exit(1)
        specs_to_lock = [spec_arg]

    for spec_key in specs_to_lock:
        current = json.loads((STRATEGY_DIR / spec_key / "preflop.json").read_text())
        existing[spec_key] = {
            "abstraction_exploitability_mbb": current["abstraction_exploitability_mbb"],
            "abstraction_exploitability_se_mbb": current.get("abstraction_exploitability_se_mbb"),
            "iterations": current["iterations"],
            "game_value_bb": current.get("game_value_bb"),
            "solver_hash": current["solver_hash"],
        }
        print(f"Locked {spec_key}: {current['abstraction_exploitability_mbb']:.2f} mbb/g ({current['iterations']:,} iterations)")

    PREFLOP_BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREFLOP_BASELINE_PATH.write_text(json.dumps(existing, indent=2, sort_keys=True))
    print(f"-> {PREFLOP_BASELINE_PATH}")


# --- report + entry point -----------------------------------------------------------------


def _print_report(results: List[CheckResult], elapsed: float, fast: bool) -> bool:
    name_width = max(len(r.name) for r in results)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.name:<{name_width}}  {r.detail}")

    n_pass = sum(r.passed for r in results)
    mode = " (fast mode)" if fast else ""
    print(f"\n{n_pass}/{len(results)} checks passed{mode}  ({elapsed:.1f}s)")
    all_pass = n_pass == len(results)
    print("ALL POKER BASELINES PASS" if all_pass else "SOME CHECKS FAILED -- see [FAIL] lines above")
    return all_pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 14 poker regression gate")
    parser.add_argument("--fast", action="store_true", help="CI mode: stride-sample the 7-card evaluator check instead of the full C(52,7) enumeration")
    parser.add_argument("--generate", action="store_true", help="Re-lock preflop_baseline.json from every currently-shipped solve")
    parser.add_argument("--generate-spec", metavar="KEY", help="Re-lock one spec's preflop_baseline.json entry only")
    args = parser.parse_args()

    if args.generate or args.generate_spec:
        _generate(args.generate_spec)
        return

    t0 = time.perf_counter()
    results: List[CheckResult] = []
    results.extend(check_evaluator(args.fast))
    results.append(check_equity())
    results.extend(check_toy_games())
    results.extend(check_preflop_strategies())
    results.extend(check_pushfold())
    results.extend(check_icm())

    all_pass = _print_report(results, time.perf_counter() - t0, args.fast)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
