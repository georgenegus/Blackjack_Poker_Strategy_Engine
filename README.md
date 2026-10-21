# Cards — Blackjack & Hold'em Strategy Engines

Two card-game strategy engines behind one Flask app. Both compute strategy from first principles and check themselves against published results; neither copies a chart.

- **Blackjack.** An exact combinatorial EV solver produces basic strategy for any ruleset. Count-indexed deviations come from re-solving against count-biased shoes. Bets are sized by fractional Kelly.
- **Texas Hold'em** (heads-up). An exact hand evaluator and equity engine, plus CFR / CFR+ / DCFR / MCCFR solvers validated against an independent LP on toy games. Also includes push/fold with ICM, and preflop strategy lookups.

<!-- TODO: screenshot or GIF of the blackjack Play tab and the poker Preflop tab -->

## Why trust the numbers

Published values are used only as known-answer tests. Every result below is recomputed by the regression gate and locked in `data/baselines/`.

**Blackjack: exact house edge** (S17, DAS, no surrender, 3:2, fresh shoe) against published anchors, tolerance ±0.02pp:

| Decks | Exact edge | Published |
|---:|---:|---:|
| 2 | 0.173% | 0.19% |
| 4 | 0.344% | 0.35% |
| 6 | 0.400% | 0.40% |
| 8 | 0.428% | 0.43% |

**Blackjack: rule-effect deltas**, solved independently of the absolute edge. A solver can get the absolute edge right and still mishandle a rule, so these are checked separately:

| Rule change | House-edge change (solver) | Published |
|---|---:|---:|
| H17 vs S17 | +0.213pp | ~+0.22pp |
| No DAS vs DAS | +0.142pp | ~+0.14pp |
| No surrender vs late surrender | +0.072pp | ~+0.08pp |
| 6:5 vs 3:2 blackjack | +1.360pp | ~+1.39pp |
| Resplit aces | −0.070pp | ~−0.08pp |

In addition:

- **Strategy charts.** The solved grid matches the reference charts cell for cell for 4/6/8 decks under both S17 and H17 (340 cells each).
- **Monte Carlo cross-check.** A 2M-hand simulation agrees with every exact edge within its standard-error-aware tolerance.
- **Count edge model.** A 20M-hand Hi-Lo simulation (6D S17 DAS LS) with the Illustrious 18 + Fab 4 deviations gives `edge(TC) ≈ −0.33% + 0.48%·TC`, with R² = 0.98.

**Poker:**

- **Kuhn poker.** The sequence-form LP matches the analytic game value (−1/18) to machine precision.
- **Leduc poker.** The CFR game value matches the LP to 2×10⁻⁵.

### Known limitations

These are reported as measured, not hidden:

- **Leduc exploitability** reached 0.0092, short of the 10⁻³ target. Closing the gap would take roughly 17 hours of further DCFR iterations.
- **Abstraction error in the heads-up preflop solves.** Exploitability inside the abstraction is about 2,270 mbb/g at 100bb and about 480 mbb/g at 10bb. This measures error *inside the abstraction*, not exploitability in the real game.
- **Preflop terminal values** use an equity-realisation approximation. It is the weakest modelling assumption in the poker engine.
- **Poker scope** is heads-up, preflop, plus bounded single-spot postflop solves. Full-tree postflop solving is out of scope.

## Quickstart

Requires Python 3.12+ (CI runs 3.12).

```bash
pip install -r requirements.txt
python scripts/poker/build_evaluator_tables.py   # one-time, ~20 s; the poker evaluator needs it
python app.py                                    # blackjack at http://127.0.0.1:5000, poker at /poker
```

Print a solved basic-strategy grid from the command line:

```bash
python main.py --decks 6 --s17 --das --surrender late --print-grid
```

On Windows, `py` works in place of `python`.

## What's in the app

| | Blackjack (`/`) | Poker (`/poker`) |
|---|---|---|
| Tabs | Play, Strategy Grid, Counting, Bankroll, Simulator | Equity, Ranges, Preflop, Push/Fold & ICM, Solver, Bankroll, Trainer |
| API | `/api/rules`, `/api/grid`, `/api/advise`, `/api/count`, `/api/stake`, `/api/simulate`, `/api/game/{new,deal,action}` | `/api/poker/{spec,equity,range/parse,range/equity,preflop,advise,pushfold,icm,solve,bankroll}` |

