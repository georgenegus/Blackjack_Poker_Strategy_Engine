# Project Overview — Blackjack Strategy Engine

## What This Project Is

A **blackjack decision engine** built on an exact combinatorial EV solver, not a transcribed strategy chart. It computes:
- The mathematically optimal action (stand/hit/double/split/surrender) for any hand, dealer upcard, shoe composition, and rule set
- True-count-indexed deviations from basic strategy (Illustrious 18 + Fab 4), derived by re-solving cells against count-biased shoe compositions
- Kelly-optimal bet sizing from bankroll, true count, and the simulated edge-vs-count relationship

Served through a **Flask web application** with a vanilla-JS single-page frontend (not yet built — see Phases 10–11 of the build plan), styled after the glassmorphism dark-mode convention used in `T20_Win_Probability_Model`.

This project's structure is deliberately based on `C:\Python\T20_Win_Probability_Model` (`.agents/` agent docs, `src/` subpackages by concern, `tests/` as regression gates against locked JSON baselines, `markdowns/<area>/` build plans, Flask + vanilla-JS SPA) — see that repo for the template this one follows, and `markdowns/blackjack/blackjack_build_plan_v1.md` for the two deliberate deviations (this repo commits `data/strategy/`, `data/indices/`, `data/baselines/`, and `markdowns/`, where T20 gitignores both).

## Current Status

**Phase 0 (repository bootstrap) complete.** No engine code exists yet. See the Implementation Tracking table in `markdowns/blackjack/blackjack_build_plan_v1.md` for live status of every phase.

## Architecture (Planned Pipeline)

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

## Key Source Files (Planned — not yet created)

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
| `app.py` | Flask API — `/api/grid`, `/api/advise`, `/api/game/*`, `/api/count`, `/api/stake`, `/api/simulate` | 10 |
| `static/index.html`, `js/*.js` | Web UI — Play / Strategy Grid / Counting / Bankroll / Simulator tabs | 11 |
| `tests/regression_test.py` | The gate — grid + house edge + indices vs locked baselines | 12 |

## Key Test/Validation Files (Planned)

| File | Purpose | Phase |
|------|---------|:---:|
| `tests/test_strategy_grid.py` | Solver output vs published charts (Appendix A of the build plan), cell-for-cell | 5 |
| `tests/test_house_edge.py` | Simulated house edge vs published anchors, ±0.02% tolerance | 5 |
| `tests/test_deviations.py` | Derived count indices vs Illustrious 18 / Fab 4, ±1 TC tolerance | 7 |
| `tests/regression_test.py` | Full gate: grid + house edge + indices + edge-model fit vs locked baselines, `--generate`/`--generate-ruleset` to re-lock | 12 |

## Model Performance (Locked Baselines)

None yet — Phase 5 has not run. Once locked, `data/baselines/strategy_baseline.json` and `house_edge_baseline.json` will be summarised here, following the same convention T20 uses for its `baseline_metrics.json` table.

## Cached Data (Planned)

Unlike T20, small deterministic artifacts here are **committed to the repo**, not gitignored:
- `data/strategy/{ruleset_key}.json` — solved basic-strategy grid, one per shipped `RuleSet` (Phase 4)
- `data/indices/{ruleset_key}__{system}.json` — solved count-index tables (Phase 7)
- `data/baselines/strategy_baseline.json`, `house_edge_baseline.json`, `edge_model_baseline.json` — locked regression baselines (Phase 5/8)
- `data/sims/` — raw Monte Carlo output, **gitignored** (large, non-deterministic, regenerable)

## Rule Variants Shipped

Per the build plan, `scripts/build_all_grids.py` (Phase 4) pre-solves the matrix `{2,4,6,8} decks × {S17,H17} × {DAS, no-DAS} × {LS, no surrender}` = 32 grids. 6-deck is included as an additional anchor beyond the requested 2/4/8 because it has the richest published validation data and is what Phase 5 leans on hardest.
