# Coding Standards

## Language & Runtime

- **Python 3.14+** (Windows)
- Key dependencies: `flask`, `numpy`, `pandas`, `pytest` (core); `numba`, `scipy` (optional — add only if the cache-first solver approach proves too slow, see the build plan's Phase 3 notes)
- No virtual environment convention — packages are installed globally
- Dev machine has only **7.7GB RAM** — Monte Carlo batteries (Phase 8) and grid pre-solves (Phase 4) can OOM if run alongside other heavy processes. Standalone solver/simulation scripts need an `if __name__ == "__main__":` guard (Windows `spawn` will otherwise silently re-run the whole script multiple times in worker processes)

## Code Style

### General

- Use **type hints** for function signatures where practical
- Use **docstrings** for classes and public methods
- Use `# Comment` for inline explanations of non-obvious logic — prefer explaining *why*, not *what*
- Prefer **explicit over implicit** — avoid magic numbers without named constants or comments
- Keep functions focused on a single responsibility

### Naming Conventions

- Classes: `PascalCase` (e.g. `Shoe`, `Hand`, `RuleSet`, `EloEngine`-style single-responsibility classes)
- Functions/methods: `snake_case` (e.g. `dealer_distribution`, `kelly_fraction`, `solve_grid`)
- Private methods: prefix with `_` (e.g. `_extract_features_and_target`-style internal helpers)
- Constants: `UPPER_SNAKE_CASE` for true constants (`RANKS`, `HARD_VALUE`); rule-variant defaults live in `RuleSet`, never as scattered module-level constants
- Variables: `snake_case`, descriptive names (e.g. `decks_remaining`, `true_count`, `bust_prob`)

### File Organisation

- **Source code**: `src/` with subpackages `engine/` (game mechanics), `strategy/` (solver + grid + deviations), `counting/` (count systems + edge model), `bankroll/` (Kelly + risk), `simulation/` (Monte Carlo), `utils/` (cache manager)
- **Tests & validation**: `tests/` — `regression_test.py` is the regression gate against locked baselines, not a unit test; `test_*.py` files validate individual phases; `tests/one-time/` is gitignored ad-hoc experiments
- **Automation**: `scripts/` — `build_all_grids.py`, `build_all_indices.py`, `run_sim_battery.py`
- **Static web assets**: `static/` with `index.html`, `js/`, `css/`
- **Documentation**: `docs/` for system-level docs (Phase 12), `markdowns/blackjack/` for the build plan
- **Cached data**: `data/strategy/`, `data/indices/`, `data/baselines/` — committed (small, deterministic JSON); `data/sims/` — gitignored (large, regenerable Monte Carlo output)

## Correctness Rules

### RuleSet Is the Single Source of Truth

This is the single most important rule in the codebase, equivalent to T20's "no data leakage" rule:

1. Every EV, strategy decision, and house-edge figure is computed from an explicit `RuleSet` instance, never a hardcoded assumption about deck count, S17/H17, DAS, or payout.
2. `RuleSet.key()` produces a deterministic short hash (e.g. `6d-s17-das-ls-p75`) used as the filename for every cached grid/index and as the cache-manifest key.
3. A new rule variant is added by constructing a different `RuleSet`, never by branching on a format string scattered through `src/strategy/` or `src/simulation/`.
4. Format-specific behaviour (e.g. no-peek/European handling) is guarded with explicit `RuleSet` field checks (`if rules.dealer_peeks: ...`), never assumed.

### The 10-Bucket Rank Composition Is Canonical

Shoe composition is always represented as the 10-bucket vector `(n2, n3, ..., n9, nT, nA)`, with T/J/Q/K collapsed into a single `T` bucket. This collapse is required for the solver's memoisation to be tractable — do not expand it to 13 buckets. The one exception is Red Seven counting, which needs suit colour on the `7` rank specifically; `Card` retains suit for this reason, but `Hand`/`Shoe` composition logic still operates on the 10-bucket index.

### Peek Conditioning

When `rules.dealer_peeks` is true and the dealer shows a Ten or Ace, every downstream EV calculation must condition the hole-card distribution on "no dealer blackjack" (renormalise after removing the blackjack-completing rank). This is the most common blackjack-solver bug — see `.agents/instructions.md` for why it survives casual review, and `markdowns/blackjack/blackjack_build_plan_v1.md` Phase 3 for the implementation.

### Split EV Approximation

`ev_split = 2 × ev(one post-split hand, split card removed from shoe)` is the standard treatment (used by every published chart), not a strict independence assumption — the two hands actually draw from the same depleted shoe, and the resulting error (~0.01%) is required to match Appendix A of the build plan. Do not attempt to "fix" this into full joint enumeration.

### True-Count Rounding Convention

- **Betting decisions**: round `true_count` toward zero / floor (conservative — never overbets on a rounding artefact)
- **Playing decisions**: round `true_count` to nearest
- This split must be explicit in `src/counting/counter.py`, not implicit in caller code. Mixing conventions is the most common reason two "correct" implementations disagree with each other by ±1 index.

### Count-to-Composition Mapping (Phase 7)

Deriving a count index requires the inverse of "true count → implied shoe composition", which is mathematically underdetermined (a scalar can't uniquely determine a 10-dimensional vector). The standard, documented choice: distribute the count's implied surplus/deficit **proportionally within each tag group** (all `+1`-tagged ranks share the surplus proportionally; all `−1`-tagged ranks share the deficit; untagged ranks are left at their neutral proportion). Do not use a different mapping (e.g. concentrating the adjustment on a single rank) — it will produce indices that disagree with the Illustrious 18 by more than the expected ±1 tolerance, which Phase 7's test treats as a bug.

### No Bare Point Estimates from Monte Carlo

Every simulated figure — house edge, edge-vs-count slope, variance, risk of ruin, N₀ — is reported with its standard error or confidence interval, in test assertions, UI display, and documentation. See the build plan's Phase 8 `[!WARNING]`.

### Cache Management

- Caches are validated by a **content hash of the solver source `.py` files plus the `RuleSet`**, ported from T20's `src/utils/cache_manager.py` pattern.
- **No grandfather clause**: unlike T20's Elo-cache bug (a pre-existing cache with no manifest entry was trusted blindly), every cached grid/index file here must carry `{"solver_hash": ..., "ruleset": {...}}` and be rebuilt on any mismatch — including files that predate the manifest.
- Cache files: `data/strategy/{ruleset_key}.json`, `data/indices/{ruleset_key}__{system}.json`.

### Regression Gate Discipline

Once Phase 5 locks `data/baselines/strategy_baseline.json` and `house_edge_baseline.json`, the engine (`src/engine/`, `src/strategy/dealer_probs.py`, `src/strategy/ev_solver.py`) is effectively frozen. Any later change that moves a locked baseline must: (1) be established as a correctness fix, not a regression, with the mechanism written down; (2) record before/after numbers in the build plan's tracking table; (3) re-lock deliberately with `py tests/regression_test.py --generate-ruleset <key>` — never a blanket `--generate` that silently absorbs unrelated drift.
