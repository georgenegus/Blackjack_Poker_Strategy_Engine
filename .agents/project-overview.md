# Project Overview — Blackjack Strategy Engine

## What This Project Is

A **blackjack decision engine** built on an exact combinatorial EV solver, not a transcribed strategy chart. It computes:
- The mathematically optimal action (stand/hit/double/split/surrender) for any hand, dealer upcard, shoe composition, and rule set
- True-count-indexed deviations from basic strategy (Illustrious 18 + Fab 4), derived by re-solving cells against count-biased shoe compositions
- Kelly-optimal bet sizing from bankroll, true count, and the simulated edge-vs-count relationship

Served through a **Flask web application** (`app.py`) with a vanilla-JS single-page frontend (`static/`), styled after the glassmorphism dark-mode convention used in `T20_Win_Probability_Model`.

This project's structure is deliberately based on `C:\Python\T20_Win_Probability_Model` (`.agents/` agent docs, `src/` subpackages by concern, `tests/` as regression gates against locked JSON baselines, `markdowns/<area>/` build plans, Flask + vanilla-JS SPA) — see that repo for the template this one follows, and `markdowns/blackjack/blackjack_build_plan_v1.md` for the two deliberate deviations (this repo commits `data/strategy/`, `data/indices/`, `data/baselines/`, and `markdowns/`, where T20 gitignores both).

## Current Status

**All 12 phases complete.** Engine, solver, validation gate, counting, deviations, simulator, bankroll, Flask API, web UI, and the Phase 12 regression gate + CI workflow are all built. `py tests/regression_test.py --fast` is the one command that checks everything this repo ships against a fresh recomputation. See the Implementation Tracking table in `markdowns/blackjack/blackjack_build_plan_v1.md` for full per-phase notes, and `docs/system_guide.md` for the technical walkthrough (solver derivation, where every published anchor came from, count-to-composition mapping, why half-Kelly).

## Architecture (Pipeline)

```
RuleSet (src/engine/rules.py) ── the single source of truth for every rule variant
        │
        ▼
Shoe / Hand / Dealer / Game  (src/engine/)  ── the game mechanics, no strategy knowledge
        │
        ▼
dealer_probs.py → ev_solver.py  (src/strategy/)  ── exact EV per action, per cell
        │
        ▼
grid_builder.py → basic_strategy.py  ── solved grid, cached per ruleset
        │
        ├──────────────────────────────┐
        ▼                              ▼
counting/systems.py + counter.py   Phase 5 VALIDATION GATE
        │                          (grid vs published charts,
        ▼                           simulated house edge)
index_builder.py → deviations.py
        │
        ▼
simulation/simulator.py → edge_model.py  ── Monte Carlo, TC → edge fit
        │
        ▼
bankroll/kelly.py → bet_ramp.py → risk.py
        │
        ▼
Flask API (app.py) — grid / advise / game / count / stake / simulate
        │
        ▼
Web UI (static/) — Play / Strategy Grid / Counting / Bankroll / Simulator tabs
```

## Key Source Files

| File | Purpose | Phase |
|------|---------|:---:|
| `src/engine/rules.py` | `RuleSet` dataclass — every rule variant's single source of truth | 1 |
| `src/engine/cards.py`, `shoe.py`, `hand.py` | Card/shoe/hand primitives, 10-bucket rank composition | 1 |
| `src/engine/dealer.py`, `game.py` | Dealer draw logic, round state machine | 2 |
| `src/strategy/dealer_probs.py` | Exact dealer outcome distribution, peek-conditioned | 3 |
| `src/strategy/ev_solver.py` | EV of stand/hit/double/split/surrender per cell | 3 |
| `src/strategy/grid_builder.py`, `basic_strategy.py` | Solved grid generation, cache, runtime lookup | 4 |
| `src/strategy/index_builder.py`, `deviations.py` | Count-indexed strategy deviations | 7 |
| `src/counting/systems.py`, `counter.py` | Hi-Lo/KO/Hi-Opt/Omega II/Zen/Red 7, running/true count | 6 |
| `src/counting/edge_model.py` | Simulation-fitted true-count → player-edge model | 8 |
| `src/simulation/simulator.py`, `metrics.py` | Monte Carlo shoe engine, EV/variance/RoR/N₀ | 8 |
| `src/bankroll/kelly.py`, `bet_ramp.py`, `risk.py` | Kelly sizing, discrete bet ramp, risk of ruin | 9 |
| `app.py` | Flask API — `/api/grid`, `/api/advise`, `/api/game/*`, `/api/count`, `/api/stake`, `/api/simulate`; also serves `static/` at `/` | 10/11 |
| `static/index.html`, `css/style.css`, `js/{app,rules,table,grid,counting,bankroll,simulator}.js` | Web UI — Play / Strategy Grid / Counting / Bankroll / Simulator tabs, vanilla JS, glassmorphism dark mode | 11 |
| `tests/regression_test.py` | The gate — grid cache freshness + Appendix A + house edge + indices + edge-model sanity vs locked baselines | 12 |
| `docs/system_guide.md` | Deep technical walkthrough: solver derivation, published-anchor provenance, count-to-composition mapping, why half-Kelly | 12 |
| `.github/workflows/regression.yml` | CI: full unit suite + `regression_test.py --fast` on every push/PR | 12 |

## Key Test/Validation Files

