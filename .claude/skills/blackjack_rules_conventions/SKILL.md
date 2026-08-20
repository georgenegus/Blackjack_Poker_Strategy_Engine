---
name: blackjack_rules_conventions
description: Triggers when adding or modifying blackjack rule variants, RuleSet fields, hand/shoe primitives, or dealer/round logic in src/engine/.
---

# Blackjack Rules Conventions

Conventions for `src/engine/` — the game mechanics layer, which has no strategy knowledge and must work correctly for every rule variant.

## RuleSet Is the Single Source of Truth

Every rule variant is a field on `RuleSet` (`src/engine/rules.py`), never a hardcoded assumption elsewhere:

| Field | Type | Default | Effect on player return |
|---|---|---|---|
| `num_decks` | `int` | `6` | 2D ≈ +0.21%, 4D ≈ +0.05% vs 6D; 8D ≈ −0.03% |
| `dealer_hits_soft_17` | `bool` | `False` (S17) | H17 ≈ −0.22% |
| `blackjack_payout` | `Fraction` | `3/2` | 6:5 ≈ −1.39%; 1:1 ≈ −2.3% |
| `double_after_split` | `bool` | `True` | DAS ≈ +0.14% |
| `double_on` | `str` | `"any"` | `"9-11"` ≈ −0.09%; `"10-11"` ≈ −0.18% |
| `surrender` | `str` | `"late"` | Late surrender ≈ +0.08%; `"none"` = 0 |
| `resplit_to` | `int` | `4` | Max total hands from splits |
| `resplit_aces` | `bool` | `False` | RSA ≈ +0.08% |
| `hit_split_aces` | `bool` | `False` | Split aces get one card only |
| `dealer_peeks` | `bool` | `True` | No-hole-card (European, OBBO) ≈ −0.11% |
| `penetration` | `float` | `0.75` | No EV effect per hand; drives counting yield |
| `split_by_value` | `bool` | `True` | T/J/Q/K mutually splittable |

`RuleSet.key()` produces a short deterministic hash (e.g. `6d-s17-das-ls-p75`) used as the filename for cached grids/indices and as the cache-manifest key — the same role T20's `{format}_` artifact prefix plays for `format_spec.py`.

The rule-effect percentages above are the well-established published deltas, included so the field is self-documenting. They are **not** the source of truth — Phase 5 of the build plan re-derives every one from the solver and treats disagreement as a solver bug, not a table error.

## The 10-Bucket Rank Composition

Shoe composition is always `(n2, n3, n4, n5, n6, n7, n8, n9, nT, nA)` — T/J/Q/K collapsed into one `T` bucket, since they are indistinguishable to every rule and every count system. This collapse is what makes the solver's memoisation tractable. `Card` retains suit only because Red Seven counting needs it on the `7` rank; `Hand`/`Shoe` composition logic still operates on the 10-bucket index.

## Round Resolution Order

`game.play_round()` must resolve in exactly this order — reordering any step changes payouts silently:

```
1. Deal: player card, dealer up, player card, dealer hole (if rules.dealer_peeks)
2. If dealer upcard is Ace → offer insurance (2:1)
3. If rules.dealer_peeks and upcard in {T, A} → peek: dealer BJ settles immediately
4. Player blackjack (no dealer BJ) → pay rules.blackjack_payout
5. Player decisions, per hand, in split order: SURRENDER → SPLIT → DOUBLE → HIT/STAND
6. If no hands remain live → dealer does not draw
7. Dealer plays out
8. Settle each live hand vs dealer total
```

## Known Correctness Traps

- **21-after-split is not a blackjack** — pays 1:1 (or the table's regular win rate), never `blackjack_payout`. Only the initial two-card 21 qualifies.
- **No-peek (European/OBBO) is a common source of silent bugs.** Under `dealer_peeks=False` the player can lose the *additional* bet from a double or split to a dealer blackjack revealed later; under OBBO ("original bets only") they lose only the original bet. The two differ by ~0.11%. Get the `RuleSet` semantics explicit and unit-test both branches.
- **Split aces get exactly one card** under the default `hit_split_aces=False` — this is a terminal action, not a hit-eligible hand.
- **Strategy logic must never leak into `src/engine/`.** `game.play_round()` takes an injected `decide_fn(player_hand, dealer_up, shoe_state, rules) -> Action` — this is the seam that lets the same round engine be driven by basic strategy, count-aware deviations, a random baseline, or a human via the UI.

## Verification Pattern

Every `RuleSet` field needs at least one unit test in `tests/test_engine.py` covering both its True and False (or each enum value's) branch — see the build plan's Phase 2 minimum-coverage list (player BJ payout, push on dealer BJ, 21-after-split payout, split-ace single-card, surrender-returns-half, S17-vs-H17 dealer draw, no-draw-when-all-busted).
