# Blackjack Strategy Engine

A blackjack decision engine that solves basic strategy by exact combinatorial EV enumeration rather than transcribing a published chart, counts cards under multiple systems, and sizes bets via fractional Kelly. Served via a Flask app (`app.py`, not yet built) with a vanilla-JS SPA (`static/`, not yet built).

**Before making any changes, read:**
1. `.agents/instructions.md` — critical rules and common pitfalls
2. `.agents/project-overview.md` — architecture, key files, current locked baselines
3. `.agents/coding-standards.md` — conventions and correctness rules
4. `markdowns/blackjack/blackjack_build_plan_v1.md` — the full phased build plan, including the reference strategy charts (Appendix A) used as the Phase 5 known-answer test

## The one rule that matters most

Every EV number is a function of a `RuleSet` (`src/engine/rules.py`), never a global constant. Deck count, S17/H17, double-after-split, surrender rules, blackjack payout, and penetration all flow through `RuleSet` — no function may hardcode "6 decks" or "3:2" or assume S17.

## Verifying a change

```bash
py tests/regression_test.py   # grid + house edge + count-index gate, once Phase 12 lands
```
Until Phase 5 locks the strategy and house-edge baselines, there is nothing to regress against — build in phase order (see the Implementation Tracking table in the build plan) and do not start Phase 6+ before Phase 5 passes.
