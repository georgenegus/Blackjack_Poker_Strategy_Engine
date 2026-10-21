---
name: poker_evaluator_conventions
description: Triggers when writing or modifying the hand evaluator, equity engine, or card/board encoding in src/poker/cards.py, evaluator.py, equity.py.
---

# Poker Evaluator Conventions

Conventions for `src/poker/cards.py`, `evaluator.py`, `equity.py` — the layer every other poker module depends on. An evaluator wrong on one hand in 10⁵ produces equities wrong in the third decimal, invisibly, and corrupts every solve built on it. See `markdowns/poker/poker_build_plan_v1.md` Phases 2–3 and 5 for the full derivation and the validation gate.

## Rank Direction Is Fixed, Never Flipped

Every 5-card hand maps to one of exactly **7,462** distinct rank classes. This project's convention: **lower integer = stronger hand** (royal flush = 0). Do not flip this anywhere — a function that silently reverses the comparison (e.g. treating a raw output as "higher is better" in one call site) is the single easiest way to make an evaluator that looks right on spot checks and is backwards everywhere else.

## Cards Retain Suit — No Bucket Collapse

Unlike the blackjack side's 10-bucket rank collapse, poker needs full rank × suit (52 values), because flushes and suit isomorphism both depend on it. `card_id`: `rank = card // 4`, `suit = card % 4`. A 52-bit mask (`sum(1 << c for c in cards)`) is the standard representation for O(1) conflict/blocker checks — use it for range conditioning and dead-card checks rather than set operations.

## Ties Are Exact Integer Equality, Not "Close Enough"

Two hands tie iff their rank classes are the *same integer*. A split pot scores exactly 0.5 to each side. This is handled in the **comparator**, not the evaluator, and needs its own explicit tests — the Phase 5 category-count enumeration does not exercise tie logic at all. Board-plays-the-hand spots (best five cards are all on the board) are the case that breaks a hand-rolled comparator that tries to break ties by kicker.

## Two Independent Implementations, Checked Against Each Other

Strategy A (21-subset perfect hash over C(7,5)) is the reference; Strategy B (7-card DAG lookup) is the fast path. They must agree **element-wise on all 133,784,560 seven-card hands** — this is stronger evidence of correctness than either one matching a handful of hand-checked examples, and it is Phase 5's Check 2.

## Exact vs Sampled Equity — Decided by Runout Count, Never Guessed

```
Preflop heads-up:  C(48,5) = 1,712,304   → exact
Flop, 2 players:   C(45,2) = 990         → exact
Turn, 2 players:   44                    → exact
Range vs range:    up to 1,326² runouts  → Monte Carlo
```
Rule: enumerate whenever the runout count is below `EXACT_LIMIT` (default 5,000,000); sample otherwise. Never sample a spot that could have been enumerated exactly.

## No Bare Point Estimates From Monte Carlo (inherited, unmodified)

`equity_mc(...)` returns `(equities, standard_errors)` — there is no single-value convenience wrapper, because a signature that makes the error optional guarantees it gets dropped before it reaches the UI. This is the blackjack area's rule (`.agents/instructions.md`), applied here without exception.

## Equity Is Not EV

Equity is the showdown share of the *current* pot assuming a random runout with no further betting. EV also depends on fold equity and the ability to realise that equity given position and future action. Every field and label must say which one it is — this is a naming-discipline requirement, not a computational one, and it is the most common way a poker tool misleads its user.

## Range-vs-Range Equity Must Use Joint Card Removal

Averaging each combo's equity-against-the-*unconditioned* range and then weighting by the combo's own weight double-counts blocked combos and is typically wrong by 0.5–2 percentage points — worst exactly on blocker-heavy, close-decision boards. Compute range-vs-range equity as a joint sum over **non-conflicting** combo pairs `(a, b)`, weighted by `w_a × w_b`, normalised by the weight actually used. See `poker_range_conventions` for the range side of this.

## Verification Pattern

```bash
py -m pytest tests/poker/test_evaluator.py tests/poker/test_equity.py -q   # fast subsample
py -m pytest tests/poker/test_evaluator.py -q -m slow                      # full C(52,7) enumeration
```
Expected: the nine category counts across all 133,784,560 seven-card hands match `markdowns/poker/poker_build_plan_v1.md` Appendix A.1 **exactly** — no tolerance.
