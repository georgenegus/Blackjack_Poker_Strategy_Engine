# System Guide — Blackjack Strategy Engine

> **Author:** Claude Code (Sonnet 5) · **Date:** 2026-08-25
> **Purpose:** A deep technical walkthrough of how the engine actually works — the solver's derivation, where every published number this repo checks itself against came from, the count-to-composition mapping, and why half-Kelly — for anyone (human or agent) who needs to reason about *why* the code is shaped the way it is, not just what it does.
> **Companion docs:** `markdowns/blackjack/blackjack_build_plan_v1.md` (the full phased build history and every deviation encountered along the way), `.agents/instructions.md` / `coding-standards.md` (the rules this guide explains the reasoning behind).

---

## 1. Why exact enumeration instead of a transcribed chart

Nearly every blackjack tool on the internet hardcodes a basic-strategy chart copied from a book. This project computes `EV(action | hand, dealer_upcard, shoe_composition, RuleSet)` from first principles by exact recursive enumeration over the shoe, for every `action ∈ {stand, hit, double, split, surrender}`. The published charts (Appendix A of the build plan) are used only as a **known-answer test** — if the solver disagrees with a chart, the solver is presumed wrong until Phase 5's cell-for-cell comparison proves otherwise.

Everything downstream is a consequence of this one function:

```
RuleSet ──▶ Shoe/Hand/Dealer/Game (mechanics, no strategy knowledge)
                │
                ▼
dealer_probs.py ──▶ ev_solver.py (exact EV per action, per cell)
                │
                ▼
grid_builder.py ──▶ basic_strategy.py (solved grid, cached per ruleset)
                │
     ┌──────────┼──────────────────────┐
     ▼          ▼                      ▼
counting/    Phase 5 gate         index_builder.py
systems.py   (grid vs charts,     (count-indexed
             simulated edge)      deviations)
                │                      │
                ▼                      ▼
     simulation/simulator.py   deviations.py (runtime)
     + edge_model.py (TC→edge)
                │
                ▼
     bankroll/kelly.py, bet_ramp.py, risk.py
                │
                ▼
     app.py (Flask API) ──▶ static/ (web UI)
```

`RuleSet` (`src/engine/rules.py`) is the one thing every layer takes as an explicit parameter. There is no global "6 decks" or "S17" constant anywhere in the codebase — a new rule variant is a different `RuleSet` instance, never a branch on a format string.

---

## 2. The solver

### 2.1 Dealer outcome distribution (`src/strategy/dealer_probs.py`)

`dealer_distribution(upcard, comp, rules)` returns `P(17, 18, 19, 20, 21, BUST)` given the dealer's upcard and the shoe composition remaining after it. It's a straightforward recursion — draw each rank with probability `comp[r] / comp.sum()`, remove it, recurse until the dealer must stand (`total >= 17`, unless soft 17 and `rules.dealer_hits_soft_17`) — memoized on `(hard_total, is_soft, comp.tobytes())`.

### 2.2 Peek conditioning — the one bug that survives casual review

When `rules.dealer_peeks` is true and the upcard is a Ten or Ace, the dealer has already checked the hole card for blackjack before the player acts. The hole-card distribution used in every downstream calculation from that point on must be conditioned on "the dealer does not have blackjack": renormalise after zeroing the Ace (ten showing) or the Tens (Ace showing).

Skipping this produces a grid that is *almost* right — it typically only flips 16-vs-10 and 12-vs-4 — which is exactly why it's the most common blackjack-solver bug in the wild: it passes a casual glance. Phase 3's own verification caught this early (P(21) dropped from 11.19% unconditioned to 3.77% conditioned on a dealer-shows-Ten shoe), and Phase 5's cell-for-cell chart comparison exists specifically to catch it if it ever regresses.

### 2.3 Player action EVs (`src/strategy/ev_solver.py`)

- `ev_stand` — dot the dealer distribution against the payoff vector for the player's total.
- `ev_hit` — for each rank `r`: `P(r) × [bust ? −1 : max(ev_stand', ev_hit')]`. The `max` makes this *optimal-play* EV (every future decision is also optimal), not fixed-strategy EV.
- `ev_double` — for each rank `r`: `2 × P(r) × ev_stand(total + r)`. Exactly one card, no further action.
- `ev_surrender` — a constant `−0.5`, available only as a first action.
- `ev_split` — `2 × ev(one post-split hand, split card removed from shoe)`, allowing resplits up to `rules.resplit_to` and doubles iff `rules.double_after_split`.