| File | Purpose | Phase |
|------|---------|:---:|
| `tests/test_strategy_grid.py` | Solver output vs published charts (Appendix A of the build plan), cell-for-cell | 5 |
| `tests/test_house_edge.py` | Simulated house edge vs published anchors, ±0.02% tolerance (primary: exact, flat tolerance; secondary: MC vs the exact figure, SE-aware tolerance) | 5 |
| `tests/test_deviations.py` | Derived count indices vs Illustrious 18 / Fab 4, ±1 TC tolerance | 7 |
| `tests/regression_test.py` | The gate: grid cache freshness, grid vs Appendix A (reused from test_strategy_grid.py), house edge vs locked baseline (fresh exact recompute, MC secondary outside `--fast`), Illustrious 18/Fab 4/insurance vs published, edge-model sanity + fresh-battery cross-check outside `--fast`. `--generate`/`--generate-ruleset <decks>` re-lock `house_edge_baseline.json` only — `edge_model_baseline.json` stays `scripts/run_sim_battery.py --generate`'s job (~70 min for 20M hands) | 12 |

## Model Performance (Locked Baselines)

- **Strategy grid**: no separate `strategy_baseline.json` file — the grid is validated directly against the Appendix A fixture in `tests/test_strategy_grid.py` every run (fast and deterministic, so there's nothing to gain from a separate lock file). All 32 shipped grids' `data/strategy/*.json` cache files are hash-validated against current solver source on every load.
- **House edge** (`data/baselines/house_edge_baseline.json`): exact (zero-noise) edge vs published anchor, S17/DAS/no-surrender/3:2 — 2D 0.1727% (anchor 0.19%), 4D 0.3439% (0.35%), 6D 0.4002% (0.40%), 8D 0.4284% (0.43%). All within the ±0.02% primary gate; MC secondary (2M hands each) within 4×SE of the exact figure.
- **Edge model** (`data/baselines/edge_model_baseline.json`, 6d-s17-das-ls-p75/Hi-Lo, 20M hands): `edge(TC) = -0.00326 + 0.00479·TC`, R² = 0.9789 over the trusted TC∈[-3,+6] fit range.

## Cached Data

Unlike T20, small deterministic artifacts here are **committed to the repo**, not gitignored:
- `data/strategy/{ruleset_key}.json` — solved basic-strategy grid, one per shipped `RuleSet` (Phase 4); 32 shipped
- `data/indices/{ruleset_key}__{system}.json` — solved count-index tables (Phase 7); only `6d-s17-das-ls-p75__hi-lo.json` has been pre-built so far
- `data/baselines/house_edge_baseline.json`, `edge_model_baseline.json` (+ its keyed `edge_model__{ruleset_key}__{system}.json` twin) — locked regression baselines (Phase 5/8)
- `data/sims/` — raw Monte Carlo output, **gitignored** (large, non-deterministic, regenerable)

## Rule Variants Shipped

Per the build plan, `scripts/build_all_grids.py` (Phase 4) pre-solves the matrix `{2,4,6,8} decks × {S17,H17} × {DAS, no-DAS} × {LS, no surrender}` = 32 grids. 6-deck is included as an additional anchor beyond the requested 2/4/8 because it has the richest published validation data and is what Phase 5 leans on hardest.

---

## Poker Area (Additive)

A second engine, `markdowns/poker/poker_build_plan_v1.md`, in progress. **Strictly additive** — see that plan's Non-Destructive Principle and `.agents/instructions.md`'s "Poker Area" section for the boundary. Status: Phase 0 (bootstrap) only; see the build plan's Implementation Tracking table for current phase status, which is more current than this section.

| File | Purpose | Phase |
|------|---------|:---:|
| `src/poker/spec.py` | `GameSpec` dataclass — every equity/EV/frequency is a function of this, the poker analogue of `RuleSet` | 1 |
| `src/poker/cards.py` | 52-card rank×suit encoding, bitmasks, suit isomorphism (169 preflop classes, 1,755 flop classes) | 1 |
| `src/poker/evaluator.py` | Exact 5/6/7-card hand evaluator → 7,462 rank classes, validated against the full C(52,7) enumeration | 2 |
| `src/poker/equity.py` | Exact enumeration where tractable, Monte Carlo with mandatory standard errors otherwise | 3 |
| `src/poker/ranges.py` | 169-grid notation, weighted combos, card removal with renormalisation | 4 |
| `src/poker/tree.py`, `abstraction.py` | Betting tree from `GameSpec`, card bucketing | 6 |
| `src/poker/cfr.py` | CFR+ / Discounted CFR / MCCFR solver | 7 |
| `src/poker/exploit.py`, `toy.py` | Best-response exploitability, Kuhn/Leduc toy games with analytic/LP references | 8 |
| `src/poker/pushfold.py`, `icm.py` | Exact jam/fold equilibrium, Malmuth-Harville ICM | 9 |
| `src/poker/advisor.py` | Runtime spot → action-frequency lookup | 10 |
| `src/poker/bankroll.py` | Risk of ruin, win-rate confidence intervals, downswing quantiles | 11 |
| `src/poker/api.py` | Flask Blueprint, `/api/poker/*` — the only permitted edit to `app.py` is registering it | 12 |
| `tests/poker/regression_test.py` | The poker gate — mirrors `tests/regression_test.py`'s role, kept as a separate CI job | 14 |

`data/poker/{evaluator,solves}/` are gitignored (large, regenerable); `data/poker/{equity,ranges,strategy,baselines}/` are committed, matching the blackjack area's policy on `data/{strategy,indices,baselines}/` vs `data/sims/`.
