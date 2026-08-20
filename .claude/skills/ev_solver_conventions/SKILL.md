---
name: ev_solver_conventions
description: Triggers when writing or modifying the exact EV solver, dealer probability distribution, strategy grid generation, or count-index derivation in src/strategy/.
---

# EV Solver Conventions

Conventions for `src/strategy/` — the exact combinatorial solver that is the project's source of truth for every strategy decision. Published charts (Appendix A of `markdowns/blackjack/blackjack_build_plan_v1.md`) are a known-answer test for this code, never the implementation.

## Peek Conditioning (the most common solver bug)

When `rules.dealer_peeks` is true and the dealer's upcard is a Ten or Ace, the dealer has already checked the hole card and does not have blackjack. The hole-card distribution used in every downstream EV calculation must be conditioned on that: renormalise `dealer_distribution()`'s input composition after zeroing the Ace (ten up) or the Tens (ace up).

Skipping this produces a grid that is *almost* right — typically flipping only 16 vs 10 and 12 vs 4 — which is exactly why it survives casual inspection. These two cells are the canary in Phase 5's cell-for-cell chart comparison; if they're wrong, check peek conditioning first.

## Memoisation Keys

- `dealer_distribution(upcard, comp, rules)` — memoise on `(hard_total, is_soft, comp.tobytes())` during the recursion.
- The grid/EV cache (`grid_builder.py`) is keyed on `(total, is_soft, upcard, comp.tobytes(), rules.key())`.
- Solve once per `RuleSet` and cache to `data/strategy/{rules.key()}.json` — the runtime Flask app never re-solves live. Escalate to `numba` only if `scripts/build_all_grids.py` proves too slow in pure Python; do not add it as a default dependency.

## Composition Modes

Two solver modes, selected explicitly by the caller:

- `mode="total_dependent"` (default) — shoe at full composition minus known player/dealer cards. Produces the standard published charts; what Phase 5 validates against.
- `mode="composition_dependent"` — full exact removal of every visible card. Produces the genuinely optimal play for the specific hand shown (e.g. 16 vs 10 as `T+6` differs from `9+7`). This is the mode the UI's "mathematically correct decision" feature should default to once built.

Never conflate the two in a test or in cached output — a grid file's `mode` must be part of its cache key alongside `rules.key()`.

## Split EV Treatment

`ev_split = 2 × ev(one post-split hand, split card removed from shoe)`, with recursion up to `rules.resplit_to` and doubles permitted iff `rules.double_after_split`. This treats the two post-split hands as independent, which is not strictly true (they draw from the same depleted shoe) — but it is the standard treatment used by every published chart and by Griffin's *Theory of Blackjack*, and the ~0.01% error it introduces is *required* to match Appendix A. Do not "fix" this into full joint two-hand enumeration.

## Action Legality and Notation

Surrender is checked before the stand/hit/double comparison, because it caps loss at −0.5 rather than maximising EV — a cell where hit/stand both lose more than half the bet still surrenders. Double and surrender are first-action-only; split only on pairs. Grid notation:

| Code | Meaning |
|---|---|
| `H` / `S` | Hit / Stand |
| `D` | Double if allowed, otherwise Hit |
| `Ds` | Double if allowed, otherwise Stand |
| `P` | Split |
| `Ph` | Split if DAS, otherwise Hit |
| `Rh` / `Rs` / `Rp` | Surrender if allowed, otherwise Hit / Stand / Split |

## Count-Index Derivation (Phase 7)

Indices are derived, never transcribed: sweep true count, construct the shoe composition that count implies (see "Count-to-composition mapping" in `.agents/coding-standards.md` — proportional adjustment within each tag group), re-solve in `composition_dependent` mode, and record the TC at which the argmax action flips. Validate against the Illustrious 18 / Fab 4 within **±1 true count** — published tables themselves disagree by this much due to differing composition mappings, so ±1 is an honest tolerance, not a weakened gate. Any cell off by ≥2 is a genuine bug.

## No Bare Point Estimates

Any EV or edge figure produced by simulation (as opposed to the exact solver) must carry a standard error wherever it's reported — see `counting_systems_conventions` and the build plan's Phase 8.