The frontend is vanilla JavaScript with no build step.

## Architecture

### Blackjack

Every number is a function of a frozen `RuleSet` (`src/engine/rules.py`). It covers decks, S17/H17, DAS, doubling restrictions, surrender, blackjack payout, resplit rules, peek and penetration. Nothing assumes 6 decks, S17 or 3:2. `RuleSet.key()` (e.g. `6d-s17-das-ls-p75`) names every cached artifact.

| Layer | Files | What it does |
|---|---|---|
| Mechanics | `src/engine/` | Cards, shoe with cut card, hands, dealer play, round state machine |
| Exact solver | `src/strategy/dealer_probs.py`, `ev_solver.py` | Dealer outcome distribution (peek-conditioned); memoised recursive EV of stand, hit, double, split and surrender |
| Strategy grid | `src/strategy/grid_builder.py`, `basic_strategy.py`, `exact_edge.py` | Solves every hard, soft and pair cell; exact house edge |
| Counting | `src/counting/` | Hi-Lo, KO, Hi-Opt I/II, Omega II, Zen, Red 7 |
| Deviations | `src/strategy/index_builder.py`, `deviations.py` | Illustrious 18, Fab 4 and insurance indices, derived rather than transcribed |
| Simulation | `src/simulation/` | Monte Carlo batteries with standard errors, N₀, risk of ruin, SCORE |
| Bankroll | `src/bankroll/` | Fractional (default half) Kelly, discrete bet ramp, drawdown and risk profile |

Solved grids are cached as JSON and validated against a hash of the solver source plus the ruleset. A stale cache is rebuilt rather than trusted.

### Poker

Everything lives under `src/poker/`, keyed by `GameSpec` (`spec.py`), the poker counterpart of `RuleSet`. It covers players, stacks, blinds, antes, rake and bet sizes.

| Area | Files |
|---|---|
| Evaluation and equity | `evaluator.py` (exact 5/6/7-card, 7,462 classes), `equity.py` (exact enumeration, or Monte Carlo with standard errors), `ranges.py` (169-grid notation, combos, card removal) |
| Solving | `tree.py`, `abstraction.py`, `cfr.py` (vanilla, CFR+, DCFR, external-sampling MCCFR) |
| Validation | `exploit.py` (best-response exploitability), `toy.py` (Kuhn and Leduc, with an independent sequence-form LP) |
| Applications | `pushfold.py`, `icm.py` (Malmuth–Harville), `advisor.py`, `bankroll.py` |

The poker engine is strictly additive. It never modifies the blackjack engine or its baselines.

## Testing

```bash
python tests/regression_test.py --fast           # blackjack regression gate (~4 min)
python tests/poker/regression_test.py --fast     # poker regression gate (~5 min)
python -m pytest tests/ --ignore=tests/regression_test.py --ignore=tests/poker -q
python -m pytest tests/poker/ --ignore=tests/poker/regression_test.py -q
```

The `--fast` gates are what CI runs, as two separate jobs so a failure names the engine that broke. Without `--fast`, the blackjack gate recomputes all four exact house edges plus the Monte Carlo checks, which takes several minutes. Some unit tests also run full solves and are slow.

## Further reading

- [`docs/system_guide.md`](docs/system_guide.md): how the blackjack solver works, where every published anchor came from, and why half-Kelly.
- [`docs/poker_guide.md`](docs/poker_guide.md): CFR and MCCFR, the equity-realisation approximation, and why abstraction exploitability is not real-game exploitability.
- [`markdowns/blackjack/blackjack_build_plan_v1.md`](markdowns/blackjack/blackjack_build_plan_v1.md) and [`markdowns/poker/poker_build_plan_v1.md`](markdowns/poker/poker_build_plan_v1.md): the phased build history, including every bug found and the verification numbers for each phase.

## Development

The project was built with AI coding agents working from the build plans above. Their working rules are in [`.agents/`](.agents/) (mirrored in `.claude/skills/`) and [`CLAUDE.md`](CLAUDE.md). The engine is frozen behind `data/baselines/`. Moving a locked baseline has to be justified as a correctness fix and re-locked deliberately, per ruleset. See [`.agents/coding-standards.md`](.agents/coding-standards.md).

## Disclaimer

This project is for education and simulation. Card counting is legal, but casinos may refuse service to suspected counters. Simulated results carry statistical uncertainty and are no guarantee of real-world outcomes.
