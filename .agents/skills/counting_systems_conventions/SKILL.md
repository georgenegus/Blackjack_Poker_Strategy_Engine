---
name: counting_systems_conventions
description: Triggers when working on card-counting systems, running/true count arithmetic, count-to-composition mapping, Monte Carlo simulation, or the edge model in src/counting/ and src/simulation/.
---

# Counting Systems & Simulation Conventions

Conventions for `src/counting/` (count arithmetic) and `src/simulation/` (Monte Carlo validation of the edge those counts imply).

## Tag Vectors

All systems are defined over the same 10-bucket rank index as the shoe composition (see `blackjack_rules_conventions`):

| System | Level | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A | Balanced |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Hi-Lo | 1 | +1 | +1 | +1 | +1 | +1 | 0 | 0 | 0 | −1 | −1 | ✅ |
| KO | 1 | +1 | +1 | +1 | +1 | +1 | +1 | 0 | 0 | −1 | −1 | ❌ |
| Hi-Opt I | 1 | 0 | +1 | +1 | +1 | +1 | 0 | 0 | 0 | −1 | 0 | ✅ |
| Hi-Opt II | 2 | +1 | +1 | +2 | +2 | +1 | +1 | 0 | 0 | −2 | 0 | ✅ |
| Omega II | 2 | +1 | +1 | +2 | +2 | +2 | +1 | 0 | −1 | −2 | 0 | ✅ |
| Zen | 2 | +1 | +1 | +2 | +2 | +2 | +1 | 0 | 0 | −2 | −1 | ✅ |
| Red 7 | 1 | +1 | +1 | +1 | +1 | +1 | ½* | 0 | 0 | −1 | −1 | ❌ |

\* Red Seven: red 7s count +1, black 7s count 0 — the only system needing suit colour.

Hi-Lo is the default (highest Betting Correlation among level-1 balanced systems, and what every published index table is quoted for). Hi-Opt I/II and Omega II count aces as 0 and need a side count of aces for betting accuracy — expose that explicitly, never silently mis-size bets by omitting it.

## Running Count / True Count

- Balanced systems (Hi-Lo, Hi-Opt I/II, Omega II, Zen) initialise `running_count = 0`.
- Unbalanced systems: KO's IRC is `−4 × (num_decks − 1)` (e.g. `−20` for 6 decks), pivoting at `+4`; these expose `running_count` only and must raise if `true_count` is requested — they are designed to be used without conversion.
- `true_count = running_count / decks_remaining`, `decks_remaining = (total_cards − dealt) / 52`, resolution configurable (default half-deck).
- **Rounding convention is explicit and split by use case**: `"floor"` for betting decisions (conservative — never overbets on a rounding artefact), `"nearest"` for playing decisions. Mixing these is the most common reason two "correct" implementations produce different bets or different index-play calls from the same shoe state.

## Verification Invariant

Dealing an entire balanced shoe must return the running count exactly to its IRC (0 for Hi-Lo). This is the definition of "balanced" and catches a tag-vector typo instantly — put it in `tests/test_counting.py` for every balanced system.

## Monte Carlo Simulation (`src/simulation/`)

- The simulator plays N shoes through the `src/engine/game.py` round engine with an injected `decide_fn`, recording per-hand: true count at bet time, amount wagered, net result, and whether the hand was doubled/split.
- `edge_model.py` buckets hands by true count and fits `edge(TC) = intercept + slope × TC`. Fit this **per `RuleSet`** — never hardcode "+0.5% per true count"; deck count and penetration both materially move the fit. Store per-bucket standard errors alongside the linear fit and be honest in the UI about extrapolating past the sampled range (default clamp: TC ∈ [−5, +8]).
- **No bare point estimates.** House edge, edge-vs-count slope, variance, risk of ruin, N₀ — every one of these is reported with its standard error, in test assertions, UI display, and documentation. Blackjack's ~1% edges with per-hand SD ~1.15–1.3 mean distinguishing real effects from Monte Carlo noise requires stating the uncertainty every time; see the build plan's Phase 8 `[!WARNING]` for the sample-size math.
- The simulator's flat-bet, basic-strategy house edge must reproduce Phase 5's locked solver-derived house edge within Monte Carlo standard error — this is the primary cross-check that the simulator and the solver agree, and it matters more than any other single simulation assertion.

## Memory Discipline

Long Monte Carlo batteries run on a 7.7GB dev machine. Standalone scripts (`scripts/run_sim_battery.py`) need an `if __name__ == "__main__":` guard, and any simulate-on-demand API endpoint (Phase 10's `/api/simulate`) must cap hands per request rather than accept an unbounded count.
