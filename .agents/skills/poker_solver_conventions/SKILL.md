---
name: poker_solver_conventions
description: Triggers when working on the betting tree, card abstraction, CFR solver, exploitability, push/fold, or ICM code in src/poker/tree.py, abstraction.py, cfr.py, exploit.py, pushfold.py, icm.py.
---

# Poker Solver Conventions

Conventions for `src/poker/tree.py`, `abstraction.py`, `cfr.py`, `exploit.py`, `toy.py`, `pushfold.py`, `icm.py`. See `markdowns/poker/poker_build_plan_v1.md` Phases 6–10 for the full derivation and Phase 8 for the validation gate.

## `GameSpec` Is the Single Source of Truth (the headline rule)

Every equity, EV, frequency, and exploitability figure is a function of an explicit `(GameSpec, Range)` pair. No function may hardcode 100bb, heads-up, rake-free, or a bet-size grid. A new game type is a different `GameSpec` (`src/poker/spec.py`), never a branch on a string scattered through `src/poker/`. `spec.bet_sizes` lives on `GameSpec`, not in `tree.py`, because the betting abstraction is part of the definition of the game being solved — a solve at `(0.5, 1.0)` and one at `(0.33, 0.75, 1.5)` are answers to different games and must land in different cache directories (`GameSpec.key()`).

## A Strategy Without a Measured Exploitability Is Not a Result (the second headline rule)

CFR always terminates with *something* — a converged equilibrium and a diverged mess both come out as a tidy frequency table, indistinguishable by eye. No strategy artifact may be written to `data/poker/strategy/` without its exploitability and iteration count recorded in the same file. This is the poker analogue of the blackjack area's "no bare point estimates from Monte Carlo" rule.

## Abstraction Exploitability ≠ Real-Game Exploitability

Always name the field `abstraction_exploitability_mbb` — in JSON, in the API, in the UI, in this project's docs — never bare "exploitability". It is measured **inside** the abstracted game (bucketed cards, discretised bet sizes), and Waugh et al. (2009) showed that refining an abstraction can *increase* real-game exploitability, non-monotonically. Convergence on the toy games (Phase 8) validates the regret update and tree traversal; it says nothing about the card abstraction or bet-size grid.

## Report the Average Strategy, Never the Current One

In vanilla CFR the *current* strategy oscillates and can be arbitrarily far from equilibrium at any single iteration; only the **time-averaged** strategy is proven to converge. CFR+'s current strategy is unusually well-behaved, which makes shipping it by mistake easier to get away with — and therefore easier to actually ship. Always persist and report the average.

## Regret Matching⁺ (CFR+, the shipped default)

Three changes from vanilla CFR: floor cumulative regrets at zero every iteration (`R ← max(R + r, 0)`), weight each iteration's strategy contribution linearly by iteration number, and alternate which player updates each iteration. Build vanilla CFR first anyway — it's small enough to read end-to-end and check by hand against Kuhn poker, and it's the reference Phase 8 checks CFR+ against.

## Perfect Recall by Default

An information set is `(my hole-card bucket, public board, betting history)` — it must be structurally impossible to key an infoset on anything the acting player cannot see. CFR's convergence guarantee requires perfect recall; imperfect-recall abstractions (forgetting earlier-street detail to afford more buckets later) are common in strong agents but void that guarantee. Ship perfect recall for v1; if imperfect recall is adopted later for memory reasons, record the loss of guarantee explicitly in the build plan's tracking table.

## Bounded Solves Only, Behind the API

`/api/poker/solve` (Phase 12) must be bounded by iteration count **and** wall-clock, with a node-count pre-check that rejects an oversized tree before starting — the same constraint the blackjack side's `/api/simulate` already lives under on the 7.7GB dev machine. An unbounded solve endpoint is a self-inflicted denial of service.

## Push/Fold Is Solved Exactly, Not by CFR

The jam-or-fold game reduces to a direct lookup into the Phase 3 equity matrix, solved by fictitious play (alternating best response) with no tree and no abstraction — milliseconds, and exact up to the equity matrix itself. It depends only on Phase 5 (`equity.py`), deliberately *not* on Phase 8's CFR machinery. Validate against the Miltersen–Sørensen (2007) analytic result / published Nash push-fold tables, within 2% of total hand frequency per stack depth.

## Verification Pattern

```bash
py -m pytest tests/poker/test_toy_games.py -q -v
py -c "from src.poker.toy import KuhnPoker; from src.poker.cfr import solve; \
s = solve(KuhnPoker(), iterations=10_000, variant='cfr+'); print(round(s.game_value, 6))"
```
Expected: Kuhn poker's game value converges to **−0.055556** (−1/18) *and* its four frequency rows (Appendix A.5) match — a game-value-only check passes structurally wrong solvers.