**The split-EV approximation is deliberate, not a bug.** The two post-split hands actually draw from the same depleted shoe, so they aren't strictly independent — but `2 × one_hand_EV` is the standard treatment used by every published chart and by Griffin's *Theory of Blackjack*. The error is on the order of 0.01% and is *required* to match Appendix A; full joint enumeration would produce a solver that's more "correct" in isolation but disagrees with every published reference. See `ev_split_hand`'s docstring for the one real bug found here during Phase 5 (a missing 2× factor on the *resplit* candidate one level deeper than the top-level split) — that was a genuine arithmetic bug and got fixed; the top-level 2× approximation itself was not.

### 2.4 Composition mode

Two modes exist in the design (`mode="total_dependent"` vs `"composition_dependent"`), but **only `total_dependent` is actually implemented**. This is what produces the published charts and what Phase 5 validates against — hard totals are frequency-weighted over every valid non-pair 2-card decomposition (e.g. hard 12 = 2+10, 3+9, 4+8, or 5+7) rather than one arbitrary combo, since a single Ten-heavy decomposition was found (Phase 4) to flip hard-12-vs-4 against the published chart. `composition_dependent` mode (full exact removal of every visible card, giving the genuinely optimal play for a *specific* hand like `T,6` vs `9,7`) was scoped for the web UI's "exact mode" toggle but never built — the Play tab (Phase 11) documents this and doesn't expose a toggle for a mode that doesn't exist.

### 2.5 Caching

The solver is deterministic and expensive (a full grid solve is ~108s in pure Python), so it is **solved once per ruleset and cached to `data/strategy/{ruleset_key}.json`** — the running app never re-solves. Cache validity has no grandfather clause: every cached file records `{"_source_hash": ..., "_cache_key": {...}}` (`src/utils/cache_manager.py`), where `_source_hash` is a hash of `ev_solver.py` + `dealer_probs.py` + `grid_builder.py`'s current content. Any mismatch — including a pre-existing file with no manifest metadata at all — triggers a full rebuild, never a silent stale read. This is a direct lesson from `T20_Win_Probability_Model`, whose Elo caches drifted silently for a long time because a pre-existing file with no manifest entry was trusted blindly.

---

## 3. Where every published number comes from

Every anchor this repo's tests check the solver against is recorded once, here, rather than scattered as magic numbers across test files.

### 3.1 Basic-strategy chart (Appendix A of the build plan)

