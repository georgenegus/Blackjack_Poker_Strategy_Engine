# Instructions for Working on This Project

## Before Making Any Changes

1. **Read the project overview** at `.agents/project-overview.md` to understand the system architecture.
2. **Read the coding standards** at `.agents/coding-standards.md` for conventions and correctness rules.
3. **Read the full build plan** at `markdowns/blackjack/blackjack_build_plan_v1.md` — phase order, file layout, and the reference strategy charts (Appendix A) that Phase 5 validates against.
4. **Check the Implementation Tracking table** in the build plan before starting a phase — do not start a phase whose dependencies are still `[ ]` Pending.

## Critical Rules

### RuleSet Is the Single Source of Truth (HIGHEST PRIORITY)

Every EV, every strategy decision, every house-edge figure is a function of a `RuleSet` (`src/engine/rules.py`): deck count, `dealer_hits_soft_17`, `double_after_split`, `surrender`, `blackjack_payout`, `resplit_to`, `resplit_aces`, `dealer_peeks`, `penetration`. Never hardcode "6 decks", "S17", or "3:2" anywhere outside a `RuleSet` default. A new ruleset (e.g. adding single-deck) must work by constructing a different `RuleSet`, not by branching on a format string scattered through the codebase.

### The Solver Is the Source of Truth, Not Published Charts

Published basic-strategy charts (encoded in Appendix A of the build plan) are a **known-answer test**, not the implementation. If the solver disagrees with a published chart, treat the solver as wrong until Phase 5's cell-for-cell comparison and house-edge simulation prove otherwise — never patch the grid to match a chart without finding the underlying solver bug.

### Peek Conditioning (the single most common solver bug)

When `rules.dealer_peeks` is true and the dealer's upcard is a Ten or Ace, the dealer has already checked for blackjack before the player acts. The hole-card distribution used everywhere downstream of that point must be conditioned on "dealer does not have blackjack" — renormalise after zeroing the Ace (ten up) or the Tens (Ace up). Omitting this produces a grid that is *almost* right (it typically only flips 16 vs 10 and 12 vs 4), which is exactly why it survives casual review. See `src/strategy/dealer_probs.py` (Phase 3) and the Phase 5 validation gate.

### No Bare Point Estimates from Monte Carlo

Every simulated figure (house edge, edge-vs-true-count slope, variance, risk of ruin) must be reported with its standard error or confidence interval — in test output, in the UI, and in documentation. Blackjack's edges are ~1% with per-hand SD ~1.15–1.3, so distinguishing real effects from Monte Carlo noise requires stating the uncertainty every time.

### Cache Validity Has No Grandfather Clause

T20's `Win_Probability_Model` repo had a costly bug: a pre-existing cache file with no manifest entry was trusted blindly rather than rebuilt, letting a cache silently drift out of sync with the code that produced it. This project's cache manager (`src/utils/cache_manager.py`, ported in Phase 4) must not repeat that — every cached grid/index file carries `{"solver_hash": ..., "ruleset": {...}}` and is rebuilt on any mismatch, including files that predate the manifest.

## Running the Project

```bash
py main.py --decks 6 --s17 --das --surrender late --print-grid    # Phase 4 — CLI grid printout
py -m pytest tests/ --ignore=tests/regression_test.py -q           # full unit test suite
py tests/regression_test.py --fast                                 # Phase 12 — the gate, CI mode (~1 min)
py tests/regression_test.py                                        # Phase 12 — the gate, full mode (recomputes exact house edge for all 4 anchors + MC sanity, several minutes)
py app.py                                                           # Phase 10/11 — serves the app + API on http://127.0.0.1:5000
```

## Common Pitfalls

1. **Building Phase 6+ before Phase 5 passes**: counting, indices, staking, and the UI all consume solver output. An unvalidated solver corrupts everything downstream silently — see the build plan's `[!CAUTION]` after Phase 5.
2. **Split EV treated as fully independent hands**: `2 × one_hand_EV` is the standard approximation used by every published chart (the two hands actually share a depleted shoe) — required to match Appendix A, not a bug to "fix".
3. **True-count rounding inconsistency**: use `"floor"` for betting decisions (conservative) and `"nearest"` for playing decisions (Phase 6) — mixing these produces numbers that look plausible but don't match any published reference.
4. **Unbounded Monte Carlo runs**: the dev machine has 7.7GB RAM (see Coding Standards). Standalone solver/simulation scripts need an `if __name__ == "__main__":` guard, and `/api/simulate` (Phase 10) must cap hands per request.
5. **Re-deriving count indices from a different composition-from-count mapping than the one documented** in Coding Standards — this is the #1 cause of index tables disagreeing with published ones by more than the expected ±1 tolerance.

## Documentation Locations

| Document | Path | Purpose |
|----------|------|---------|
| Build Plan | `markdowns/blackjack/blackjack_build_plan_v1.md` | Full phased plan, file structure, reference charts, risk assessment |
| This File | `.agents/instructions.md` | Working instructions for the AI agent |
| Project Overview | `.agents/project-overview.md` | Quick reference for architecture, file locations, current baselines |
| Coding Standards | `.agents/coding-standards.md` | Code conventions and correctness/data-integrity rules |

---

## Poker Area

A second, strictly additive engine lives under `src/poker/`, `data/poker/`, `tests/poker/`, `scripts/poker/`, following `markdowns/poker/poker_build_plan_v1.md`. Before touching any of it, read that plan (its own instructions-equivalent content lives in three new skills under `.agents/skills/poker_*`, not duplicated here) plus:

1. `.agents/skills/poker_evaluator_conventions/SKILL.md` — hand evaluator, equity engine, card/board encoding
2. `.agents/skills/poker_range_conventions/SKILL.md` — the 169-grid notation, combo weights, card removal
3. `.agents/skills/poker_solver_conventions/SKILL.md` — `GameSpec`, CFR, exploitability, push/fold, ICM

**The two headline rules**, the poker area's equivalent of this file's blackjack rules above:

- Every equity, EV, frequency, and exploitability figure is a function of an explicit `(GameSpec, Range)` pair (`src/poker/spec.py`) — never a hardcoded stack depth, rake, or bet-size grid. `GameSpec` plays exactly the role `RuleSet` plays for blackjack.
- A solved strategy without a measured exploitability recorded alongside it is not a result. Name the field `abstraction_exploitability_mbb`, never bare "exploitability" — it is measured inside the card/bet abstraction, not at a real table.

**Non-destructive boundary.** Poker work must never modify `src/engine/`, `src/strategy/`, `src/counting/`, `src/simulation/`, `src/bankroll/`, or `tests/regression_test.py` — the blackjack engine stays frozen behind its own `data/baselines/`. The only permitted edit to an existing file outside `.agents/`/`CLAUDE.md` is `app.py`, which gains exactly one import and one `register_blueprint()` call for the poker Flask Blueprint (`src/poker/api.py`). Run `py tests/regression_test.py --fast` after every poker-area change, not just at the end — a poker bug must never be mistaken for (or mask) a blackjack regression.

**Running the poker engine** (as phases land — see the build plan's tracking table for what's implemented so far):

```bash
py -m pytest tests/poker/ --ignore=tests/poker/regression_test.py -q   # poker unit tests
py tests/poker/regression_test.py --fast                                # poker gate, CI mode
py tests/regression_test.py --fast                                      # blackjack gate — must still pass
```
