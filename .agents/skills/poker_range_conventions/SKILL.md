---
name: poker_range_conventions
description: Triggers when working with starting-hand ranges, the 169-grid notation, combo expansion, card removal, or blockers in src/poker/ranges.py.
---

# Poker Range Conventions

Conventions for `src/poker/ranges.py`. A range is not a set — it is a **weighted distribution over the 1,326 specific two-card combinations**, and it must be re-conditioned on every card that becomes visible. See `markdowns/poker/poker_build_plan_v1.md` Phase 4 for the full derivation.

## The 169-Grid Notation and Combo Counts

| Class | Grid cells | Combos each | Total |
|---|---:|---:|---:|
| Pairs (`AA`–`22`) | 13 | 6 | 78 |
| Suited (`AKs`–`32s`) | 78 | 4 | 312 |
| Offsuit (`AKo`–`32o`) | 78 | 12 | 936 |
| **Total** | **169** | | **1,326** = C(52,2) |

Support range syntax: `TT+` (pairs at or above), `A5s-A2s` (suited range), explicit combos (`AsKd`), and per-combo weights (`AJs:0.5`). **Weights are a first-class field, not an optional decoration** — a solved strategy playing a hand 50% of the time is the normal case, not an exotic one, and the storage format must express it without a special case.

## Card Removal Must Renormalise

```python
def conditioned(rng: Range, blockers: int) -> Range:
    """Drop every combo conflicting with `blockers`, then RENORMALISE the weights."""
```
Dropping combos without renormalising silently understates the range's total weight and corrupts every downstream equity or EV computation that treats the range as a probability distribution.

## Range-vs-Range Equity: Joint Sum, Never Per-Combo Averaging

This is this project's peek-conditioning-equivalent bug — the naive version comes out *almost* right and is wrong exactly in the spots where the decision is close (ace-high boards, river bluff-catches, ace-blocker jams).

**Wrong:** average each combo's equity against the opponent's unconditioned range, then weight by the combo's own weight.
**Right:** iterate over ordered pairs `(a, b)` from the two ranges, **skip pairs that share a card**, weight each surviving pair by `w_a × w_b`, normalise by the sum of weight actually used.

Any test of this logic must include at least one constructed spot where the two methods provably disagree by more than 0.5pp — a test that can't produce such a spot means the naive path was never actually implemented differently, and the test proves nothing.

## Named Reference Ranges Are Inputs, Not Answers

`data/poker/ranges/*.json` holds standard opening/calling ranges for UI convenience and as solver seeds. Once the CFR solver (Phase 7+) has passed its validation gate (Phase 8), **the solver is the source of truth** and a disagreeing reference range gets corrected or relabeled — the same standing relationship the blackjack area has between its solver and published basic-strategy charts. Never patch a solved range to match a reference chart without finding the underlying bug first.

## Verification Pattern

```bash
py -m pytest tests/poker/test_ranges.py -q
```
Expected: combo counts match the table above exactly (`Range('AA').n_combos() == 6`); card removal drops and renormalises correctly (`Range('AA').conditioned(mask(['As'])).n_combos() == 3`); the joint-vs-naive range-equity divergence test passes with a >0.5pp gap on its constructed spot.
