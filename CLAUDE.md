# Blackjack Strategy Engine

A blackjack decision engine that solves basic strategy by exact combinatorial EV enumeration rather than transcribing a published chart, counts cards under multiple systems, and sizes bets via fractional Kelly. Served via a Flask app (`app.py`) with a vanilla-JS SPA (`static/`).

**Before making any changes, read:**
1. `.agents/instructions.md` — critical rules and common pitfalls
2. `.agents/project-overview.md` — architecture, key files, current locked baselines
3. `.agents/coding-standards.md` — conventions and correctness rules
4. `markdowns/blackjack/blackjack_build_plan_v1.md` — the full phased build plan, including the reference strategy charts (Appendix A) used as the Phase 5 known-answer test
5. `docs/system_guide.md` — deep walkthrough of the solver, where every published anchor came from, and why half-Kelly

## The one rule that matters most

Every EV number is a function of a `RuleSet` (`src/engine/rules.py`), never a global constant. Deck count, S17/H17, double-after-split, surrender rules, blackjack payout, and penetration all flow through `RuleSet` — no function may hardcode "6 decks" or "3:2" or assume S17.

## Verifying a change

```bash
py -m pytest tests/ --ignore=tests/regression_test.py -q   # full unit test suite
py tests/regression_test.py --fast                          # the regression gate, CI mode (~1 min)
py tests/regression_test.py                                 # the regression gate, full mode (recomputes exact house edge for all 4 anchor rulesets + MC sanity checks -- several minutes)
py app.py                                                    # serves the app + API on http://127.0.0.1:5000
```

The engine (`src/engine/`, `src/strategy/dealer_probs.py`, `src/strategy/ev_solver.py`) is frozen behind `data/baselines/`. Moving a locked baseline requires establishing the move as a correctness fix (not a regression), recording before/after numbers in the build plan's tracking table, and re-locking deliberately with `py tests/regression_test.py --generate-ruleset <decks>` — never a blanket `--generate`. See `.agents/coding-standards.md`'s Regression Gate Discipline.

## Poker area

A second, strictly additive Texas Hold'em engine is being built under `src/poker/`, `data/poker/`, `tests/poker/` per `markdowns/poker/poker_build_plan_v1.md` — see `.agents/instructions.md`'s "Poker Area" section before touching it. It must never modify the blackjack engine or move its baselines; `py tests/regression_test.py --fast` must stay green throughout.
