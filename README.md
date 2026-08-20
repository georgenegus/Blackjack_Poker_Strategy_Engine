# Blackjack Strategy Engine

A blackjack simulator that solves basic strategy from first principles, counts cards, and sizes stakes by Kelly criterion — served through a Flask UI that tells the player the mathematically correct decision on every hand.

Unlike most blackjack tools, the strategy grid is not a transcribed chart — it is the output of an exact combinatorial EV solver (`src/strategy/ev_solver.py`) that computes `EV(action | hand, dealer upcard, shoe composition, rules)` for every cell. Published charts are used only as a known-answer test the solver must reproduce. See [`markdowns/blackjack/blackjack_build_plan_v1.md`](markdowns/blackjack/blackjack_build_plan_v1.md) for the full build plan.

## Status

Pre-implementation. Phase 0 (repository bootstrap) is complete; Phases 1–12 are tracked in the build plan's Implementation Tracking table.

## Before making any changes, read

1. [`.agents/instructions.md`](.agents/instructions.md) — critical rules and common pitfalls
2. [`.agents/project-overview.md`](.agents/project-overview.md) — architecture, key files, locked baselines
3. [`.agents/coding-standards.md`](.agents/coding-standards.md) — conventions and correctness rules
4. [`markdowns/blackjack/blackjack_build_plan_v1.md`](markdowns/blackjack/blackjack_build_plan_v1.md) — the full phased build plan

## The one rule that matters most

Every EV number is a function of a `RuleSet` (`src/engine/rules.py`) — deck count, S17/H17, DAS, surrender, blackjack payout, penetration — never a global constant. No function may assume 6 decks, S17, or 3:2 blackjack.

## Planned feature set

- **Basic strategy grid** for any ruleset (2/4/6/8-deck shoes, S17/H17, DAS, late surrender), solved exactly rather than hardcoded
- **Card counting**: Hi-Lo, KO, Hi-Opt I/II, Omega II, Zen, Red 7 — running count, true count, count-indexed strategy deviations (Illustrious 18 + Fab 4)
- **Bankroll management**: Kelly-optimal bet sizing from bankroll and true count, risk of ruin, N₀, drawdown estimates
- **Web UI**: play a hand, view the strategy grid, drill counting, size bets, and run Monte Carlo batteries — all against the same validated engine

## Disclaimer

This project is for educational and simulation purposes. Card counting is legal, but casinos may refuse service to suspected counters. Simulated results carry statistical uncertainty and are not a guarantee of real-world outcomes.

## Verifying a change (once Phase 12 is implemented)

```bash
py tests/regression_test.py   # grid + house edge + count indices vs locked baselines
```