The 4/6/8-deck, S17, DAS, late-surrender, 3:2, dealer-peeks chart — the standard "multi-deck" basic strategy chart published in every mainstream blackjack strategy reference (e.g. Wong's *Professional Blackjack*, the Wizard of Odds strategy engine). `tests/test_strategy_grid.py` compares the solver's grid against it cell-for-cell for `{4, 6, 8} decks × {S17, H17}` (340 cells per ruleset). Documented, *expected* deviations exist for single/2-deck charts (fewer decks changes several cells, e.g. 2-deck S17 doubles hard 9 vs 2) and for H17 (six cells genuinely flip) — both encoded as separate fixtures rather than folded into the multi-deck comparison.

One cell remains a documented, investigated near-miss rather than a forced match: soft 18 vs 2 solves to Stand where the published chart shows Double (EV gap 0.003, `S=0.12400` vs `D=0.12098`). This was hand-traced (7 of 10 possible draws degrade soft 18 to a mediocre hard total against the dealer's weak 2; only 3 improve or hold it soft) and is genuinely close enough that it's plausible either answer is defensible depending on exact modelling choices — tracked in `KNOWN_NEAR_MISSES`, not silently patched.

### 3.2 House-edge anchors

| Decks | Published anchor | Source convention |
|---:|---:|---|
| 1 | ≈ 0.02% | S17, DAS, double-any-two, no surrender, 3:2, dealer peeks, standard multi-deck-style penetration |
| 2 | ≈ 0.19% | same |
| 4 | ≈ 0.35% | same |
| 6 | ≈ 0.40% | same |
| 8 | ≈ 0.43% | same |

These are the well-established published house-edge figures for this exact rule combination (the same convention quoted across Wizard of Odds' blackjack house-edge calculator and standard blackjack-appendix references). `src/strategy/exact_edge.py`'s `exact_house_edge()` — a full, zero-sampling-noise combinatorial enumeration over every possible initial deal, built directly on `ev_solver.py` — is compared against these with a flat ±0.02% tolerance (justified precisely *because* it's noise-free: there's no sampling error to account for, so a flat band is the right kind of tolerance). A Monte Carlo run through `game.py`'s actual mechanics is a *secondary* sanity check against the exact figure (not the published anchor), with a tolerance of `4×` its own standard error — this isolates "does `game.py` have an integration bug" from "does composition-dependent play differ slightly from a total-dependent chart's convention," which are different questions with different fixes.

Locked in `data/baselines/house_edge_baseline.json` (`exact_edge`, `simulated_edge`, `stderr`, and both pass/fail flags per deck count).

**A real measurement bug was found and fixed getting here** (see the build plan's Phase 5 detailed findings): the original all-Monte-Carlo version of this check spent most of a build session chasing what turned out to be pure sampling noise plus one stale non-fresh-shoe comparison. Switching to the zero-noise exact figure as the primary gate — rather than trying to brute-force more precision out of Monte Carlo — resolved it in one pass and is the reason the check is architected the way it is now.

### 3.3 Rule-effect deltas

| Rule change | Published delta | Solver's exact delta |
|---|---:|---:|
| H17 (vs S17) | ≈ −0.22pp | +0.2131pp (cost to the player) |
| No DAS (vs DAS) | ≈ −0.14pp | +0.1419pp |
| No surrender (vs late surrender) | ≈ −0.08pp | +0.0724pp |
| 6:5 payout (vs 3:2) | ≈ −1.39pp | +1.3597pp |
| Resplit aces (RSA) | ≈ +0.08pp | +0.0696pp |

These are the standard published marginal costs/benefits of each rule variant (the same figures documented as comments on `RuleSet`'s own fields in `src/engine/rules.py`). Re-deriving them from the solver (`exact_edge.py` computing the base case and the rule-flipped case, taking the difference) is a second, independent way to catch a rule-handling bug specifically (as opposed to Check 2's absolute-edge check, which would catch an arithmetic bug but not necessarily a mishandled rule flag) — one real bug (`resplit_aces` and `hit_split_aces` were incorrectly coupled, so `resplit_aces=True` had zero effect whenever `hit_split_aces=False`, the default) was found this way, not by any observed discrepancy in the other checks.

### 3.4 Illustrious 18 / Fab 4 / insurance index

The Illustrious 18 and Fab 4 are Don Schlesinger's well-known named subset of count-indexed basic-strategy deviations (the highest-value ones to memorize, from *Blackjack Attack*) — the specific true-count thresholds at which the optimal action for a hand flips as the shoe's composition shifts. `src/strategy/index_builder.py` re-derives each cell's flip point by re-solving the cell's EV at a count-perturbed shoe composition, sweeping true counts from −10 to +10. `tests/test_deviations.py` compares against the published thresholds with a **±1 true-count tolerance** — not because the derivation is imprecise, but because published tables themselves disagree by this much depending on which count-to-composition mapping was used to derive them (see §4). A cell off by ≥2 is treated as a real bug; ±1 is an honest gate, not a weakened one.

Insurance's own published threshold (take insurance at TC ≥ +3 for Hi-Lo) is re-derived directly from ten-density crossing 1/3, the standard insurance-correctness criterion, and checked the same way.

### 3.5 Edge-model fit (TC → player edge)

Not a published anchor in the same sense — this is *this project's own* simulated fit, not something being checked against an external reference. `data/baselines/edge_model_baseline.json` locks a 20,000,000-hand battery's result: `edge(TC) = intercept + slope × TC`, fit by weighted least squares over per-true-count-bucket means, restricted to the trusted fit range (buckets with too few hands, or too far outside the sampled range, are reported but excluded from the fit itself). The only "external" cross-check available is that its flat-bet (TC=0) edge matches `exact_house_edge()` for the same ruleset within a fraction of a standard error, which the battery's own verification run confirmed (gap 0.14 SE).

---

## 4. Count-to-composition mapping

A true count is a single scalar; a shoe composition is a 10-dimensional vector. Going from "true count +5" back to "what does the shoe actually look like" is therefore mathematically underdetermined — there is no unique answer, only a documented convention.

**This project's choice** (`implied_composition()` in `index_builder.py`): distribute the count's implied surplus/deficit **proportionally within each tag group**. Every rank tagged `+1` by the counting system shares the implied surplus proportionally to its neutral-shoe frequency; every rank tagged `−1` shares the deficit the same way; untagged ranks are left at their neutral proportion. For a balanced system this reduces to a single uniform scale factor `f = RC / (2A)` where `A` is the tag-weighted neutral sum over positive-tag ranks; the general (including unbalanced systems) form is `f = [RC + (A+B)] / (A−B)`.

This was verified by hand against a worked example (Hi-Lo, TC+5, 4 decks: "remove 10 low cards, add 10 high cards, split 8+2 across T/A proportionally") and reproduces it exactly. Using a *different* mapping — e.g. concentrating the entire adjustment on a single rank — is explicitly called out in `.agents/coding-standards.md` as the #1 cause of index tables silently disagreeing with the Illustrious 18 by more than the expected ±1 tolerance. If you're re-deriving indices and they don't match published values, check this first before suspecting the solver.

---

## 5. True-count rounding: two conventions, on purpose

`src/counting/counter.py` exposes both:

- **Betting decisions round toward zero (floor)** — conservative, so a rounding artifact never causes an overbet.
- **Playing decisions round to nearest** — matches how the Illustrious 18 itself is conventionally applied.

Mixing these — using one rounding rule where the other is expected — is the most common reason two otherwise-correct implementations disagree with each other by exactly ±1 index, without either being "wrong" in isolation. `deviations.advise()` always uses nearest; `app.py`'s `/api/stake` and the Bankroll tab always use floor. This split is explicit in the counter itself, not left to caller discipline.

---

## 6. Why half-Kelly

`src/bankroll/kelly.py`: `kelly_fraction(edge, variance, fraction) = fraction × edge / variance`, defaulting `fraction=0.5`.

Full Kelly (`fraction=1.0`) maximises long-run log growth, but it does so at the cost of brutal short-run volatility — roughly a 13.5% chance of the bankroll being cut in half before it's doubled, and drawdowns that are unbearable in practice even when the underlying edge is real and positive. Half-Kelly retains **75% of full Kelly's growth rate at roughly half the volatility** — a well-known result of the growth-rate curve `g(f) = f·edge − 0.5·f²·variance` being concave and fairly flat near its peak, so backing off from the peak costs proportionally less growth than it saves in variance.

There's a second, more project-specific reason, spelled out in the build plan's Phase 9 `[!IMPORTANT]`: **Kelly's guarantee assumes the edge estimate is correct.** A counter's edge estimate carries real uncertainty — from the edge-model fit itself, from deck-estimation error, and from the true count being an imperfect summary of the actual shoe composition. Overbetting relative to a *mis-estimated* edge is punished far more severely than underbetting the same amount. Half-Kelly is the standard hedge against exactly this — not conservatism for its own sake.

One genuinely counter-intuitive, *verified-not-hypothetical* finding from Phase 9's own testing against the real locked edge model: `bet_ramp.py`'s `RampLevel.ev_cost` (the growth-rate cost of snapping a continuous Kelly fraction down to the nearest 1/2/4/8/16-unit ramp level) is normally positive — snapping down from ≥1 unit always strictly loses some growth — but goes slightly *negative* at TC +1 specifically for this locked model, because the true edge there is small-but-positive (raw Kelly wants under 1 unit), and the mandatory table-minimum floor bet happens to land closer to the true full-Kelly peak than half-Kelly's own target does. This is a real, reproducible property of the growth curve for this specific fitted edge, not a bug — reported honestly rather than clamped to look tidier, per the project's "No Bare Point Estimates" convention.

---

## 7. The regression gate

`py tests/regression_test.py` (Phase 12) is the single command that answers "did anything actually move?" It checks four things, each against a fresh recomputation rather than trusting whatever's on disk:

1. **Grid cache freshness** — do the committed `data/strategy/*.json` files still carry a `_source_hash` matching the *current* solver source? A mismatch means someone edited the solver without re-running `scripts/build_all_grids.py` before committing.
2. **Grid vs Appendix A** — reuses `tests/test_strategy_grid.py`'s own fixture comparison directly (not duplicated).
3. **House edge** — `exact_house_edge()` recomputed fresh and compared to the locked baseline. This is a pure, deterministic function, so any drift at all here is real — the tolerance is far tighter than Phase 5's own correctness gate, because this check's job is "did the number move," not "is the number right" (Phase 5 already answered that). Outside `--fast`, also re-runs the Monte Carlo secondary sanity check.
4. **Count-indexed deviations** — the Illustrious 18 / Fab 4 / insurance index, re-derived and compared to published values, for the one ruleset+system combo that's actually shipped with a pre-built index cache (`6d-s17-das-ls-p75` / Hi-Lo).
5. **Edge model** — sanity-checks the locked `edge_model_baseline.json` loads and has a sane (positive) slope; outside `--fast`, cross-checks it against a fresh moderate-hand battery.

`--fast` (used by `.github/workflows/regression.yml` on every push/PR) skips everything that requires fresh Monte Carlo sampling, keeping CI to the deterministic, cheap checks. `--generate` / `--generate-ruleset <decks>` re-lock `house_edge_baseline.json` only — `edge_model_baseline.json` is a separate, ~70-minute artifact owned by `scripts/run_sim_battery.py --generate`, deliberately kept out of the fast/default path of this script.

Per `.agents/coding-standards.md`'s Regression Gate Discipline: once a baseline is locked, moving it requires (1) establishing the move as a correctness fix and writing down the mechanism, (2) recording before/after numbers in the build plan's tracking table, and (3) a deliberate `--generate-ruleset` re-lock — never a blanket `--generate` that silently absorbs unrelated drift.
