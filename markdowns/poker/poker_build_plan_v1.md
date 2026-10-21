# Texas Hold'em Strategy Engine — Build Plan v1

> **Author:** Claude Code (Opus 5) · **Date:** 2026-08-25  
> **Purpose / Strategy:** A No-Limit Hold'em engine that computes exact equities by enumeration and derives strategy by self-play regret minimisation (CFR+) rather than transcribing a chart — served through the existing Flask app as a second, strictly additive area alongside blackjack  
> **Baseline / Metrics:** Greenfield area in an existing repo. Correctness anchors: the evaluator must reproduce the published 7-card category counts *exactly* across all 133,784,560 hands; exact equities must match published matchup values to the last published digit; CFR must converge to Kuhn poker's analytic equilibrium (game value −1/18) and to a sequence-form LP solution of Leduc  
> **Defaults / Scope:** Heads-up and 6-max No-Limit Hold'em · 100bb default stacks · 0.5/1 blinds · 5% rake capped at 3bb · exact enumeration where tractable, Monte Carlo with standard errors where not · CFR+ with measured exploitability in mbb/g on every strategy shipped  
> **Structure basis:** Mirrors this repo's blackjack area (`markdowns/blackjack/blackjack_build_plan_v1.md`), which in turn mirrors `C:\Python\T20_Win_Probability_Model`

---

## Executive Summary

Build a **Texas Hold'em strategy engine** that is correct by construction rather than correct by transcription — the same thesis that drives the blackjack area of this repo, applied to a game where the answer is not a single action but a probability distribution over actions.

Almost every hold'em tool online ships a preflop chart copied from a training site and an equity calculator whose internals nobody checks. This project instead builds:

- An **exact hand evaluator**, verified not by spot-checking a few hands but by enumerating all C(52,7) = 133,784,560 seven-card hands and asserting the category counts match the published combinatorial values *exactly* — an all-or-nothing test that no subtly wrong evaluator survives.
- An **exact equity engine** that enumerates every runout when the runout count is small enough (C(48,5) = 1,712,304 preflop heads-up; 990 from the flop; 44 from the turn) and falls back to Monte Carlo **with a standard error attached** when it is not.
- A **CFR+ solver** whose output is a *mixed* strategy, validated first against toy games with a known analytic equilibrium (Kuhn poker, value −1/18) and an exact LP solution (Leduc), and then shipped with a **measured exploitability in mbb/g**.
- A **push/fold and ICM layer** for tournament spots, where the equilibrium is small enough to solve exactly and published Nash tables exist as a known-answer test.
- A **bankroll layer** that answers the question poker players actually get wrong: not "what is my edge" but "how long is a downswing that is still consistent with that edge".

> [!IMPORTANT]
> **The deepest difference from the blackjack engine: the answer is a distribution, not an argmax.** Blackjack's solver produces one correct action per cell, and a chart that disagrees is wrong. A Nash strategy for hold'em routinely says "raise 62%, call 38%", and both of those are correct. Any layer that rounds a mixed strategy to a pure one — the cache format, the API response, the UI cell — is discarding the actual answer. Carry frequencies from the start; retrofitting them later means rewriting the artifact format, the API contract, and the UI simultaneously.

> [!CAUTION]
> **Phases 5 and 8 are the two go/no-go gates.** Phase 5 proves the evaluator and equity engine are exact. Phase 8 proves the solver actually converges to equilibrium on games where the equilibrium is independently known. Everything downstream — preflop charts, push/fold ranges, the trainer's "EV lost" score, every number in the UI — is a consequence of those two. An evaluator wrong on 0.001% of hands, or a CFR implementation with a sign error in the regret update, produces output that looks entirely plausible and is entirely worthless.

### Non-Destructive Principle

This area is **strictly additive to an existing, validated repo.** The blackjack engine is frozen behind `data/baselines/` and its regression gate currently passes; nothing in this plan may move it.

- **Zero modifications** to `src/engine/`, `src/strategy/`, `src/counting/`, `src/simulation/`, `src/bankroll/`, or `tests/regression_test.py`.
- All new code lives under `src/poker/`, all new data under `data/poker/`, all new tests under `tests/poker/`.
- **Exactly one** permitted edit to an existing source file: `app.py` gains one import and one `register_blueprint()` call (Phase 12). Poker routes live in `src/poker/api.py` as a Flask Blueprint, not inline in `app.py`.
- `py tests/regression_test.py --fast` must stay green after **every** phase of this plan, and is part of each phase's verification block, not just the final one.
- Shared infrastructure is **reused read-only**: `src/utils/cache_manager.py`'s hash-validated cache pattern is imported, not copied and not edited.

### Phase Overview

| # | Phase | Tier | Effort | Files Created |
|---|-------|------|:------:|---------------|
| 0 | Area Bootstrap & Agent Docs | Infrastructure | 🟢 Low | `.agents/skills/poker_*/SKILL.md`, `src/poker/__init__.py` |
| 1 | Card Primitives + `GameSpec` | Infrastructure | 🟢 Low | `src/poker/cards.py`, `src/poker/spec.py` |
| 2 | Exact Hand Evaluator | Core Math | 🔴 High | `src/poker/evaluator.py` |
| 3 | Equity Engine (exact + MC) | Core Math | 🟡 Medium | `src/poker/equity.py` |
| 4 | Ranges, Combos & Card Removal | Core Logic | 🔴 High | `src/poker/ranges.py` |
| 5 | **Validation Gate I** — Evaluator + Equity | Validation Gate | 🔴 High | `tests/poker/test_evaluator.py`, `test_equity.py`, `data/poker/baselines/*.json` |
| 6 | Betting Tree & Abstraction | Core Logic | 🔴 High | `src/poker/tree.py`, `src/poker/abstraction.py` |
| 7 | CFR+ Solver | Core Math | 🔴 High | `src/poker/cfr.py` |
| 8 | **Validation Gate II** — Exploitability + Toy Games | Validation Gate | 🔴 High | `src/poker/exploit.py`, `src/poker/toy.py`, `tests/poker/test_toy_games.py` |
| 9 | Push/Fold Equilibrium & ICM | Core Math | 🟡 Medium | `src/poker/pushfold.py`, `src/poker/icm.py` |
| 10 | Preflop Solve & Strategy Artifacts | Core Math | 🔴 High | `scripts/poker/solve_preflop.py`, `src/poker/advisor.py` |
| 11 | Bankroll, Variance & Risk of Ruin | Core Logic | 🟢 Low | `src/poker/bankroll.py` |
| 12 | Flask API Blueprint | Integration | 🟡 Medium | `src/poker/api.py` (+2 lines in `app.py`) |
| 13 | Web UI (Equity · Ranges · Preflop · Solver · Bankroll · Trainer) | Integration | 🔴 High | `static/poker.html`, `static/js/poker/*.js` |
| 14 | Regression Harness & CI | Validation Gate | 🟡 Medium | `tests/poker/regression_test.py`, CI job |

Effort key: 🟢 Low Effort / Low Risk · 🟡 Medium Effort / Medium Risk · 🔴 High Effort / Critical Priority

---

## Repository Structure

Additive layout inside the existing `C:\Python\Cards` repo. Nothing outside the marked-`NEW` paths is touched except the three append-only docs and `app.py`.

```
C:\Python\Cards\
│
├── .agents/
│   ├── instructions.md               [MODIFY — append a "Poker Area" section only]
│   ├── project-overview.md           [MODIFY — append poker rows to the key-files table]
│   └── skills/
│       ├── poker_evaluator_conventions/SKILL.md    [NEW] Rank encoding, 7462 classes, tie handling
│       ├── poker_range_conventions/SKILL.md        [NEW] 169-grid notation, combo weights, blockers
│       └── poker_solver_conventions/SKILL.md       [NEW] CFR variants, exploitability units, abstraction
│
├── src/poker/                        [NEW] The whole engine — no edits outside this tree
│   ├── __init__.py                   [Phase 0]
│   ├── cards.py                      [Phase 1] 52-card encoding, bitmasks, suit isomorphism
│   ├── spec.py                       [Phase 1] GameSpec dataclass — THE single source of truth
│   ├── evaluator.py                  [Phase 2] Exact 5/6/7-card evaluator → 7462 rank classes
│   ├── equity.py                     [Phase 3] Exact enumeration + MC with standard errors
│   ├── ranges.py                     [Phase 4] 169-grid parsing, combo expansion, card removal
│   ├── tree.py                       [Phase 6] Betting tree built from GameSpec, never hardcoded
│   ├── abstraction.py                [Phase 6] Card bucketing + bet-size discretisation
│   ├── cfr.py                        [Phase 7] CFR+ / Discounted CFR / external-sampling MCCFR
│   ├── exploit.py                    [Phase 8] Best response, exploitability in mbb/g
│   ├── toy.py                        [Phase 8] Kuhn + Leduc, with sequence-form LP reference
│   ├── pushfold.py                   [Phase 9] Jam/fold equilibrium by fictitious play
│   ├── icm.py                        [Phase 9] Malmuth-Harville ICM, bubble factor
│   ├── advisor.py                    [Phase 10] Runtime lookup: spot → action frequencies + EV
│   ├── bankroll.py                   [Phase 11] RoR, downswing quantiles, stake selection
│   └── api.py                        [Phase 12] Flask Blueprint — all /api/poker/* routes
│
├── data/poker/                       [NEW]
│   ├── evaluator/                    [Phase 2] Lookup tables                     ← GITIGNORED (~124MB, regenerable)
│   ├── equity/preflop_169x169.npy    [Phase 3] Preflop equity matrix             ← COMMITTED (~350KB)
│   ├── ranges/*.json                 [Phase 4] Named reference ranges            ← COMMITTED
│   ├── strategy/{spec_key}/*.json    [Phase 10] Solved strategies + frequencies  ← COMMITTED
│   ├── baselines/                    [Phase 5/8/10] Locked regression baselines  ← COMMITTED
│   │   ├── evaluator_baseline.json
│   │   ├── equity_baseline.json
│   │   ├── toy_game_baseline.json
│   │   └── preflop_baseline.json
│   └── solves/                       [Phase 7] Raw CFR checkpoints               ← GITIGNORED
│
├── tests/poker/                      [NEW]
│   ├── regression_test.py            [Phase 14] THE poker gate
│   ├── test_evaluator.py             [Phase 5] Full C(52,7) category-count enumeration
│   ├── test_equity.py                [Phase 5] Published matchups + exact identities
│   ├── test_ranges.py                [Phase 4] Combo counts, blockers, removal
│   ├── test_toy_games.py             [Phase 8] Kuhn analytic + Leduc LP
│   ├── test_pushfold.py              [Phase 9] Nash jam/call vs published tables
│   └── test_bankroll.py              [Phase 11] RoR, CI width, downswing
│
├── scripts/poker/                    [NEW]
│   ├── build_evaluator_tables.py     [Phase 2] Generate the lookup tables
│   ├── build_preflop_equity.py       [Phase 3] The 169×169 matrix (long-running)
│   ├── solve_preflop.py              [Phase 10] CFR preflop solve per GameSpec
│   └── solve_spot.py                 [Phase 10] Bounded postflop solve for one spot
│
├── static/                           [Phase 13]
│   ├── poker.html                    [NEW] Second SPA entry point
│   ├── css/poker.css                 [NEW]
│   └── js/poker/{app,equity,ranges,preflop,solver,bankroll,trainer}.js  [NEW]
│
├── docs/poker_guide.md               [Phase 14] Deep walkthrough
├── markdowns/poker/                  This plan
└── app.py                            [MODIFY — exactly 2 lines: import + register_blueprint]
```

> [!NOTE]
> **Why the evaluator tables are gitignored but the equity matrix is committed.** The 7-card lookup table is ~124MB and deterministically regenerable in minutes from `build_evaluator_tables.py` — the same reasoning that gitignores `data/sims/` on the blackjack side. The 169×169 preflop equity matrix is ~350KB, takes hours to build, and is needed at runtime by the API, so it is committed, exactly as `data/strategy/*.json` is.

---

## Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `numpy` | Vectorised evaluation and enumeration — **not optional here** | *(installed)* |
| `flask` | Already present — the poker Blueprint mounts into the existing app | *(installed)* |
| `pytest` | Test runner for both gates | *(installed)* |
| `scipy` | `linprog` for Phase 8's sequence-form LP; also `cluster.vq.kmeans2` for Phase 6's flop+ card abstraction | *(installed)* |
| `pandas` | Solve-result aggregation, range tabulation | *(installed)* |
| `numba` | JIT for `src/poker/evaluator.py`'s batch evaluator (added in Phase 3, not merely reserved for Phase 7's CFR loop — see below) | *(installed)* |

`numpy` moves from "core" to "load-bearing". The blackjack solver's hot path is a memoised recursion over a 10-element composition vector; poker's hot path is evaluating tens of millions of seven-card hands. A pure-Python evaluator is roughly 10⁴× too slow for Phase 5's full enumeration, and there is no cache-first escape hatch — **the enumeration is the test**.

> [!NOTE]
> `numba` was planned as optional, reserved for Phase 7's CFR inner loop if numpy proved too slow there. In practice it was needed two phases earlier: `evaluate_batch`'s pure-numpy vectorisation (still shipped, as the fallback when numba is unavailable) measured ~235k hands/sec, which put the Phase 3 preflop-equity-matrix build — ~14,365 class pairs × ~3.4 average distinct suit-shapes per pair, one full 1,712,304-runout exact enumeration per shape — at an estimated **~8.4 days**. A `numba(parallel=True)` kernel for the same 7-card evaluation measured **~6.9M hands/sec** (a ~29× speedup, using all cores via `prange`), bringing the same build to a measured ~1.7s/shape, an estimated **~23 hours** total. `requirements.txt` now lists it as a real dependency rather than an optional one; the pure-numpy path stays in `evaluator.py` as a fallback so the module still imports and works (just far slower) if `numba` is ever unavailable.

`scipy` is a genuine dependency, needed two phases earlier than originally planned: Phase 6's flop+ card abstraction uses `scipy.cluster.vq.kmeans2` for bucket clustering, not just Phase 8's LP. For Phase 8 itself, it remains essential rather than a nicety — CFR converging to *something* is not evidence it converged to *equilibrium*; the LP gives an independent, exact answer on the toy games to compare against.

> [!WARNING]
> The dev machine has **7.7GB RAM** (`.agents/coding-standards.md`). Three places in this plan will exhaust it if written naively: the 7-card lookup table (~124MB as `int32`, but 900MB+ if built as a Python list of boxed ints); Phase 5's full C(52,7) enumeration (must be chunked, never materialised as one array alongside its evaluated copy); and Phase 7's CFR regret tables (bounded by the abstraction, which is the reason Phase 6 exists). Every standalone script needs the `if __name__ == "__main__":` guard the repo already requires for Windows `spawn`.

---

## Phase Execution Order

```
Phase 0: Area Bootstrap & Agent Docs
    │
    ▼
Phase 1: Card primitives + GameSpec
    │
    ▼
Phase 2: Exact Hand Evaluator
    │
    ▼
Phase 3: Equity Engine (exact + MC)
    │
    ▼
Phase 4: Ranges, Combos & Card Removal
    │
    ▼
Phase 5: VALIDATION GATE I  ←──── GO / NO-GO
    │      category counts exact?  equities match published?
    │
    ├──────────────┬───────────────────┐
    ▼              ▼                   ▼
Phase 6:       Phase 9:            Phase 11:
Tree +         Push/Fold + ICM     Bankroll
Abstraction    (needs only 3-5)    (independent)
    │              │                   │
    ▼              │                   │
Phase 7: CFR+      │                   │
    │              │                   │
    ▼              │                   │
Phase 8: VALIDATION GATE II  ←──── GO / NO-GO
    │      Kuhn == −1/18?  exploitability → 0?
    │              │                   │
    ▼              │                   │
Phase 10: Preflop solve + advisor      │
    │              │                   │
    └──────────────┴───────────────────┘
                   │
                   ▼
            Phase 12: Flask API Blueprint
                   │
                   ▼
            Phase 13: Web UI
                   │
                   ▼
            Phase 14: Regression harness + CI
```

> [!CAUTION]
> Phase 9 (push/fold) deliberately depends on Phase 5 and **not** on Phase 8. The jam-or-fold game is small enough to solve by fictitious play over exact equities with no abstraction and no tree machinery, and it has published Nash tables to check against. That makes it the cheapest available early proof that the equity layer is sound in a *strategic* setting rather than merely an arithmetic one — build it while Phases 6–8 are in progress, not after.

---

## Phase 0: Area Bootstrap & Agent Docs

**Files:** `.agents/skills/poker_*/SKILL.md`, `src/poker/__init__.py`, `data/poker/`, `tests/poker/`, `scripts/poker/` (NEW); `.agents/instructions.md`, `.agents/project-overview.md`, `CLAUDE.md` (MODIFY — append only)  
**Priority:** 🟢 Low — mechanical, but it fixes conventions everything else inherits  
**Dependencies:** None

### Problem

This repo's real asset is its agent-documentation contract: `CLAUDE.md` → `.agents/instructions.md` → `project-overview.md` → `coding-standards.md` → the build plan. A second area added without extending that chain means a future session reads "this is a blackjack repo" and either ignores `src/poker/` entirely or, worse, refactors across the boundary and moves a locked baseline.

### Implementation

1. **Create the skeleton** — `src/poker/__init__.py`, `data/poker/{evaluator,equity,ranges,strategy,baselines,solves}/`, `tests/poker/`, `scripts/poker/`, each with a `.gitkeep` where empty.

2. **Extend `.gitignore`** (append only — do not restructure the existing entries):

   ```gitignore
   data/poker/evaluator/    # ~124MB lookup tables, deterministically regenerable
   data/poker/solves/       # raw CFR checkpoints, large and regenerable
   ```

3. **Write three new skills** under `.agents/skills/`, mirrored into `.claude/skills/` exactly as the existing five are:
   - `poker_evaluator_conventions` — rank encoding direction (lower value = stronger, or the reverse; pick one, document it, never flip it), the 7,462 equivalence classes, ties are *exact integer equality* and score 0.5.
   - `poker_range_conventions` — the 169-grid notation (`AKs`, `AKo`, `TT+`, `A5s-A2s`), combo counts (6 / 4 / 12), weighted ranges, blocker semantics.
   - `poker_solver_conventions` — CFR+ vs vanilla, exploitability always in mbb/g, "abstraction exploitability is a convergence diagnostic, not a real-game bound".

4. **Append to `.agents/instructions.md`** a "Poker Area" section carrying the two headline rules (Phase 1 and Phase 7 below), and to `project-overview.md` a poker block in the key-files table. Append; do not rewrite the blackjack content.

5. **Append to `CLAUDE.md`** a one-paragraph pointer to this plan, plus the standing note that `src/poker/` is additive and the blackjack gate must stay green.

### Verification

```bash
py -c "import src.poker; print('ok')"
py tests/regression_test.py --fast
git status --short
```
Expected: `ok`; the blackjack gate still reports `ALL BASELINES PASS`; `git status` shows only new files under the paths listed above plus append-only diffs to the three docs.

---

## Phase 1: Card Primitives + `GameSpec`

**Files:** `src/poker/cards.py`, `src/poker/spec.py` (NEW)  
**Priority:** 🟢 Low  
**Dependencies:** Phase 0

### Problem

Every later phase needs one shared vocabulary for "which cards" and "what game". Getting `GameSpec` wrong means threading stack depth, rake, and bet sizes through as ad-hoc arguments later — the exact trap `RuleSet` exists to avoid on the blackjack side, and the reason that side ships 32 rule variants without a single `if decks == 6`.

### Implementation

**1. `cards.py` — encoding.** Poker cares about rank *and* suit, so unlike blackjack there is no bucket collapse. Use an integer 0–51 with `rank = card // 4`, `suit = card % 4`, plus a 52-bit mask representation for O(1) conflict checks:

```python
RANKS = "23456789TJQKA"      # index 0..12, ace high
SUITS = "cdhs"               # index 0..3
def card_id(s: str) -> int:  # "As" -> 51
    return RANKS.index(s[0]) * 4 + SUITS.index(s[1])
def mask(cards) -> int:      # bitmask for conflict checks and blockers
    return sum(1 << c for c in cards)
```

**2. Suit isomorphism.** Two boards differing only by a relabelling of suits are strategically identical, and canonicalising them is what makes flop-level work tractable:

| Object | Raw count | Distinct up to suit isomorphism |
|---|---:|---:|
| Starting hands | C(52,2) = 1,326 | **169** |
| Flops | C(52,3) = 22,100 | **1,755** |

`canonical_board(cards)` must map all 22,100 flops onto exactly 1,755 classes — a hard, exact identity, and the cheapest test in Phase 5.

**3. `spec.py` — `GameSpec`.** A frozen dataclass, the single source of truth, playing the role `RuleSet` plays for blackjack:

| Field | Type | Default | Why it matters |
|---|---|---|---|
| `num_players` | `int` | `2` | Heads-up vs 6-max changes the tree and every range |
| `stack_bb` | `float` | `100.0` | The single biggest driver of preflop strategy |
| `sb` / `bb` | `float` | `0.5` / `1.0` | Pot-odds baseline |
| `ante_bb` | `float` | `0.0` | Antes widen every range materially |
| `bb_ante` | `bool` | `False` | Big-blind ante vs per-player ante — different starting pots |
| `rake_pct` | `float` | `0.05` | Rake shifts break-even opens; ignoring it is a modelling error, not a simplification |
| `rake_cap_bb` | `float` | `3.0` | Caps the above, making rake regressive in big pots |
| `no_flop_no_drop` | `bool` | `True` | No rake if the hand ends preflop — changes preflop EV directly |
| `bet_sizes` | `tuple[float, ...]` | `(0.33, 0.5, 0.75, 1.0, 1.5)` | Fractions of pot — **the betting abstraction lives here, not in `tree.py`** |
| `allow_allin` | `bool` | `True` | All-in is always a legal abstraction action |
| `raise_cap` | `int \| None` | `None` | Limit-style cap; `None` = no-limit |
| `variant` | `str` | `"nlhe"` | `"nlhe"` / `"lhe"` — reserved for a limit tree |

- `GameSpec.key()` → a deterministic short string (e.g. `hu-100bb-r5c3-s5`), used as the directory name for every cached solve and as the cache-manifest key, exactly as `RuleSet.key()` is used for `data/strategy/`.
- `GameSpec.pot_after_rake(pot_bb, saw_flop)` — the single place rake is ever applied. No other module computes rake.

> [!IMPORTANT]
> **The headline rule for this area, and the direct analogue of blackjack's "every EV is a function of a `RuleSet`":** every equity, EV, frequency and exploitability figure is a function of an explicit `(GameSpec, Range)` pair. No function may hardcode 100bb, heads-up, rake-free, or a bet-size grid. A new game type is a different `GameSpec`, never a branch on a string scattered through `src/poker/`.

> [!NOTE]
> `bet_sizes` living in `GameSpec` rather than in the tree builder is deliberate and worth defending: the betting abstraction is not an implementation detail of the solver, it is **part of the definition of the game being solved**. A strategy solved with `(0.5, 1.0)` and one solved with `(0.33, 0.75, 1.5)` are answers to different games and must land in different cache directories. Burying the sizes in `tree.py` makes two incomparable solves collide on the same cache key — the same class of bug as an unversioned cache, which this repo has already paid for once.

### Verification

```bash
py -c "from src.poker.cards import card_id, canonical_board; from itertools import combinations; \
print(card_id('As')); print(len({canonical_board(c) for c in combinations(range(52), 3)}))"
py -c "from src.poker.spec import GameSpec; s=GameSpec(); print(s.key(), s.pot_after_rake(20.0, True))"
```
Expected: `51`; then **`1755`** exactly — not 1,754, not 1,756. Then a stable key string and `19.0` (5% of a 20bb pot is 1.0bb, under the 3bb cap).

---

## Phase 2: Exact Hand Evaluator

**Files:** `src/poker/evaluator.py`, `scripts/poker/build_evaluator_tables.py` (NEW)  
**Priority:** 🔴 Critical — **every number in the project is downstream of this one function**  
**Dependencies:** Phase 1

### Problem

`evaluate(seven_cards) -> int` must order any two hands correctly across all 133,784,560 seven-card hands, with ties being *exactly* equal. Equity, CFR payoffs, and the trainer's EV-loss score are all consequences. An evaluator wrong on one hand in 10⁵ produces equities wrong in the third decimal — invisible to inspection, and fatal to every solve built on them.

### Implementation

**1. Rank space.** There are exactly **7,462 distinct five-card hand values** in hold'em. Map every hand to an integer in `[0, 7462)` where a lower value is stronger (or higher — pick one, document it in the skill file, never flip it). Seven-card hands collapse onto the same 7,462 classes, because a seven-card hand's value *is* the value of its best five-card subset.

**2. Two implementation strategies, in order of preference:**

*Strategy A — 5-card perfect hash over 21 subsets (build this first).* Cactus-Kev style: encode each rank as a prime, take the product of five cards, look up a perfect-hash table of 7,462 values. For a seven-card hand, evaluate all C(7,5) = 21 subsets and take the best. Simple, obviously correct, ~124MB smaller than Strategy B, and vectorises acceptably.

*Strategy B — 7-card DAG lookup (escalate only if A is too slow).* A 32,487,834-entry `int32` array walked with exactly seven array indexings per hand, no subset loop. Roughly an order of magnitude faster.

Ship A as the reference and B as the fast path, and **assert they agree on all 133,784,560 hands in Phase 5**. Two independently-derived implementations agreeing exactly is far stronger evidence than either one agreeing with a handful of hand-checked examples.

**3. Vectorised interface.** The equity engine calls this with millions of boards at once:

```python
def evaluate_batch(hands: np.ndarray) -> np.ndarray:
    """hands: (N, 7) int8 card ids -> (N,) int32 rank class, lower = stronger."""
```

**4. Category extraction.** `category(rank_class) -> HandCategory`, for display and for Phase 5's counting test. The nine categories and their exact counts are in Appendix A.

> [!CAUTION]
> **Ties are the silent killer, and Phase 5's category counts will not catch them.** A split pot is worth exactly 0.5, not 0 and not 1, and two hands tie iff their rank classes are *equal integers* — never "within epsilon", never "same category". Board-plays cases (the best five cards are all on the board) are common enough to matter and are exactly where a hand-rolled comparator that breaks ties on hole cards goes wrong. Tie handling lives in the *comparator*, not the evaluator, so it needs its own explicit tests.

> [!WARNING]
> Do not build the lookup table as a Python `list` of ints — CPython boxes each at ~28 bytes, turning a 124MB table into 900MB+ and OOMing the 7.7GB dev machine. Build into a preallocated `np.zeros(N, dtype=np.int32)` and persist with `np.save` to `data/poker/evaluator/` (gitignored).

### Verification

```bash
py scripts/poker/build_evaluator_tables.py
py -c "from src.poker.evaluator import evaluate; from src.poker.cards import card_ids; \
print(evaluate(card_ids('AsKsQsJsTs2c3d')) < evaluate(card_ids('AcAdAhAs2c3d4h')))"
py -c "from src.poker.evaluator import distinct_five_card_values; print(distinct_five_card_values())"
```
Expected: `True` (royal flush beats quads under the lower-is-stronger convention); then **`7462`** exactly — computed by enumerating all C(52,5) = 2,598,960 hands and counting the unique classes returned.

---

## Phase 3: Equity Engine (Exact + Monte Carlo)

**Files:** `src/poker/equity.py`, `scripts/poker/build_preflop_equity.py` (NEW)  
**Priority:** 🟡 Medium  
**Dependencies:** Phase 2

### Problem

Equity is the probability of winning at showdown given the currently known cards, counting ties as fractional wins. It is the input to every all-in decision, the terminal value of every solved tree, and the number the UI shows most often. It must be *exact* wherever exactness is affordable, and honest about its error where it is not.

### Implementation

**1. Choose exact vs sampled by counting the runouts, not by guessing.** The enumeration sizes are small and known:

| Spot | Known cards | Runouts to enumerate | Exact? |
|---|---:|---:|:---:|
| Preflop, 2 players | 4 | C(48,5) = **1,712,304** | ✅ |
| Preflop, 3 players | 6 | C(46,5) = **1,370,754** | ✅ |
| Flop, 2 players | 7 | C(45,2) = **990** | ✅ |
| Turn, 2 players | 8 | **44** | ✅ |
| Range vs range, preflop | — | up to 1,326² × C(48,5) | ❌ sample |

Rule: **enumerate whenever the runout count is below a configurable `EXACT_LIMIT` (default 5,000,000); otherwise sample.** Never sample a spot that could have been enumerated — a Monte Carlo estimate of a number the machine could compute exactly is a self-inflicted error bar.

**2. Exact enumeration, vectorised.** Generate runouts as `(N, board_len)` arrays *in chunks* (never materialise 1.7M × 7 alongside its evaluated copy), concatenate each player's hole cards, `evaluate_batch`, reduce:

```python
def equity_exact(hands, board, spec) -> np.ndarray:
    """-> (n_players,) equities summing to exactly 1.0; ties split fractionally."""
```

**3. Monte Carlo with a mandatory standard error.** `equity_mc(hands, board, n, seed) -> (equities, standard_errors)`. For a binomial share, `SE = sqrt(p(1-p)/n)`:

| Samples | SE at p ≈ 0.5 | 95% CI half-width |
|---:|---:|---:|
| 10,000 | 0.50% | ±0.98% |
| 100,000 | 0.158% | ±0.31% |
| 1,000,000 | 0.050% | ±0.098% |

> [!IMPORTANT]
> This repo's **"no bare point estimates from Monte Carlo"** rule (`.agents/instructions.md`) applies here unchanged. `equity_mc` returns a tuple and there is deliberately **no single-value convenience wrapper** — not because callers can't be trusted, but because a signature that makes the error optional guarantees it gets dropped somewhere between the solver and the UI. The blackjack area already learned this; do not relearn it.

**4. The 169×169 preflop matrix.** `build_preflop_equity.py` computes exact equity for every ordered pair of the 169 starting-hand classes, weighted correctly across the suit configurations consistent with each pair. This weighting is not a rounding detail: whether two hands share suits moves AA vs KK by roughly 0.7 percentage points. Output `data/poker/equity/preflop_169x169.npy`, shape `(169, 169, 3)` float32 for win/tie/lose. Budget a few hours; it is built once and committed.

**5. Equity distribution, not just the mean.** For a hand against a range, the *distribution* of equity across runouts is what determines whether it wants to bet, check-call, or check-fold. `equity_distribution(hand, rng, board, spec)` returns the histogram; the UI's most useful chart is built on it, and a mean equity with no distribution behind it is what makes players call off with the wrong 55%.

> [!CAUTION]
> **Equity is not EV.** Equity is the showdown share of the *current* pot assuming all cards run out with no further betting. EV includes future streets, fold equity, and the cost of realising equity out of position. A hand with 55% equity that cannot realise it is not a 55% hand. Every API field and UI label must say which one it is showing — this is a naming-discipline problem rather than a maths problem, and it is the most common way a poker tool misleads its user.

### Verification

```bash
py -c "from src.poker.equity import equity_exact; from src.poker.cards import card_ids; \
e = equity_exact([card_ids('AsAh'), card_ids('KsKh')], [], None); print(e, e.sum())"
py -c "from src.poker.equity import equity_exact; from src.poker.cards import card_ids; \
print(equity_exact([card_ids('AsKs'), card_ids('QhQd')], [], None))"
```
Expected: AA ≈ **0.819** vs KK ≈ 0.181 for that specific two-shared-suits configuration, summing to **exactly 1.0** (float equality — the enumeration is a complete partition, so anything else is a bug, not a rounding artefact). AKs vs QQ ≈ **0.462**. Appendix A carries the full anchor table and the suit-configuration caveat.

---

## Phase 4: Ranges, Combos & Card Removal

**File:** `src/poker/ranges.py` (NEW)  
**Priority:** 🔴 High — small file, disproportionate blast radius  
**Dependencies:** Phase 1 (testable against Phase 3 as soon as both exist)

### Problem

Poker strategy is about ranges, not hands, and a range is not a set — it is a **weighted distribution over the 1,326 specific two-card combinations**, conditioned on every card already visible. Getting that conditioning wrong is this area's equivalent of the blackjack solver's missing peek conditioning: the answer comes out *almost* right, looks plausible, and is wrong precisely where the decision is close.

### Implementation

**1. Notation and expansion.** Parse the standard grid notation into weighted combos:

| Class | Classes | Combos each | Total |
|---|---:|---:|---:|
| Pairs (`AA`–`22`) | 13 | 6 | 78 |
| Suited (`AKs`–`32s`) | 78 | 4 | 312 |
| Offsuit (`AKo`–`32o`) | 78 | 12 | 936 |
| **Total** | **169** | | **1,326** = C(52,2) |

Support `TT+`, `A5s-A2s`, `KQo`, explicit combos (`AsKd`), and weights (`AJs:0.5`). A range that plays a hand half the time is the *normal* case in a solved strategy, not an exotic one — weights are a first-class field, not an optional decoration.

**2. Card removal — the part that must be right.**

```python
def conditioned(rng: Range, blockers: int) -> Range:
    """Drop every combo conflicting with `blockers`, then RENORMALISE the weights."""
```

**3. Range-vs-range equity done correctly.** Iterate over ordered pairs of combos `(a, b)` drawn from the two ranges, **skipping pairs that share a card**, weight each pair by `w_a × w_b`, and normalise by the sum of the weights actually used — not by the product of the unconditioned range sizes.

> [!CAUTION]
> **The naive range-vs-range calculation is this area's peek-conditioning bug.** Averaging each combo's equity-against-the-unconditioned-range and then weighting by the combo's own weight double-counts the mass of hands your own cards block. The error is typically 0.5–2 percentage points; it is largest exactly in blocker-heavy spots (ace-high boards, river bluff-catches, ace-blocker jams) — which is to say in exactly the spots where the decision is close; and a number that is off by 1% looks entirely reasonable to a reviewer. Compute it as a joint sum over non-conflicting combo pairs, and make Phase 5 test a spot where the two methods provably disagree.

**4. Named reference ranges** in `data/poker/ranges/*.json` — standard opening ranges by position, calling ranges, and a `random` range (all 1,326 combos at weight 1). These are **inputs and UI conveniences, not answers**: Phase 10 derives its own ranges from the solver, and where the two disagree, the solver wins — once Phase 8 has passed. This is the same standing relationship the blackjack area has with published basic-strategy charts.

**5. Range arithmetic** — union, intersection, difference, scalar reweighting, plus `combos()` and `percent_of_hands()` for display.

### Verification

```bash
py -c "from src.poker.ranges import Range; print(Range('100%').n_combos())"
py -c "from src.poker.ranges import Range; from src.poker.cards import mask, card_ids; \
r = Range('AA'); print(r.n_combos(), r.conditioned(mask(card_ids('As'))).n_combos())"
py -m pytest tests/poker/test_ranges.py -q
```
Expected: **`1326`**; then `6` → **`3`** (holding the A♠ removes three of AA's six combos). The test file must additionally assert that joint-pair range-vs-range equity differs from the naive per-combo average by more than 0.5pp on at least one constructed spot — if it does not, the naive path was never implemented differently and the test proves nothing.

---

## Phase 5: Validation Gate I — Evaluator + Equity

**Files:** `tests/poker/test_evaluator.py`, `tests/poker/test_equity.py`, `data/poker/baselines/{evaluator,equity}_baseline.json` (NEW)  
**Priority:** 🔴 Critical — **GO / NO-GO**  
**Dependencies:** Phases 2–4

### Problem

The evaluator is either exact or it is subtly, invisibly wrong, and from the inside those look identical. Unlike the blackjack solver — whose known-answer test is a published chart that is itself a transcription — poker's evaluator has a *combinatorial* known answer requiring no external source and admitting no tolerance: the number of seven-card hands in each category is a fact about C(52,7), not a figure someone published.

### Implementation

**Check 1 — Full C(52,7) category enumeration.** Enumerate all **133,784,560** seven-card hands, classify each by its best five, and assert the nine counts match Appendix A **exactly**. A hard equality test, no tolerance:

- Runtime is the only concern. With the Strategy B lookup table and chunked numpy this is a few minutes; in pure Python it is hours. Mark it `@pytest.mark.slow`, run a deterministic 1-in-64 stratified subsample in `--fast` mode, and require the full enumeration in the full gate.
- The counts must sum to exactly 133,784,560, a free internal consistency check that catches an off-by-one in the *enumerator* rather than the evaluator.

**Check 2 — Two independent evaluators agree.** Run Strategy A and Strategy B over the same enumeration and assert **element-wise equality of the rank class**, not merely of the category. Two independently-derived implementations agreeing on 133 million hands is the strongest evidence available here.

**Check 3 — Distinct-value counts.** All C(52,5) = 2,598,960 five-card hands must yield exactly **7,462** distinct classes, and the five-card category counts in Appendix A exactly. Fast, and it catches perfect-hash collisions that the seven-card test can mask.

**Check 4 — Equity identities.** No external source needed; these hold to float exactness or to a stated tolerance:

1. `equity_exact` over any spot sums to exactly `1.0`.
2. Symmetry: `equity(A, B) == 1 - equity(B, A)` on the same board.
3. Averaging all 169 starting-hand classes against a random hand, weighted by combos, gives exactly **0.5**.
4. A hand that is already the nuts with no runout able to change that has equity exactly `1.0` — not `0.9999`.

**Check 5 — Published matchup anchors.** Compare `equity_exact` against Appendix A's published values. Because the enumeration is exact, the *only* legitimate tolerance is the precision at which the reference is published (±0.05pp); a larger gap means either the evaluator is wrong or the fixture was transcribed with the wrong suit configuration.

> [!IMPORTANT]
> **When Check 5 disagrees, Checks 1–4 adjudicate — not the published table.** This mirrors the blackjack area's standing rule that published charts are a known-answer test rather than the implementation. If the category counts are exact, the two evaluators agree on 133 million hands, and the identities hold, then the engine is right and the transcription is wrong: correct the fixture and record why in the tracking table. Never adjust the evaluator to hit a published number.

**Lock the baselines.** On pass, write `evaluator_baseline.json` (the nine category counts, the 7,462 count, the table content hash) and `equity_baseline.json` (every anchor matchup to six decimal places). These freeze exactly as `house_edge_baseline.json` does for blackjack, and move only through the three-step re-lock ritual in the Regression Guard.

> [!CAUTION]
> **Do not proceed to Phase 6 on a partial pass.** "The counts match except straights are off by 4" is not a near-miss — it is the signature of a wheel (A-2-3-4-5) handling bug, and the ace-low straight is not a rare edge case: it appears in millions of the enumerated hands and in a meaningful share of real ones. Every equity, every CFR payoff, and every solved frequency downstream inherits it silently.

### Verification

```bash
py -m pytest tests/poker/test_evaluator.py tests/poker/test_equity.py -q     # fast subsample
py -m pytest tests/poker/test_evaluator.py -q -m slow                        # full 133,784,560
py tests/regression_test.py --fast                                           # blackjack still green
```
Expected: all pass; the slow run prints the nine category counts beside Appendix A's and reports `EXACT MATCH` on all nine plus the 133,784,560 total.

---
## Phase 6: Betting Tree & Abstraction

**Files:** `src/poker/tree.py`, `src/poker/abstraction.py` (NEW)  
**Priority:** 🔴 High  
**Dependencies:** Phase 5

### Problem

Heads-up No-Limit Hold'em has on the order of **10¹⁶⁰ decision points**. It cannot be solved, stored, or even enumerated. Everything practical in this phase is about choosing *which smaller game to solve instead*, and being explicit that the smaller game is what the solver's output actually describes.

### Implementation

**1. `tree.py` — the betting tree, built from `GameSpec`.** Nodes are `Chance`, `Decision(player, infoset_key, actions)`, or `Terminal(payoff_fn)`. Legal actions at a decision node are derived from `spec.bet_sizes`, `spec.stack_bb`, remaining stack, and the current pot — never hardcoded and never enumerated with a literal list.

- **Minimum-raise legality** is a real rule, not an approximation: a raise must be at least the size of the previous raise. A bet-size grid that generates illegal raises produces a tree for a game that does not exist.
- **All-in is always available** when `spec.allow_allin`, and a pot-fraction bet that would leave less than half a big blind behind is snapped to all-in rather than creating a near-useless stub node.
- `tree.size()` returns node, infoset, and terminal counts. Print it before every solve — an abstraction that silently grew by 40× is the most common cause of a solve that "hangs".

**2. `abstraction.py` — card abstraction.**

- **Preflop: none needed.** The 169 isomorphic classes *are* the exact preflop abstraction, lossless up to suit relabelling. This is a genuinely free win and one of the reasons Phase 10 targets preflop first.
- **Flop and later: bucketing.** Compute a feature per hand — start with expected hand strength squared, `E[HS²]`, then move to potential-aware equity-distribution histograms — and cluster into `k` buckets with k-means. Histogram clustering uses earth-mover distance, not Euclidean, because two equity distributions with the same mean and different shapes play completely differently.
- **Bucket counts are a `GameSpec`-adjacent parameter and belong in the cache key.** A solve at 200 flop buckets and one at 5,000 are answers to different games.

**3. Public/private state separation.** An information set is (my hole cards' bucket, the public board, the full betting history). It must be **impossible** for the tree to key an infoset on anything the acting player cannot see — the single bug class that produces a "solver" whose strategy is better than any strategy could legally be.

> [!CAUTION]
> **Abstraction pathology is real and counter-intuitive.** Waugh et al. (2009) showed that refining an abstraction — more buckets, more bet sizes — can *increase* real-game exploitability, non-monotonically. It follows that the exploitability number Phase 8 computes is measured **inside the abstraction** and is a convergence diagnostic, not a bound on how exploitable the strategy is at a real table. Every place this number is surfaced — test output, API response, UI, this plan's tracking table — must say "abstraction-exploitability", never "exploitability", or the project will end up claiming something it has not measured.

> [!WARNING]
> Imperfect-recall abstractions (forgetting earlier-street buckets to afford more later-street ones) are standard practice in strong agents and **break CFR's convergence guarantee** — CFR is only proven to converge under perfect recall. They often work well anyway, but "works well" and "provably converges" are different claims. Ship perfect recall for v1; if imperfect recall is later adopted for memory reasons, record it in the tracking table as a deliberate loss of the guarantee.

### Verification

```bash
py -c "from src.poker.spec import GameSpec; from src.poker.tree import build_tree; \
t = build_tree(GameSpec(stack_bb=10.0, bet_sizes=(1.0,))); print(t.size())"
py -c "from src.poker.abstraction import preflop_buckets; print(len(set(preflop_buckets())))"
```
Expected: a small, finite, printed `(nodes, infosets, terminals)` triple that grows monotonically when a bet size is added and shrinks when `stack_bb` falls; then **`169`** exactly.

---

## Phase 7: CFR+ Solver

**File:** `src/poker/cfr.py` (NEW)  
**Priority:** 🔴 Critical — **the component the whole strategy layer depends on**  
**Dependencies:** Phase 6

### Problem

Given a tree, find a strategy profile no opponent can profitably deviate from. Counterfactual Regret Minimisation does this by self-play: at every information set, track the counterfactual regret of each action, play proportionally to positive regret, and average the strategies over time. The **average** strategy converges to a Nash equilibrium in two-player zero-sum games; the *current* strategy does not, and confusing the two is the most common way a working CFR implementation gets reported as broken.

### Implementation

**1. Vanilla CFR first, for auditability.** The full-tree recursion with reach probabilities, regret matching, and cumulative strategy averaging. Slow, but small enough to read end-to-end and check by hand against Kuhn. Build this before anything faster.

**2. CFR+ as the shipped default.** Three changes from vanilla:
- **Regret matching⁺**: floor cumulative regrets at zero after every iteration (`R ← max(R + r, 0)`) instead of letting negative regret accumulate.
- **Linear averaging**: weight iteration *t*'s strategy by *t* rather than uniformly.
- **Alternating updates**: update one player per iteration instead of both simultaneously.

Empirically an order of magnitude or more faster than vanilla on the same tree.

**3. Discounted CFR as an option** — discount accumulated regrets by `t^α/(t^α+1)` with α = 1.5, negative regrets by β = 0, and the strategy sum by `(t/(t+1))^γ` with γ = 2. Expose as `variant="dcfr"`; it is usually the fastest of the three on large trees.

**4. External-sampling MCCFR for trees too large to traverse fully** — sample chance and opponent actions, traverse only the acting player's subtree. Necessary once postflop enters the picture; unnecessary for preflop and toy games, so build it last.

**5. Checkpointing.** Write regret and strategy-sum tables to `data/poker/solves/{spec_key}/` every N iterations, with the `GameSpec`, abstraction parameters, and a source hash in the manifest — the same hash-validated pattern as `src/utils/cache_manager.py`, imported rather than reimplemented. A multi-hour solve that dies at hour three with nothing on disk is a self-inflicted wound.

> [!IMPORTANT]
> **The second headline rule for this area:** *a strategy without a measured exploitability is not a result.* This is the poker analogue of the repo's "no bare point estimates from Monte Carlo" rule. CFR always produces *something* — a converged equilibrium and a diverged mess both come out as a tidy table of frequencies, and they are indistinguishable by eye. No strategy artifact may be written to `data/poker/strategy/` without its abstraction-exploitability in mbb/g and its iteration count recorded in the same file.

> [!WARNING]
> Report and ship the **average** strategy, never the current one. The current strategy oscillates and can be arbitrarily far from equilibrium at any single iteration even while the average converges perfectly. In CFR+ the distinction is somewhat softened — its current strategy is unusually well-behaved — which makes the mistake easier to get away with and therefore easier to ship.

### Verification

```bash
py -c "from src.poker.toy import KuhnPoker; from src.poker.cfr import solve; \
s = solve(KuhnPoker(), iterations=10_000, variant='cfr+'); print(round(s.game_value, 6))"
```
Expected: **`-0.055556`** ≈ −1/18, the analytically known value of Kuhn poker to player 1. Phase 8 turns this one-line check into the actual gate.

---

## Phase 8: Validation Gate II — Exploitability + Toy Games

**Files:** `src/poker/exploit.py`, `src/poker/toy.py`, `tests/poker/test_toy_games.py`, `data/poker/baselines/toy_game_baseline.json` (NEW)  
**Priority:** 🔴 Critical — **GO / NO-GO**  
**Dependencies:** Phase 7

### Problem

"The solver ran and produced frequencies" is not evidence of anything. A CFR implementation with an inverted regret sign, a missing reach probability, or averaging over the wrong player still terminates and still emits a plausible-looking strategy. The only way to know is to run it on games whose equilibria are known by other means, and to measure how much a best response wins against the output.

### Implementation

**Check 1 — Kuhn poker against its analytic solution.** Three cards (J, Q, K), one ante, one bet size. Its equilibria are known in closed form as a one-parameter family:

- Player 1 bets J with probability α ∈ **[0, 1/3]**, always checks Q, and bets K with probability **3α**.
- After checking and facing a bet, player 1 folds J, calls Q with probability **α + 1/3**, and always calls K.
- Player 2, facing a bet, folds J, calls Q with probability **1/3**, and always calls K. Facing a check, bets J with probability **1/3**, checks Q, and always bets K.
- **Game value to player 1: −1/18 ≈ −0.055556.**

Assert the converged game value matches −1/18 to 1e-4, that player 2's frequencies match the (unique) values above to 1e-3, and that player 1's recovered α lies in [0, 1/3] with the 3α and α+1/3 relationships holding. The last part matters: asserting only the game value would pass for a solver that found *a* value-preserving strategy while getting the structure wrong.

**Check 2 — Leduc poker against a sequence-form LP.** Six cards, two rounds, a two-bet cap: small enough to solve *exactly* by linear programming (`scipy.optimize.linprog` on the sequence-form representation) and large enough to exercise chance nodes, multiple betting rounds, and public-card information sets — everything Kuhn does not. Assert CFR's game value matches the LP's to 1e-4 and its abstraction-exploitability falls below 1e-3 chips/hand.

**Check 3 — Exploitability actually decreases.** `exploit.best_response(strategy, player)` computes the exact best-response value by full-tree traversal; exploitability for a two-player zero-sum game is the mean of both best-response values, reported in **mbb/g** (thousandths of a big blind per game). Assert it decreases monotonically-in-trend over iterations and follows roughly the expected `O(1/√T)` shape, on a log-log plot recorded in the baseline.

**Check 4 — Best response beats a deliberately bad strategy by the expected amount.** Compute the best response to always-fold and check it wins the blinds exactly. This validates the best-response machinery itself, which Checks 1–3 all silently assume is correct.

**Lock the baseline.** `toy_game_baseline.json` stores Kuhn's game value and frequency vector, Leduc's LP value, and both convergence curves. These are analytic or LP-exact constants — if this baseline ever moves, the change is a bug in every case except a documented change to the toy game's own definition.

> [!CAUTION]
> **Convergence on Kuhn and Leduc does not imply correctness on hold'em.** It proves the regret update, the averaging, and the tree traversal are right. It says nothing about the card abstraction, the bet-size grid, or the terminal-value model — which is why Phase 10's preflop solve carries its own separate, and weaker, validation. Do not let a green Phase 8 be quoted as "the solver is validated" without that qualifier attached.

> [!NOTE]
> For scale: heads-up **limit** hold'em — about 3.19 × 10¹⁴ information sets — was essentially weakly solved by Cepheus (Bowling et al., *Science*, 2015) at 0.986 mbb/g of exploitability, using CFR+ across thousands of CPU cores for months. Heads-up **no-limit** is roughly 10¹⁶⁰ decision points and has never been solved, only approximated. This plan's ambitions must be read against those numbers: an exactly-solved preflop under a stated abstraction is a realistic goal, and a "GTO solution to NLHE" is not.

### Verification

```bash
py -m pytest tests/poker/test_toy_games.py -q -v
py -c "from src.poker.toy import LeducPoker; from src.poker.cfr import solve; from src.poker.exploit import exploitability; \
s = solve(LeducPoker(), iterations=100_000, variant='cfr+'); print(exploitability(LeducPoker(), s))"
py tests/regression_test.py --fast
```
Expected: every toy-game test passes; Leduc's exploitability prints below `1e-3` chips/hand; the blackjack gate is still green.

---

## Phase 9: Push/Fold Equilibrium & ICM

**Files:** `src/poker/pushfold.py`, `src/poker/icm.py`, `tests/poker/test_pushfold.py` (NEW)  
**Priority:** 🟡 Medium — but the highest value-per-line in the plan  
**Dependencies:** Phase 5 (deliberately *not* Phase 8)

### Problem

At short stacks the game collapses to one decision — jam or fold — and the equilibrium becomes exactly computable over the 169×169 preflop equity matrix with no abstraction, no tree, and no approximation. This is the only part of hold'em where "the GTO answer" is a defensible phrase, published Nash tables exist to check against, and the answer is genuinely actionable in real tournaments.

### Implementation

**1. `pushfold.py` — the jam-or-fold game.** Heads-up, the small blind either shoves all-in or folds; the big blind calls or folds. Given a caller's range, the shover's EV for each of the 169 classes is a direct lookup into the Phase 3 equity matrix, and vice versa. Solve by **fictitious play**: start from arbitrary ranges, best-respond alternately, converge. Milliseconds, and exact up to the equity matrix.

- Output: a 169-cell jam range and a 169-cell call range per effective stack depth, on a grid of 1–25bb in 0.5bb steps.
- Extend to 3+ handed by iterating over positions with the players behind folding at their own equilibrium frequencies.
- Antes materially widen both ranges — this must flow from `GameSpec.ante_bb`, never from a separate "with antes" table.

**2. Known-answer test.** The exact equilibrium of the heads-up jam-or-fold game was computed by Miltersen and Sørensen (2007), and the resulting Nash push/fold tables are widely published; the SAGE system is a hand-computable approximation of the same thing. Assert agreement with the published tables to within **2% of total hand frequency** per stack depth, and check the structural facts that need no table at all:

- Below roughly 2bb effective, the small blind jams 100% of hands (the blind investment already exceeds what folding can save).
- Jam and call ranges are monotone decreasing in effective stack depth.
- The call range is always tighter than the jam range at the same depth.

**3. `icm.py` — the Independent Chip Model.** Malmuth-Harville: a player's probability of finishing first is their share of chips; conditional on that, the rest of the field competes for second by the same rule, recursively. Equity is the payout-weighted sum.

Property tests that require no external reference:

1. ICM equities sum to **exactly** the prize pool.
2. Equal stacks → equal equity, for any payout structure.
3. Chips are worth strictly less at the margin as a stack grows — a chip leader's equity per chip is below a short stack's. This is the whole reason ICM exists, and a model that fails it is not ICM.
4. Winner-take-all reduces ICM exactly to chip-proportional equity.

**4. Bubble factor** — the ratio of the tournament equity risked to the tournament equity gained in an all-in, which is the tournament analogue of pot odds and the number that actually drives correct play near the money. Feed it back into `pushfold.py` so ICM-adjusted jam/call ranges are available, and label them separately from the chip-EV ones.

> [!NOTE]
> Malmuth-Harville is known to overstate the finishing probabilities of short stacks, because it treats each finishing position as a fresh proportional draw rather than modelling actual play. Alternatives exist (Malmuth-Weitzman, Roberts). Ship Harville as the default because every published table and every competing tool uses it — comparability is worth more than a small accuracy gain — and expose the model as a parameter rather than a hardcoded choice, exactly as `RuleSet` exposes rule variants on the blackjack side.

### Verification

```bash
py -c "from src.poker.pushfold import solve_pushfold; from src.poker.spec import GameSpec; \
r = solve_pushfold(GameSpec(stack_bb=10.0)); print(round(r.jam_pct, 1), round(r.call_pct, 1))"
py -c "from src.poker.icm import icm_equity; \
print(icm_equity([5000, 3000, 2000], [50, 30, 20]), sum(icm_equity([5000,3000,2000],[50,30,20])))"
py -m pytest tests/poker/test_pushfold.py -q
```
Expected: a jam percentage materially wider than the call percentage at 10bb, both matching the published Nash table within 2pp; ICM equities summing to **exactly `100`** (float equality — it is a partition of the prize pool), with the 5,000-chip leader holding *less* than 50% of the pool despite holding 50% of the chips.

---

## Phase 10: Preflop Solve & Strategy Artifacts

**Files:** `scripts/poker/solve_preflop.py`, `scripts/poker/solve_spot.py`, `src/poker/advisor.py`, `data/poker/baselines/preflop_baseline.json` (NEW)  
**Priority:** 🔴 High  
**Dependencies:** Phases 8, 9

### Problem

The product a player actually wants is: "I have AJs on the button at 100bb, what do I do, and how often?" That means a solved preflop strategy per `GameSpec`, cached to disk and looked up in microseconds — the same solve-once-and-cache architecture that makes the blackjack grid viable, applied to a much larger and much less exact problem.

### Implementation

**1. The preflop tree.** Open / 3-bet / 4-bet / 5-bet-jam, with sizes from `spec.bet_sizes`, positions from `spec.num_players`, rake from `spec.pot_after_rake`. Preflop card abstraction is the lossless 169 classes, so the only abstraction error is in the betting grid and in the terminal values.

**2. Terminal values — the plan's largest modelling compromise, stated plainly.** Lines that end preflop (everyone folds, or an all-in) have exact values. Lines that *see a flop* do not: their true value requires solving postflop. v1 approximates a flop-seeing terminal as **all-in equity scaled by an equity-realisation factor** parameterised by position and stack-to-pot ratio.

> [!CAUTION]
> **This approximation is to the preflop solve what `2 × one_hand_EV` is to the blackjack split solver — a documented, bounded compromise, not a bug to be quietly fixed.** But it is a *larger* compromise than blackjack's, and the difference matters: the split approximation is worth about 0.01% and blackjack's charts were built with it, so it is required to match published references. Equity realisation is worth considerably more and there is no published reference built on the same assumption. Consequences that must be respected: the resulting strategy is an equilibrium **of the approximated game**, the exploitability figure is measured **against that same approximated game**, and neither number transfers to a real table without qualification. Record the realisation factors in `preflop_baseline.json` alongside the strategy, because changing them changes the answer, which makes them part of the game definition rather than a tuning knob.

**3. Solve and store.** `solve_preflop.py --spec hu-100bb-r5c3-s5 --iterations 5_000_000` writes `data/poker/strategy/{spec_key}/preflop.json`:

```json
{
  "spec": {...}, "solver_hash": "...", "iterations": 5000000,
  "abstraction_exploitability_mbb": 3.4,
  "realisation_factors": {...},
  "strategy": {"BTN:open": {"AJs": {"raise_2.5": 0.87, "fold": 0.13}, ...}, ...}
}
```

Frequencies, always. A cell that resolves to a pure action stores `{"raise_2.5": 1.0}`, not `"raise"` — a format that *can* express purity without a special case is the only one that survives contact with a mixed solution.

**4. `advisor.py` — the runtime layer.** `advise(hole_cards, position, action_history, spec) -> Advice` returning the action frequencies, the EV of each action, the EV gap between the best and chosen action (this is what the Phase 13 trainer scores against), and a `is_close` flag when the top two actions are within a configurable EV epsilon.

**5. `solve_spot.py` — bounded postflop.** Solve a single, fully-specified postflop spot (board, both ranges, stack, pot) with a small bet grid, capped by iteration count and wall-clock. This powers the UI's Solver tab. **Bounded by construction** — an unbounded solver behind an HTTP endpoint is a denial-of-service on a 7.7GB machine, the same constraint the blackjack `/api/simulate` route already lives under.

### Verification

```bash
py scripts/poker/solve_preflop.py --spec hu-100bb-r5c3-s5 --iterations 1000000
py -c "from src.poker.advisor import advise; from src.poker.spec import GameSpec; \
print(advise('AJs', 'BTN', [], GameSpec()))"
```
Expected: a solve that reports a decreasing abstraction-exploitability curve and finishes below 10 mbb/g; then an `Advice` whose frequencies sum to 1.0 and whose structure passes the sanity checks that hold in every published solve — AA opens 100% from every position, 72o opens 0% from every position, and open frequency rises monotonically from UTG to the button.

---

## Phase 11: Bankroll, Variance & Risk of Ruin

**File:** `src/poker/bankroll.py`, `tests/poker/test_bankroll.py` (NEW)  
**Priority:** 🟢 Low — small file, and the one most likely to change a user's actual behaviour  
**Dependencies:** None (independent; buildable any time after Phase 0)

### Problem

Poker's edges are small relative to its variance, and the resulting intuition failure is severe: a genuinely winning player routinely experiences downswings that look exactly like being a losing player. This module makes that quantitative — the poker analogue of the blackjack area's Kelly and risk-of-ruin layer, but with the units and formulas the game actually uses.

### Implementation

**1. Units.** Win rate `w` in **bb/100 hands**, standard deviation `s` in **bb/100 hands** (typical: 80–110 for 6-max NLHE, 100–140 for heads-up), bankroll `B` in **big blinds**.

**2. Risk of ruin.** For a random walk with drift, the probability of ever losing a bankroll `B` is

```
RoR = exp(−2 · B · w / s²)
```

with `B` in bb and `w`, `s` in bb/100 (the per-hand conversion cancels, which is why this compact form is correct and worth writing out in the docstring so nobody "fixes" it).

| Bankroll | w = 5 bb/100, s = 100 | w = 2 bb/100, s = 100 |
|---:|---:|---:|
| 1,000 bb (10 buy-ins) | 36.8% | 67.0% |
| 2,000 bb (20 buy-ins) | 13.5% | 44.9% |
| 5,000 bb (50 buy-ins) | 0.67% | 13.5% |

The same expression with `D` in place of `B` gives the probability of *ever* enduring a downswing of `D` — which is the number that actually stops people playing, and which the UI should show at least as prominently as the ruin probability.

**3. Win-rate confidence intervals — the honesty function.** The standard error of an observed win rate over `n` hands is `s / sqrt(n/100)`:

| Hands | SE (bb/100) at s = 100 | 95% CI half-width |
|---:|---:|---:|
| 10,000 | 10.0 | ±19.6 |
| 100,000 | 3.16 | ±6.2 |
| 1,000,000 | 1.00 | ±2.0 |

> [!IMPORTANT]
> **A million hands buys a ±2 bb/100 confidence interval.** Most winning players' true win rates live inside that interval end to end. This is not a footnote — it is the single most useful output in this module, and it belongs in the UI next to every observed win rate, exactly as the blackjack area's `metrics.py` attaches a standard error to every simulated figure. A tool that displays "your win rate: 5.2 bb/100" from a 20k-hand sample without its ±14 is not reporting a measurement.

**4. Stake selection.** Given a bankroll and a target risk of ruin, return the largest stake whose RoR stays under target. This is the poker-shaped analogue of fractional Kelly: the bet is not continuously scalable, so the decision is discrete stake choice, and the same conservatism argument applies — default to the stake that hits **half** the user's stated risk tolerance, and say so.

**5. Downswing simulation.** Monte Carlo over hands with the given `(w, s)` to produce the distribution of maximum drawdown and time-to-recovery, reported with quantiles and standard errors.

### Verification

```bash
py -c "from src.poker.bankroll import risk_of_ruin, winrate_ci; \
print(round(risk_of_ruin(bankroll_bb=1000, wr_bb100=5, sd_bb100=100), 4)); \
print(winrate_ci(observed_bb100=5.0, hands=1_000_000, sd_bb100=100))"
py -m pytest tests/poker/test_bankroll.py -q
```
Expected: **`0.3679`** (exactly `exp(−1)` — a closed-form check with no tolerance needed), then a 95% interval of approximately `(3.0, 7.0)` bb/100.

---
## Phase 12: Flask API Blueprint

**Files:** `src/poker/api.py` (NEW); `app.py` (MODIFY — exactly two lines)  
**Priority:** 🟡 Medium  
**Dependencies:** Phases 3, 4, 9, 10, 11

### Problem

The UI needs the engine, and the engine is Python. The existing `app.py` already carries the blackjack API and its startup registry, and it must not become a two-headed file. A Blueprint keeps the entire poker surface in `src/poker/api.py` and reduces the diff against a validated file to an import and a registration.

### Implementation

**The two permitted lines in `app.py`:**

```python
from src.poker.api import poker_bp          # (1)
app.register_blueprint(poker_bp)            # (2)
```

**Startup**, mirroring the blackjack side's `GRIDS = {...}` eager-load pattern:

```python
PREFLOP = {key: load_preflop(key) for key in SHIPPED_SPECS}   # data/poker/strategy/*/preflop.json
EQUITY_169 = np.load("data/poker/equity/preflop_169x169.npy") # ~350KB, always loaded
```

**Eagerly load only what is small and pre-built.** The preflop strategies and the equity matrix are; the evaluator's 124MB table is loaded lazily on first equity request; postflop solves are never eagerly loaded. Where an artifact is missing, return a clean error **naming the exact command that would build it** — the blackjack side's `/api/stake` already does this for missing index tables, and it is the difference between a 30-second debugging session and an hour of one.

**Routes** (all under `/api/poker/`):

| Route | Method | Purpose |
|---|---|---|
| `/api/poker/spec` | GET | Available `GameSpec`s, defaults, which artifacts are pre-built |
| `/api/poker/equity` | POST | `{hands, board, spec}` → equities; exact when enumerable, else MC **with SE** |
| `/api/poker/range/parse` | POST | `{notation}` → combos, weights, percent of hands |
| `/api/poker/range/equity` | POST | Range vs range, with card removal done jointly |
| `/api/poker/preflop` | GET | Solved preflop strategy for a spec — feeds the Preflop tab |
| `/api/poker/advise` | POST | `{hole, position, history, spec}` → frequencies, EV per action, EV gap |
| `/api/poker/pushfold` | GET | Jam/call ranges by effective stack, chip-EV and ICM-adjusted |
| `/api/poker/icm` | POST | `{stacks, payouts, model}` → equities, bubble factors |
| `/api/poker/solve` | POST | A **bounded** single-spot postflop solve |
| `/api/poker/bankroll` | POST | `{bankroll, wr, sd, stakes}` → RoR, downswing quantiles, CI, stake advice |

> [!WARNING]
> `/api/poker/solve` must be bounded by **both** iteration count and wall-clock, and must reject trees above a node-count threshold *before* starting rather than after. An unbounded solve endpoint on a 7.7GB machine is a self-inflicted denial of service — the same constraint the blackjack `/api/simulate` route already carries, for the same reason.

> [!IMPORTANT]
> **Every response that contains a Monte Carlo number carries its standard error in the same object**, and every response containing a solved strategy carries its `abstraction_exploitability_mbb` and `iterations`. Not in a sibling field the client may ignore, and not only in the docs — in the same JSON object the UI renders from, so that a UI which forgets to display it is an obvious omission rather than an invisible one.

### Verification

```bash
py app.py
curl -s -X POST localhost:5000/api/poker/equity -H "Content-Type: application/json" \
  -d '{"hands":["AsAh","KsKh"],"board":[],"spec":"hu-100bb-r5c3-s5"}'
curl -s localhost:5000/api/blackjack/grid?rules=6d-s17-das-ls-p75 | head -c 200
```
Expected: `{"equities":[0.819...,0.181...],"method":"exact","runouts":1712304}` with no `standard_error` field (because it was enumerated, not sampled); and the existing blackjack routes responding exactly as before.

---

## Phase 13: Web UI

**Files:** `static/poker.html`, `static/css/poker.css`, `static/js/poker/*.js` (NEW)  
**Priority:** 🔴 High  
**Dependencies:** Phase 12

### Problem

This is the deliverable the user sees. It has to make the two things that are genuinely hard to internalise about poker visible: that correct play is *mixed*, and that variance dwarfs edge over any period a human can perceive.

### Implementation

Follow the repo's existing frontend conventions exactly — **single-page app, tab navigation, vanilla JS with no framework, glassmorphism dark mode, Outfit font, `fetch()` against Flask**. Poker gets its own entry point (`/poker`) rather than a sixth tab in the blackjack SPA, so neither app's tab bar becomes a mess and neither JS bundle grows a dependency on the other.

**Tabs:**

1. **Equity** — hand/range vs hand/range on any board. Show the exact-vs-sampled badge and the runout count; when sampled, show the ±CI. The headline chart is the **equity distribution histogram**, not the mean, because that is the picture that explains why a 55% hand can be a check-fold.

2. **Ranges** — the 169-grid editor. Click and drag to select, right-click for a weight slider, notation box synced both ways, live combo count and percent-of-hands. Weighted cells render as partially-filled, never as on/off.

3. **Preflop** — the solved charts by position and stack depth. **Mixed cells render as split cells with their frequencies**, never as the most-frequent action alone. A toggle switches to a "simplified" view that rounds to pure actions for memorisation, clearly labelled with the EV cost of the simplification — showing the cost is what makes the simplification honest.

4. **Push/Fold & ICM** — jam/call charts by effective stack with a slider, side-by-side chip-EV and ICM-adjusted, plus an ICM calculator (stacks, payouts, bubble factor) and the equity-per-chip curve that makes chip devaluation visible.

5. **Solver** — configure a bounded single spot, run it, and watch the **exploitability curve fall** in real time. That curve is the most educational object in the whole app: it shows convergence as a process rather than an oracle, and it makes it obvious when a solve has not converged.

6. **Bankroll** — bankroll, stake, win rate, SD. Outputs RoR, the downswing distribution, stake recommendation, and — most importantly — the confidence interval around the user's *observed* win rate given their sample size.

7. **Trainer** — a spot is dealt, the user picks an action, and the score is the **EV lost in bb** against the solver's frequencies, accumulated over the session. Scoring against frequencies rather than a single "right answer" is the whole point: picking the 30% action is not an error, and a trainer that marks it wrong teaches the wrong lesson.

> [!CAUTION]
> The UI must state plainly, in the app and not only in the README, that (a) using a solver or any real-time assistance **during** play violates the terms of service of essentially every online poker site and is grounds for account closure and fund confiscation — this is a study tool for off-table analysis; (b) every strategy shown is an equilibrium of an **abstracted** game, and its exploitability figure is measured inside that abstraction rather than at a real table; and (c) edges in poker are small relative to variance, so results over any humanly-perceptible sample are dominated by noise. The blackjack area carries an equivalent disclaimer about counting and casino policy; this one is if anything more necessary, because the consequence is more concrete.

> [!NOTE]
> The single most valuable UI decision in this plan is refusing to collapse a mixed strategy to a pure one by default. Every commercial trainer that shows "the right play" for a mixed spot is lying by simplification, and users then learn a strategy that is exploitable in exactly the way the mixing was there to prevent. The simplified view exists — memorisation is a real need — but it is opt-in and priced.

### Verification

Open `http://127.0.0.1:5000/poker` and confirm: the Equity tab reports `exact / 1,712,304 runouts` for a preflop heads-up matchup and switches to a sampled result with a visible ±CI for a range-vs-range one; the Preflop tab renders at least one visibly split cell with two frequencies; moving the Push/Fold stack slider from 15bb to 8bb visibly widens both charts; the Solver tab's exploitability curve is monotone downward in trend; the Bankroll tab shows a ±CI wider than the observed win rate itself at a 10,000-hand sample. Then confirm `http://127.0.0.1:5000/` still serves the blackjack app unchanged.

---

## Phase 14: Regression Harness & CI

**Files:** `tests/poker/regression_test.py`, `docs/poker_guide.md` (NEW); `.github/workflows/regression.yml` (MODIFY — add a job, do not alter the existing one)  
**Priority:** 🟡 Medium  
**Dependencies:** All

### Problem

The blackjack area's single most valuable artifact is `tests/regression_test.py`: one command that checks every locked baseline and either passes or names exactly what moved. Without the equivalent here, "did my change break something?" is unanswerable and every refactor is a gamble. Build the twin — and keep it a twin, not a merger, so a poker failure can never mask a blackjack one.

### Implementation

1. **`tests/poker/regression_test.py`** — the poker gate, checking in order:
   - evaluator table hash + the nine category counts (subsampled in `--fast`, full otherwise) and the 7,462 distinct-value count;
   - every anchor equity against `equity_baseline.json`;
   - Kuhn's game value and frequencies against the analytic constants, and Leduc's against the LP;
   - every shipped preflop strategy's abstraction-exploitability against `preflop_baseline.json`;
   - push/fold ranges against the published Nash tables;
   - the ICM property identities.

   Flags mirror the blackjack gate exactly: `--fast` (CI mode), `--generate` (re-lock all), `--generate-spec <key>` (re-lock one).

2. **CI** — add a **separate job** to `.github/workflows/regression.yml` running `py tests/poker/regression_test.py --fast`. Do not fold it into the existing blackjack job: two jobs means the summary line tells you which engine broke without reading a log.

3. **`docs/poker_guide.md`** — the deep walkthrough, matching `docs/system_guide.md` in role: where every published anchor came from, why CFR+ over vanilla, what the equity-realisation approximation does and does not justify, why abstraction exploitability is not real-game exploitability, and the derivation of the risk-of-ruin form.

### Verification

```bash
py tests/poker/regression_test.py --fast
py tests/regression_test.py --fast
py -m pytest tests/ --ignore=tests/regression_test.py --ignore=tests/poker/regression_test.py -q
```
Expected: `ALL POKER BASELINES PASS` with a per-check table; `ALL BASELINES PASS` from the untouched blackjack gate; the full unit suite green across both areas.

---

## Implementation Tracking

| Phase | Component | Status | Notes |
|-------|-----------|:------:|-------|
| 0 | Area Bootstrap & Agent Docs | `[x] Completed` | Skeleton created: `src/poker/__init__.py`, `tests/poker/__init__.py`, `scripts/poker/`, `data/poker/{evaluator,equity,ranges,strategy,baselines,solves}/` (`.gitkeep` in the three gitignored-or-still-empty dirs). `.gitignore` extended (append-only) for `data/poker/evaluator/` and `data/poker/solves/`. Three new skills written and mirrored into `.claude/skills/` byte-identical (no symlinks on this Windows checkout, matching how the existing five skills are already mirrored): `poker_evaluator_conventions`, `poker_range_conventions`, `poker_solver_conventions`. `.agents/instructions.md` and `.agents/project-overview.md` got append-only "Poker Area" sections; `CLAUDE.md` got a one-paragraph pointer. Verification: `py -c "import src.poker"` → `ok`; `py tests/regression_test.py --fast` → `11/11 checks passed, ALL BASELINES PASS` (83.9s), confirming the blackjack gate is unaffected; `git status` diff scoped to exactly the additive paths plus append-only edits to the three docs and `.gitignore` — no file under `src/engine/`, `src/strategy/`, `src/counting/`, `src/simulation/`, `src/bankroll/`, or `tests/regression_test.py` touched |
| 1 | Card Primitives + `GameSpec` | `[x] Completed` | Built `src/poker/cards.py` (`card_id`/`card_ids`/`id_to_str`, `rank_of`/`suit_of`, `mask`, `deck`, `canonical`/`canonical_board`) and `src/poker/spec.py` (`GameSpec`, frozen dataclass). Plan's exact verification commands reproduced their expected output precisely, including the illustrative key string: `card_id('As') == 51`; `canonical_board` over all C(52,3) flops → **1755** exactly; `GameSpec().key() == "hu-100bb-r5c3-s5"` and `pot_after_rake(20.0, True) == 19.0` exactly. `canonical()` also collapses all C(52,2) = 1,326 starting hands to exactly **169** classes using the same suit-permutation logic (not required by the plan's verification block, but confirms the function generalises rather than being flop-specific). Additional checks: card-id round-trip on `As/Td/2c/Kh`; `card_ids`/`id_to_str` correctly parse/render a 7-card string; `mask` conflict bit set correctly; `deck()` returns 52 unique ids; `GameSpec` frozen (mutation raises `dataclasses.FrozenInstanceError`); `key()` discriminates on `stack_bb`, `ante_bb`, `num_players`, and `bet_sizes` (all game-defining fields, not just cosmetic ones) so two solves under different specs cannot collide on a cache key; `__post_init__` validation rejects `rake_pct=1.5`. `py tests/regression_test.py --fast` still `11/11 checks passed, ALL BASELINES PASS` (80.8s) |
| 2 | Exact Hand Evaluator | `[x] Completed` | Built `src/poker/evaluator.py` (Strategy A: `_classify5` pure classification + `flush_class`/`unique5_class` bitmask-indexed arrays + `prime_class` sorted-array lookup for repeated-rank hands, derived from a full direct enumeration of all C(52,5) = 2,598,960 real card combos rather than abstract multiset reasoning — the classify-from-real-cards approach caught that the naive "multisets of size 5 from 13 ranks" combinatorial identity overcounts by exactly 13 impossible five-of-a-kind cases, before any code was written on that basis) and `scripts/poker/build_evaluator_tables.py`. Table build: **7,462** rank classes in 9.1s, matching the known constant exactly (internal `assert` in `build_tables()`); persisted to `data/poker/evaluator/tables.npz` (152KB, gitignored — far smaller than Strategy B's ~124MB 7-card DAG, which was not needed and is deferred per the plan's "escalate only if Strategy A proves too slow"). Plan's exact verification commands reproduced exactly: royal-flush-plus-junk evaluates stronger than quad-aces-plus-junk (`True`); `distinct_five_card_values()` (a fresh, independent re-enumeration via `evaluate5()` itself, not reusing `build_tables()`'s internal count) → **7462** in 4.6s. Went beyond the plan's minimal verification block: all nine 5-card category counts (`STRAIGHT_FLUSH` 40, `FOUR_OF_A_KIND` 624, `FULL_HOUSE` 3744, `FLUSH` 5108, `STRAIGHT` 10200, `THREE_OF_A_KIND` 54912, `TWO_PAIR` 123552, `ONE_PAIR` 1098240, `HIGH_CARD` 1302540) reproduced **exactly** against Appendix A.2 over the full C(52,5) enumeration (9.4s), summing to exactly 2,598,960; a sampled pairwise order-consistency check (4,000 random hands, ~16k adjacent pairs) confirmed `evaluate5()`'s table-lookup ordering agrees with the independent `_classify5()` reference key comparison on every pair (0 mismatches) — the property Phase 5's full gate will check exhaustively; the wheel (A-2-3-4-5) correctly ranks weaker than a 6-high straight; two same-rank different-suit flushes tie exactly; a board-plays-the-hand case (royal flush entirely on the board) ties correctly across two different hole-card pairs; quad aces beats a full house in a 7-card evaluation. Full C(52,7) enumeration (133,784,560 hands × 21 subsets ≈ 2.8B `evaluate5` calls) was deliberately **not** run in this phase — extrapolated at ~2.8 hours from measured throughput, it is explicitly Phase 5's job (`@pytest.mark.slow`, stratified subsample in `--fast`), not a Phase 2 spot-check. `py tests/regression_test.py --fast` still `11/11 checks passed, ALL BASELINES PASS` (86.9s) |
| 3 | Equity Engine (exact + MC) | `[x] Completed` | Built `src/poker/equity.py` (`equity_exact`, `equity_mc`, `equity_distribution`, `equity` dispatcher, `runout_count`/`EXACT_LIMIT`) and `scripts/poker/build_preflop_equity.py`. Plan's exact verification commands reproduced their expected structure precisely: `equity_exact([AsAh],[KsKh],[])` → `[0.826, 0.174]` summing to exactly `1.0`; `equity_exact([AsKs],[QhQd],[])` → `[0.462, 0.538]`, matching the plan's illustrative ≈46%/≈54%. Cross-validated `equity_mc` against `equity_exact` on the same spot (within 4×SE); verified the exact-vs-sampled dispatcher routes preflop heads-up to the exact path (`se is None`); verified 3-way preflop equity sums to 1.0; verified a turn-only spot (KK's only outs = 2 remaining kings / 44 unseen cards) reproduces the literal out-count fraction exactly; verified `equity_distribution` sums to 1.0 and matches `equity_exact`'s mean. **Mid-phase engineering escalation**: `evaluator.py`'s Phase 2 `evaluate_batch` (naive per-hand Python loop) measured too slow for this phase's own deliverable — extrapolated the preflop-matrix build at ~8.4 days. Upgraded `evaluate_batch` twice: first to a fully-vectorised pure-numpy implementation (~235k hands/sec, ~18× faster, verified bit-identical to the reference on 20,000 random 7-card hands), then — still too slow for a ~23,000-enumeration matrix build — to a `numba(parallel=True)` kernel (~6.9M hands/sec, a further ~29×, verified bit-identical again), per the plan's own "numba... add only if numpy proves too slow" escalation path (`requirements.txt` updated, pure-numpy path kept as the no-numba fallback, Dependencies section and Appendix B item 9 updated to reflect this was resolved rather than deferred). **Correctness bug caught before it shipped**: computing Appendix A.4's preflop anchors with the new exact tool revealed the v1 draft plan had the AA-vs-KK shared-suit relationship backwards (claimed fewer shared suits → higher pair equity; the real, now-exactly-computed relationship is the opposite — more shared suits denies the underdog more flush outs). Appendix A.4 rewritten with exact, suit-pinned, individually computed values (no more "≈" published transcriptions) for AA vs KK at all three shared-suit counts, AA vs 72o, AKs/AKo vs QQ, AKo vs 22, plus an honestly-labelled Monte Carlo figure (85.198% ± 0.109% 95% CI, n=400,000) for AA vs a random hand, deferring the true exact combo-weighted version to Phase 4's `Range`. `scripts/poker/build_preflop_equity.py` verified correct on a 26-pair subset (covers AA's full row through AA vs KK): the AA-vs-KK class-pair's combo-weighted aggregate (81.946%) was independently hand-verified against a hypergeometric weighting argument over the exact per-shared-suit-count values (6/24/6-weighted average of the three AA-vs-KK numbers above reproduces 81.946% exactly). **A second correctness bug, this one in the build script itself, was caught by the diagonal self-matchup assertion the moment the full run reached it**: the ~23h background build crashed at pair 338/14,365 (`AKo vs AKo`) with `AssertionError: got 0.5020987594993145`, not `0.5`. Root cause: `shapes_for_pair`'s shape key was `cards.canonical(a + b)` — canonicalising the merged 4-card *set*, which is order-blind, so for a self-matchup (`i == j`) a raw pair `(a, b)` and its reverse `(b, a)` collapsed into the same shape even though `f(b, a) = 1 − f(a, b)`, not `f(a, b)`; the represented shape's one computed value got silently reused for both. The earlier 26-pair check hadn't caught it because it only exercised `AA vs AA` (pair 1) as its one self-matchup, and pair classes are structurally immune — every one of AA's 6 combos pairs only with its exact suit-complement, and that specific relationship is independently self-symmetric (0.5 either way), which happens to mask the bug rather than being evidence against it. Fixed by replacing the shape key with `_ordered_shape`, a new hero/villain-order-sensitive canonicalisation (keeps hero's and villain's cards canonicalised separately rather than merged into one set) added to the build script. Re-verified on the same 338-pair prefix that had crashed: `AKo vs AKo` now returns exactly `50.000%`, the crash does not recur, and — confirming the bug was structurally confined to the diagonal, as the fix's own design predicts (off-diagonal pairs draw hero and villain from *disjoint* combo groups, so the colliding-reverse-pair scenario can't arise there) — every one of the 13 already-computed cross-class values (`AA vs A2o` 93.215%, `AA vs QJs` 80.888%, ... `AKs vs 53s` 62.596%) reproduced bit-for-bit identically to the pre-fix run. The **full 169×169 build was relaunched as a background job and completed**: all 14,365/14,365 class pairs, 47,086 total distinct suit-shapes (avg 3.28/pair, close to the 3.375 sampled estimate), **27h 8m** actual wall time (97,694s — longer than the ~23h estimate, most likely because the small 26-pair sample used to extrapolate it happened to undersample the more expensive offsuit-vs-offsuit pairs, which run up to 7 shapes each) — saved to `data/poker/equity/preflop_169x169.npz` (231KB, confirmed **not** gitignored via `git check-ignore`). Verified thoroughly on load: zero `NaN` entries (every one of the 14,365 pairs populated both triangle halves); **all 169 diagonal self-matchups exactly `0.5`**, `min == max == 0.5` bit-for-bit, holding across the *entire* matrix this time, not just the 338-pair prefix re-tested pre-launch; matrix symmetry (`matrix[i,j] + matrix[j,i] == 1.0`) exact with **zero** max error across all 169×169 = 28,561 cells. Spot-checked against the Phase 3 exact single-shape anchors computed earlier: `AA vs KK` → 81.946% (matches the hand-derived hypergeometric aggregate to 5 decimal places, as expected since it's the same computation); `AKs vs QQ`, `AKo vs QQ`, `AKo vs 22`, `AA vs 72o` all landed close to but distinctly different from their single-suit-configuration Appendix A.4 values (e.g. `AA vs 72o`: matrix 88.200% vs Appendix A.4's pinned-suit 88.206%) — expected and correct, since Appendix A.4 deliberately pins one specific suit configuration per its own stated design, while the matrix holds the full combo-weighted class average; the two are answers to different, equally valid questions, not a discrepancy. `py tests/regression_test.py --fast` re-run after the 27h background job: `11/11 checks passed, ALL BASELINES PASS` (blackjack area completely unaffected by a computation that pinned all 12 cores for over a day) |
| 4 | Ranges, Combos & Card Removal | `[x] Completed` | Built `src/poker/ranges.py`: the canonical 169-class registry (`CLASS_LABELS`, `class_combos()`, `hand_classes()`); a notation parser supporting pairs (`AA`, `TT+`, `88-55`), suited/offsuit/either (`AKs`, `AKo`, `AK`/`KA` = both combined), kicker ranges keeping the top card fixed (`A5s+` = A5s..AKs, `A5s-A2s`), explicit combos (`AsKd`), per-token weights (`AJs:0.5`, validated to `[0,1]`), and `100%`/`random`/`0%`; `Range` (notation/combo-count/`conditioned()`/`reweight()`/`union`/`intersect`/`difference` with `|`/`&`/`-` operators); `save_range`/`load_range` JSON persistence; `range_vs_range_equity()` (joint combo-weighted sum over non-conflicting pairs, grouped by suit-isomorphism shape before calling `equity_exact` so only one enumeration is needed per distinct shape, generalising Phase 3's technique to arbitrary weighted ranges and an optional board). Plan's exact verification commands reproduced exactly: `Range('100%').n_combos()` → `1326.0`; `Range('AA').n_combos()` → `6.0`, `.conditioned(mask(card_ids('As'))).n_combos()` → `3.0`. **`tests/poker/test_ranges.py`: 33/33 passed**, including the plan-mandated joint-vs-naive divergence check — constructed spot (hero holds a specific AA combo, villain's range is the full `AA` class, so 5 of villain's 6 combos conflict with hero's exact cards) diverges by **~41.7pp** (joint = exactly 0.5 by the same self-matchup symmetry Phase 3 established, naive = 8.33%), an order of magnitude past the plan's >0.5pp bar. Also covered: all notation shapes' combo counts (6/4/12/16, plus `+`/`-` ranges), `conditioned()`'s deliberate no-rescale behaviour (survivors keep their original weight — verified with a weighted range, not just the plan's uniform-weight `AA` example), union/intersect/difference semantics, save/load round-trip, `range_vs_range_equity` summing to exactly `1.0` both with and without a board, and rejecting a fully-self-conflicting range pair. **Two parser bugs found and fixed during testing**: (1) the `"100%"`/`"random"` keyword check ran *after* the rank-character-wise case normalisation, and since `'a'.upper()` is a valid rank character, `"random"` partially normalised to `"rAndom"` and silently failed to match — fixed by checking the keyword tokens against the raw token *before* normalisation; (2) none in the core logic, but one test itself assumed literal input-order combo tuples where the implementation intentionally always stores `(min, max)` — fixed the test, not the code. **Refactor**: relocated the 169-class registry out of `scripts/poker/build_preflop_equity.py` (a local, Phase-3-only duplicate) into `ranges.py`, its rightful Phase 4 home per the plan's file table — re-verified after the move that `AKo vs AKo` still computes to exactly `0.5` through the relocated `_ordered_shape`, confirming the Phase 3 shape-collision bug fix survived the refactor intact. Shipped `data/poker/ranges/random.json` (the trivial 1,326-combo reference range) via `save_range`; **deliberately did not** fabricate positional opening/calling ranges (UTG/BTN/etc.) as example reference data — the plan itself notes these are "inputs and UI conveniences, not answers" that Phase 10's solver will derive for real, and inventing specific percentages/notation now would be unverified poker-strategy content with no test behind it, not a Phase 4 code deliverable. `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (120.7s) |
| 5 | **Validation Gate I** | `[x] PASSED — GO for Phases 6+` | Built `tests/poker/test_evaluator.py` (10 tests), `tests/poker/test_equity.py` (15 tests), `data/poker/baselines/{evaluator,equity}_baseline.json`. **All 25 Phase 5 tests pass**, plus the 33 already-shipped Phase 4 range tests re-run clean alongside them (**58/58 across `tests/poker/` total**, 178.0s). **Check 1 (full C(52,7) enumeration) ran to completion, not a subsample**: the plan anticipated needing `@pytest.mark.slow` + a stratified 1-in-64 `--fast` subsample ("with pure Python it is hours") — the Phase 3 numba escalation made this moot, since the full 133,784,560-hand enumeration now runs in **~83s measured**, well inside normal test-suite budget; all nine category counts matched Appendix A.1 **exactly** (41,584 / 224,848 / 3,473,184 / 4,047,644 / 6,180,020 / 6,461,620 / 31,433,400 / 58,627,800 / 23,294,460), summing to exactly 133,784,560. **Check 3** (5-card enumeration, ~10s): all nine counts matched Appendix A.2 exactly, `distinct_five_card_values() == 7462` confirmed fresh. **Check 2 was reformulated** — Strategy B (the 124MB 7-card DAG table) was never built, since Strategy A's numba path proved fast enough on its own, so there was no second table to diff against as the plan's "Strategy A vs Strategy B" text envisioned. Substituted a from-first-principles reference (`_classify5`, zero lookup-table involvement) checked against the table-based evaluator on a deterministic stride-400 sample of C(52,7) (334,462 hands, ~26s for the direct path — full-scale would extrapolate to ~2-2.5h in pure Python, too slow to justify given Check 1 already covers aggregate correctness at full scale): **0 ordering mismatches**, and both paths independently see exactly 4,758 distinct classes within the sample. This is a deliberate, documented reinterpretation of Check 2's coverage split (Check 1's exact combinatorial counts catch classification-rule bugs via independently-known ground truth; the reformulated Check 2 catches table-construction/lookup-machinery bugs via a genuinely separate code path) rather than a silent scope reduction. **Check 4** (identities needing no external source): equity sums to exactly 1.0 across single/3-way spots; symmetry `equity(A,B) == 1-equity(B,A)`; nuts on a complete board → equity exactly `1.0`/`0.0` (quad aces, no runout left); and the standout — **every one of the 169 starting-hand classes' equity vs a random hand, combo-weighted across the full `preflop_169x169.npz` matrix (not a sample), averages to `0.49999999999999784`** (diff from 0.5: `2.16e-15`, pure float rounding) — a full-coverage symmetry identity exercising all 28,561 matrix cells at once, computed cheaply (0.2s) by reusing the already-locked Phase 3 matrix with fresh (equity-call-free) combo-conflict-count weighting rather than recomputing equity. **Check 5**: all 8 Appendix A.4 anchors reproduced to their full stored precision (`abs=5e-6`) — a precision mismatch surfaced here first (my earlier informal spot-check had truncated `AsAh vs 7s2d` to `0.88206` where the actual value is `0.882055698`, a ~4.3e-6 gap that would have made the test flake right at the tolerance boundary) and was fixed by regenerating every anchor's full-precision value directly from `equity_exact` rather than reusing a rounded transcription. Baselines locked: `evaluator_baseline.json` (all category counts, `distinct_five_card_values`, evaluator.py's source SHA-256 for future-drift detection) and `equity_baseline.json` (all 8 anchors to 8 decimal places). `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (87.6s) — blackjack area unaffected. **Per the plan's own gate discipline, Phases 6+ are now unblocked.** |
| 6 | Betting Tree & Abstraction | `[x] Completed` | Built `src/poker/tree.py` (`Decision`/`Terminal`/`Tree` node types, `build_tree(spec)`) and `src/poker/abstraction.py` (`preflop_buckets()`, `hand_strength_feature()`, `flop_buckets()`). **Deliberately scoped to preflop-only action** (no multi-street chaining) — a line that sees a flop is a single unresolved `Terminal(kind="showdown")`, matching Phase 10's own design of approximating flop-seeing lines via equity realisation rather than fully modelling further streets; the same single-street machinery is what Phase 10's `solve_spot.py` will reuse for one bounded postflop spot later. Plan's exact verification commands reproduced exactly: `build_tree(GameSpec(stack_bb=10.0, bet_sizes=(1.0,))).size()` → `(34, 12, 22)`; `len(set(preflop_buckets()))` → `169`. Confirmed the plan's own stated growth/shrink properties hold: adding a bet size strictly grows the tree `(34,12,22)→(94,32,62)`; halving the stack shrinks it `→(22,8,14)`; a 200bb stack stays bounded at `(58,20,38)` (pot-sized raises escalate geometrically, so deep stacks don't blow up the tree). **Minimum-raise legality implemented as a real rule, not an approximation, per the plan's explicit emphasis** — including the standard-but-subtle exception that a short all-in (a raise below the minimum, forced by a short stack) does NOT reopen the action for players who already acted on the current bet level, while players still queued keep full raise rights regardless. Verified end-to-end with two dedicated 3-handed constructed scenarios (`tests/poker/test_tree.py`): after a full raise and a call, a defender's short all-in leaves both the original raiser and caller with call/fold only, confirmed both at the internal state level (`can_raise` flags) and by building the actual resulting `Decision` node and checking its offered actions contain no `raise_*` key; the mirror case (short all-in from a player acting *before* someone still queued) confirmed the still-queued player retains full raise rights. **Found and fixed a variable-naming bug during test-writing** (not a logic bug — the logic was already correct, verified independently before the rename): the short-all-in branch's `already_acted` variable actually held the set of players *still queued* (not yet acted), with correctness only preserved because the downstream membership check happened to invert it correctly; renamed to `still_queued` for clarity, since a misleadingly-named variable is exactly the kind of thing that causes a *future* edit to introduce a real bug even though today's behaviour was right. Additional coverage: fold terminals are exactly zero-sum (chip conservation, no leaks); showdown terminals correctly carry no payoff; `fold` never offered when `to_call == 0`; heads-up BB correctly retains the "option" (check-or-raise) after SB limps, not an automatic street close; a 3-handed tree correctly starts action at UTG, not a blind. **`abstraction.py`, deliberately scoped**: `preflop_buckets()` ships the lossless 169-class abstraction (verified it exactly reproduces `ranges.hand_classes()`'s own grouping — every AA combo shares one bucket, distinct from every AKs combo). `flop_buckets()` ships the plan's *first* progression step only (`E[HS]`-style Monte Carlo feature + k-means, Euclidean distance) — the further "potential-aware equity-distribution histograms clustered by earth-mover distance" refinement the plan describes is explicitly deferred, since nothing downstream consumes it yet (Phase 7's CFR hasn't landed) and it is substantially more work than this version; documented as a scope decision, not an oversight. Verified `flop_buckets()` covers every one of a flop's 1,176 valid combos (`C(49,2)`) exactly once, respects the requested bucket count, and separates a clearly strong hand (top set on the test board) from a clearly weak one into different buckets rather than a degenerate single cluster. Added `scipy` to `requirements.txt` as a real dependency two phases earlier than the plan originally scoped it for (`scipy.cluster.vq.kmeans2`, not just Phase 8's `linprog`) — Dependencies section and Appendix updated accordingly, mirroring how Phase 3 handled `numba` arriving early. `tests/poker/test_tree.py` (10 tests) and `test_abstraction.py` (6 tests) — neither explicitly required by Phase 6's own verification block, added anyway matching this project's established per-module testing standard, especially given the correctness-criticality of betting-tree legality for everything Phase 7+ builds on top of it. `py -m pytest tests/poker/ -q`: **74/74 passed** (185.2s). `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (115.8s) |
| 7 | CFR+ Solver | `[x] Completed` | Built `src/poker/cfr.py` (vanilla / `cfr+` / `dcfr`, unified through one `_traverse` recursion differing only in which players update, how strongly regrets floor/discount, and how the strategy sum is weighted — chosen deliberately over three separate traversal implementations, since divergence between near-duplicate recursions is exactly the kind of bug class this project has already hit twice in the poker area) plus `save_state`/`load_state` checkpointing (regrets + strategy sums persisted to `.npz` + a JSON manifest, infoset keys round-tripped via `repr()`/`ast.literal_eval` since they're arbitrary hashable tuples). **Built `src/poker/toy.py` with `KuhnPoker` now, not deferred to Phase 8** — Phase 7's own plan-specified verification command imports `KuhnPoker` from `toy.py`, so CFR's correctness gate needed it to exist despite the file table nominally assigning `toy.py` to Phase 8; Phase 8 will extend the same file with `LeducPoker` and the LP cross-check apparatus, not create a separate one. Plan's exact verification command run: `solve(KuhnPoker(), iterations=10_000, variant='cfr+').game_value` → `-0.055738` (not textually "-0.055556" as the plan's own "≈" illustrative text showed, but within 1.8e-4 of the exact -1/18 and — critically — **monotonically closer with more iterations**, confirmed at 1k/5k/10k/50k/100k: `-0.056158 → -0.055816 → -0.055738 → -0.055636 → -0.055612`, converging cleanly toward truth rather than landing near it by coincidence). Measured convergence per variant at matched iteration budgets: **vanilla** (the reference implementation, built first per the plan's own ordering) reaches **4.5×10⁻⁷** of the exact value at 20,000 iterations; **dcfr** reaches **6×10⁻⁶** at 20,000; **cfr+** (the shipped default) is markedly slower on a game this tiny — **5.7×10⁻⁵** at 100,000 iterations — attributed to alternating updates halving each player's effective learning rate relative to vanilla's every-iteration-both-players updates, a real, expected characteristic on small games rather than a bug (CFR+'s advantage is asymptotic and shows more on larger trees; Phase 8's Leduc/toy-game gate will be the place to confirm this doesn't become a real problem at that slightly larger scale). **Verified the full Appendix A.5 frequency structure, not just game value** — the plan's own explicit warning that a game-value-only check "passes a structurally wrong solver" — at 60,000 `cfr+` iterations: the α-parameterised family's defining relationships all held (P1's K-bet-frequency ≈ 3α; P1's Q-call-after-check ≈ α+1/3; every "always/never" entry — P1 never bets/calls with J, always continues with K; P2 never continues with J, always continues with K, bets/calls Q or bluffs J at exactly 1/3) matched to within a few percentage points, not just the scalar game value. `tests/poker/test_cfr.py` (11 tests: per-variant convergence tightness, the full frequency-structure check, regret-matching mechanics, CFR+'s regrets never going negative — the literal invariant its name promises, average-strategy normalisation, checkpoint round-trip, invalid-variant rejection) and `tests/poker/test_toy.py` (13 tests covering `KuhnPoker`'s own mechanics independently of CFR — chance distribution sums to exactly 1 and covers all 6 deals, terminal/player/utility correctness against hand-derived payoffs for all 5 terminal lines, and the single most structurally important property: an infoset key must never leak the opponent's card, verified directly). CFR is fully deterministic (no RNG anywhere in the traversal), so every test tolerance above is a real bound, not a statistical one that could flake between runs. **Deliberately not built**: external-sampling MCCFR — the plan lists it explicitly as the last implementation step, "unnecessary for preflop and toy games", which is everything Phases 7/8/10 currently need solved; it becomes necessary once postflop abstraction enters the picture, not before. `py -m pytest tests/poker/ -q`: **98/98 passed** (247.9s). `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (136.6s) |
| 8 | **Validation Gate II** | `[x] PASSED (with one honestly-documented shortfall)` | Built `src/poker/exploit.py` (`best_response_value`, `exploitability`); extended `src/poker/toy.py` with `LeducPoker` (6 cards, 2 betting rounds at sizes 2/4, fixed-limit with a 2-bet cap, pair-beats-nonpair/higher-nonpair-wins/equal-nonpair-ties showdown rules — 5,520 terminals, 151 chance nodes, 468 infosets/player, enumerated and locked as a regression anchor) and `solve_sequence_form_lp` (an exact, LP-based Nash value independent of CFR). **A major bug found and fixed in `exploit.py` during this phase's own testing**: the first implementation of `best_response_value` recursed into every action and took `max()` independently per HISTORY — wrong in an imperfect-information game, because it implicitly lets the "best responder" see whatever hidden information (the opponent's card) distinguishes one history from another sharing the same information set, silently picking a *different* action per hidden realisation that a real player could never observe. It passed casual inspection (CFR's converged Kuhn strategy still looked right by game value and by all 12 Appendix A.5 frequencies) but computing exploitability against Kuhn's *exact, hand-constructed analytic equilibrium* (not CFR's approximation of it) gave ~0.276 where the true answer is exactly 0 — the mismatch was caught precisely because that hand-built equilibrium exists as an independent ground truth to test against, not because CFR looked wrong. Root-caused and fixed via a two-pass, deepest-first infoset resolution (enumerate every history reaching each responder infoset with its chance-and-opponent-only reach weight, resolve infosets in order from deepest to shallowest so a shallower infoset's continuation values can safely call into an already-decided deeper one, and pick the action maximising the *aggregated* weighted total across every history sharing that infoset — not a per-history max). Re-verified: the exact equilibrium now gives `br0 = -1/18`, `br1 = +1/18`, and **exploitability `4.16e-17`** (pure float noise) to machine precision; a degenerate "always fold" opponent strategy correctly shows `best_response_value = 1.0` for both players in both Kuhn and Leduc (winning exactly the ante, as Check 4 requires); CFR's own converged strategies now show exploitability that *decreases monotonically* with more iterations, as they should have all along. **The sequence-form LP** (`solve_sequence_form_lp`) was chosen over the plan's assumption that a smaller representation might suffice: a reduced-normal-form pure-strategy count for Leduc would be roughly `actions^468` (astronomically intractable), confirmed by first enumerating the actual game size before committing to an approach. Implemented from the standard LP-duality derivation (player 1's flow-constrained realisation-plan LP, dualised on player 2's side into value variables per player-2 infoset) and — critically — **validated on Kuhn poker first**, where the answer is independently known in closed form, before ever being trusted as the sole reference for Leduc: the LP reproduces `-1/18` to **`2.78e-17`** (machine precision). Only after that cross-check did it get run on Leduc, giving `-0.0856064...`, solved by `scipy.optimize.linprog` in ~0.2s for a ~1,000-sequence-per-player LP. **CFR-vs-LP cross-check on Leduc, and an honestly-documented shortfall**: a full-tree CFR traversal on Leduc's 5,520-terminal tree costs far more per iteration than Kuhn's tiny tree (~0.08–0.09s/iteration measured); an 8,000-iteration DCFR solve (744.3s) reached `game_value = -0.085586`, within **2.0e-5** of the LP's exact value — comfortably inside the plan's 1e-4 bar — but its **exploitability measured 9.174e-3**, short of the plan's stricter 1e-3 target (game value and exploitability are genuinely different metrics, and this gap is itself a real illustration of the plan's own warning that game-value convergence alone doesn't prove equilibrium). CFR+ was also measured on Leduc (500/1,000/2,000 iterations) and converges *worse* on exploitability there than DCFR (extrapolated ~0.023 at a matched 8,000 iterations vs DCFR's actual 0.00917), so it wasn't a faster alternative. Closing the remaining gap was estimated at roughly 672,000 further DCFR iterations (~17h at the measured rate) — a background commitment on the same order as Phase 3's 27h preflop-matrix build. Asked the user rather than either unilaterally spending ~17h or silently shipping an unmet bar; **the user chose to lock the honestly-achieved 9.174e-3 figure** into `data/poker/baselines/toy_game_baseline.json` rather than commit further compute, so this gate is recorded as passed-with-a-documented-shortfall on that one specific stricter sub-check, not as fully meeting every literal number in the plan. `tests/poker/test_toy_games.py`'s corresponding assertion checks against the actually-achieved 9.174e-3 (with headroom, not regressing) rather than asserting the unmet 1e-3 target as if it had been hit. **Test coverage**: `tests/poker/test_toy_games.py` (9 tests — the formal Check 1–4 gate: Kuhn game value + full frequency structure at the plan's tolerances, the LP cross-validated on Kuhn before Leduc, the CI-budget Leduc CFR-vs-LP check plus the locked-baseline check, exploitability-decreases-with-iterations, best-response-vs-always-fold on both games); `tests/poker/test_exploit.py` (5 new tests, anchored on the exact-equilibrium regression case that caught the bug above); 14 new `LeducPoker` mechanics tests added to `tests/poker/test_toy.py` (chance distributions, round-closure/raise-cap legality, fold/showdown payoffs including the pair-beats-nonpair and exact-tie cases, zero-sum, infoset privacy, and a hardcoded terminal/chance-node-count regression anchor) — one test-authoring bug caught and fixed along the way (calling `utility()` on a history that was actually non-terminal per `is_terminal()`, an invalid test input rather than a production bug). **`py -m pytest tests/poker/ -q`: 126/126 passed** (322.7s). `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (92.2s) — blackjack area unaffected. **Phase 10 is unblocked**, with the one caveat that Leduc's own exploitability figure — used only as a cross-check on the general-purpose CFR machinery, not consumed by anything downstream — sits at 9.174e-3 rather than the plan's original 1e-3 aspiration. |
| 9 | Push/Fold Equilibrium & ICM | `[x] Completed` | Built `src/poker/pushfold.py` (`solve_pushfold`, `build_pushfold_grid`, `solve_pushfold_icm`) and `src/poker/icm.py` (`icm_equity`, `bubble_factor`), solving directly over the already-locked Phase 3 169×169 matrix — no abstraction, no tree, no CFR, deliberately depending only on Phase 5 per the plan's own reasoning. **Two real bugs found and fixed during this phase's own testing.** (1) `solve_pushfold`'s first implementation used damped iterate-to-iterate updates (`new = 0.5*best_response + 0.5*previous`) and checked whether *that* iterate stopped changing — it never did: jam/call class counts cycled between ~65 and ~170 classes over 200 iterations with no sign of settling. Classical fictitious play (Robinson 1951) only guarantees convergence of the **time-average** of both players' pure best responses for zero-sum games, not the raw iterate — the identical "current strategy oscillates, average strategy converges" property CFR itself is built on (Phase 7). Fixed by best-responding to the opponent's running average (not their last move) and reporting the running average as the answer; re-verified cleanly convergent (call_pct stable to within ~0.3pp by 200 iterations, jam_pct within ~1pp by 300). (2) `icm_equity` crashed with `ZeroDivisionError` whenever every remaining player in the Harville recursion had exactly 0 chips (e.g. a player who just lost an all-in for their entire stack in an earlier branch) — Harville's stack-proportional formula is 0/0 there. Fixed by splitting the remaining finishing-order probability equally among zero-stack players; hand-verified the fix's *specific numbers* (not just that it stopped crashing) — `icm_equity([7000,3000,0],[50,30,20])` gives the zero-stack player exactly the last-place payout (20.0) with certainty, and splits the top two payouts between the other two as `44.0`/`36.0` (NOT proportional to their 7:3 chip ratio, since whichever one doesn't finish 1st is then *guaranteed* 2nd — the zero-stack player can never take it), confirmed by independent hand derivation. Plan's exact verification commands reproduced exactly: `icm_equity([5000,3000,2000],[50,30,20])` → `[38.393, 32.75, 28.857]`, summing to exactly `100.0`, matching Appendix A.6 to 5 decimal places; the 5000-chip leader holds *less* than 50% of the pool (38.4%) despite holding 50% of the chips. **The full 49-depth grid was built** (1.0–25.0bb in 0.5bb steps, 625.7s): monotonic decrease in both jam% and call% confirmed programmatically across *every* adjacent pair in the full grid (not spot-checked); 1.0bb → exactly 100%/100%; 25.0bb → 35.3%/17.0%. **A genuine, hand-verified finding that revises one of the plan's own stated structural facts**: "the call range is always tighter than the jam range" holds robustly from ~4bb onward but *inverts* at the shortest stacks (1.5–3.5bb, confirmed across the full grid: e.g. 1.5bb shows jam 98.2% vs call 100%) — because BB's pot-odds-only calling threshold (needs equity > ~16.7% at 1.5bb) is looser than SB's fold-equity-adjusted jamming threshold (needs equity > ~33.3%, since BB calling ~everything leaves jamming almost no fold-equity edge over a raw equity play). Verified via direct hand derivation: `32o`'s equity vs a random hand (32.3%) sits just under that 33.3% jam threshold at 1.5bb, explaining exactly why it's excluded from SB's jamming range while comfortably clearing BB's calling threshold. **Honest limitation**: no comparison against Miltersen & Sørensen's (2007) published exact jam/fold tables was possible — this environment has no network access to independently verify against them, and the plan's own alternative check ("structural facts that need no table at all": near-100% jam below ~2bb, monotonicity, call-tighter-than-jam) is what the test suite actually relies on for correctness evidence, documented plainly rather than fabricating an unverified agreement claim. **`solve_pushfold_icm`** reuses the same fictitious-play machinery, substituting ICM $EV deltas for chip deltas — made tractable by exploiting that ICM equity depends only on chip amounts, never on which hand is held, so the four relevant ICM states (fold / called-and-won / called-and-lost / opponent-folds) are computed once per confrontation via `icm_equity()`, not once per one of the 169 classes. Verified the expected directional effect on a genuine bubble (4 players, top 3 paid): the chip leader's ICM-adjusted calling range against a short stack's shove tightens dramatically versus the chip-EV baseline at the same effective stack (24.4% vs 44.5%) — exactly the expected "avoid unnecessary risk near the money" effect; a non-bubble, all-players-cash scenario showed a much milder, direction-varying effect, consistent with ICM pressure being genuinely context-dependent rather than a blanket tightening. `tests/poker/test_icm.py` (10 tests, including the zero-stack regression case with hand-derived exact numbers) and `tests/poker/test_pushfold.py` (10 tests, including the fictitious-play convergence regression case and the call-exceeds-jam crossover finding) — **146/146 poker tests pass total** (573.2s). `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (79.1s) — blackjack area unaffected. No grid data file was persisted to disk (unlike the preflop equity matrix) — the plan's file table lists no such artifact for this phase, and at ~625.7s to rebuild the full grid (vs the equity matrix's 27h), on-demand computation is cheap enough not to need caching yet. |
| 10 | Preflop Solve & Strategy Artifacts | `[x] Completed (with one honestly-documented shortfall, mirroring Phase 8)` | Built `scripts/poker/solve_preflop.py`, `src/poker/advisor.py` (`PreflopGame`, the equity-realisation terminal-value approximation, `advise()`), and `scripts/poker/solve_spot.py` (`SpotGame`, bounded postflop). **The real preflop tree proved far larger than Phase 7 anticipated, forcing an unplanned solver escalation**: the plan's own example spec (`hu-100bb-r5c3-s5`) builds a 23,869-node / 7,957-infoset card-agnostic betting tree, which combined with the lossless-but-large 169-class deal (169×169 = 28,561 chance outcomes) puts a single full-tree CFR traversal at ~680M node-visits/iteration -- discovered empirically at the start of this phase, not anticipated when Phase 7 explicitly deferred MCCFR as "unnecessary for preflop and toy games." Built external-sampling MCCFR (`solve_mccfr`, Lanctot et al. 2009) in `src/poker/cfr.py`, unified with the existing `_traverse` machinery's design conventions but sampling chance/opponent nodes to one action each rather than exploring every branch. **Two real performance bugs found and fixed while building this**: (1) `_traverse_mccfr` re-extracted and renormalised a probability array from the chance node's outcome list on every single iteration -- for `PreflopGame`'s 28,561-outcome root chance node this dominated per-iteration cost; fixed via `_cached_probs()`, keyed by the outcome list's object identity (stable across iterations for any game building its chance list once, harmless no-op for Kuhn/Leduc's tiny per-call lists) -- measured **~7.8x speedup** (160s→20.6s for 50k iterations on a 10bb/1-bet-size spec). (2) `solve_mccfr`'s final game-value computation called `_expected_value`'s FULL exact enumeration even for games far too large for it -- cProfile measured this one call consuming **99.96% of total runtime** (1881.5s of 1882.2s) for a 300-iteration test on a 30bb spec, completely defeating MCCFR's purpose; fixed by adding `exact_value: bool` (default `True`, correct for Kuhn/Leduc) and `_sampled_expected_value()` (Monte Carlo playout of the strategy profile, with a standard error per this repo's "no bare point estimates from Monte Carlo" rule) for `exact_value=False`, required for any large game -- a further **~10.2x speedup** (682.7s→66.9s for 5,000 iterations). Clean, isolated timing (eliminating concurrent-background-job contention that had earlier produced an inconsistent 27ms/iteration reading) confirmed **~1.6-1.9ms/iteration** on the real spec, bringing the plan's literal 1,000,000-iteration example from an initially-estimated 100+ hour cost down to a measured ~30 minutes. **A third bug, this one in `best_response_value`/`exploitability` (`src/poker/exploit.py`), was found for the same underlying reason**: exact enumeration over all 28,561 deals is equally intractable there; fixed by adding an optional `chance_sample` parameter (restricts both of Phase 8's already-validated two-pass algorithm's passes to a given deal subset) and `sampled_exploitability()` on top of it, using proper probability-weighted Monte Carlo sampling (`_sample_chance_outcomes`) rather than a naive uniform subset. **A genuine statistical bias was then discovered in `sampled_exploitability()` itself, via a regression test at Kuhn's exact analytic equilibrium (true exploitability = 0)**: at small `n_deals`, the reported mean is consistently, non-vanishingly positive (0.135 at n_deals=6, shrinking to 0.0086 at n_deals=2000) rather than fluctuating around 0 as sampling noise alone would. Root cause: this is "look-ahead" / selection bias, not noise that more trials at a fixed n_deals would average away -- each trial's own Pass 1 SELECTS the responder's best action via argmax over that trial's own noisy sampled totals, and the SAME trial's Pass 2 then EVALUATES that selection using the identical sample, so whenever two actions are genuinely close in true value (which an equilibrium guarantees for every on-path action), a small sample can make a not-quite-best action look best by chance and then confirm its own mistake -- a one-sided error that can only make the wrong pick look better, never worse. Documented at length in `sampled_exploitability`'s own docstring (the fix here was documentation plus corrected tests, not a code change -- the algorithm was already correct per-sample, only its convergence behavior was mischaracterized); the two tests that had asserted near-exact-equality at `n_deals=6` (wrongly reasoning that 6 samples "covers" Kuhn's 6 possible deals, not accounting for `_sample_chance_outcomes` sampling WITH replacement) were rewritten to check the actual documented properties instead: strictly positive at small n_deals, shrinking (not just noisy) at large n_deals, cross-validated against the exact computation only once `n_deals` is large enough (2000) for the bias to fall within a reasonable tolerance. **A fourth bug, a real correctness gap rather than a performance issue, was found while designing `solve_spot.py`**: `PreflopGame.utility()` never called `spec.pot_after_rake()` at showdown, silently understating the cost of seeing a flop for every real solve despite Phase 10's own Implementation section 1 explicitly specifying "rake from `spec.pot_after_rake`" -- the fold-terminal branch was already correctly unraked (matching `no_flop_no_drop`'s default exemption for hands that never see a flop), but the showdown branch had no rake call at all. Fixed by routing both branches through `spec.pot_after_rake(raw_pot, saw_flop=...)` (never reimplementing its `no_flop_no_drop`/cap logic locally), with a new regression test (`test_showdown_terminal_applies_rake_but_fold_terminal_does_not`) constructing the simplest showdown line (SB calls, BB checks back) and checking the exact raked value against `spec.pot_after_rake` directly. Caught before the real 100bb solve was trusted: an earlier background run (`bfvuibtb3`, 2016.9s) had completed under the UNFIXED rake-less game (`game_value=0.3192bb`, `exploitability≈2398.94mbb/g`) while this bug was still being found and fixed elsewhere in the session -- discarded as invalid once discovered, and the solve was relaunched from scratch under the corrected rules rather than kept as the answer. **Built `scripts/poker/solve_spot.py` (`SpotGame`), deliberately scoped to a COMPLETE (river) board rather than a general flop/turn spot** -- a real, stated scope decision, not a shortcut: with all 5 board cards fixed, every showdown has an EXACT value via `evaluator.evaluate(hole+board)`, so `solve_spot.py` needs NO equity-realisation approximation anywhere, unlike `PreflopGame`. Uses a "sunk-pot" convention (pre-street pot split evenly as both players' starting `committed_bb`) documented as having no effect on the solved strategy (CFR's regret computation depends only on differences between an action's value and the node's value at the same infoset, and a constant per-player offset cancels out of every such difference identically) -- only the reported absolute game-value/EV numbers are relative to that convention, stated once in the module docstring. Bounded by construction per the plan's own explicit requirement (the same DoS concern the blackjack `/api/simulate` route lives under): `solve_spot()` runs a small warm-up batch to measure iterations/second on the ACTUAL spot's tree size (which varies enormously with range width and bet-size count), then runs however many further iterations fit in a `max_seconds` wall-clock budget, capped at the requested `iterations` regardless of which limit binds first. **The real solve** (`py scripts/poker/solve_preflop.py --spec hu-100bb-r5c3-s5 --iterations 1000000 --exploit-deals 150 --exploit-trials 5 --value-samples 20000 --seed 0`, run under the corrected rake logic): **1,000,000 MCCFR iterations in 1778.5s (~29.6 min)**, `game_value = 0.1772 ± 0.0476 bb`, `abstraction_exploitability = 2271.62 ± 44.43 mbb/g` -- saved to `data/poker/strategy/hu-100bb-r5c3-s5/preflop.json`. **This does NOT meet the plan's own stated verification bar** ("finishes below 10 mbb/g"; "AA opens 100% from every position, 72o opens 0% from every position"): `advise('AA', 'BTN', [], GameSpec())` gives `{call: 24.7%, raise_1: 31.1%, raise_1.5: 10.2%, raise_2: 12.7%, raise_3: 15.0%, raise_99: 6.3%}` (never folds, but a quarter of the time just limps -- no real solved chart limps the best hand in the deck) and `advise('72o', ...)` gives `{fold: 38.8%, call: 26.9%, raise_1: 20.2%, ...}` (folding the worst hand over a third of the time is directionally plausible in isolation, but combined with AA's mushy frequencies points to the same root cause). **Root cause, diagnosed rather than assumed**: the card-agnostic tree's 7,957 infosets × 169 hand classes ≈ **1.34 million** realised infosets is a very large space to learn from only 1,000,000 sampled-update iterations (compare Phase 8's Leduc, which needed "only" 8,000 full-tree iterations to reach 9.174e-3 exploitability for 468 infosets/player -- roughly 1,000x fewer infosets than this abstraction, at a budget 125x smaller). A meaningful fraction of the reported 2,271.62 mbb/g also carries the look-ahead bias documented above, uncharacterized at this specific game's much larger stake scale (`exploit-deals=150` of 28,561 possible deals is a thinner relative sample than the n_deals=2000-of-6 ratio used to characterise the bias on Kuhn) -- disentangling bias from genuine under-convergence would need re-solving to recover the raw average-strategy dict (only the JSON-formatted, already-aggregated strategy was persisted), an additional ~30 minutes not spent given the decision below. **Asked the user rather than unilaterally committing to another multi-hour-or-more compute spend of highly uncertain payoff** (naive O(1/√T) scaling would put closing even a 10x exploitability gap at ~100x more iterations, roughly 50 hours, with no guarantee the abstraction converges cleanly at any reachable budget) or unilaterally shrinking the validated spec; **the user chose to lock the honestly-achieved, under-converged 1,000,000-iteration result** as v1's answer for the plan's literal example spec rather than spend further compute or change scope -- mirroring Phase 8's Leduc precedent (documented shortfall, not silently-met bar), but at a larger, more consequential gap that future work should revisit before this strategy file is treated as real playing advice. **Test coverage**: `tests/poker/test_advisor.py` (14 tests: `PreflopGame` mechanics, deal-outcome coverage/weighting, fold-terminal exactness, the new rake-vs-no-rake regression test, equity-realisation properties, `advise()` behavior/error handling), `tests/poker/test_solve_preflop.py` (7 tests: `parse_spec_key` round-tripping including the lossy-bet-size-count rejection, `format_strategy`, `_solver_hash`), `tests/poker/test_solve_spot.py` (14 new tests: river-only scope enforcement, deal-outcome card-removal correctness, fold/showdown zero-sum and exact-evaluator-matching payoffs including the tie-split and rake cases, the iteration AND wall-clock caps each independently, `format_strategy` frequency/label structure), `tests/poker/test_cfr.py` (18 tests, 3 new this phase: sampled-vs-exact game value agreement, `exact_value=True` never setting a standard error, standard error shrinking with more samples), `tests/poker/test_exploit.py` (8 tests, rewritten this phase: the corrected bias-shrinks-with-n_deals test replacing the two that wrongly asserted near-zero at `n_deals=6`). **`py -m pytest tests/poker/ -q`: 176/176 passed** (887.4s). `py tests/regression_test.py --fast`: **11/11 checks passed, ALL BASELINES PASS** (301.2s) -- blackjack area unaffected throughout, including through the two ~30-minute background solves and the two prior performance-bug fixes. |
| 11 | Bankroll, Variance & Risk of Ruin | `[x] Completed` | Built `src/poker/bankroll.py`: `risk_of_ruin` (the plan's own closed form, `exp(-2*B*w/s**2)`, `B` in bb and `w`/`s` in bb/100 -- returns certain ruin (`1.0`) rather than evaluating a wrong number for a non-positive win rate or bankroll, since the closed form assumes positive drift), `probability_of_downswing` (deliberately the SAME closed form as `risk_of_ruin`, not a separate derivation, since a depth-`D` downswing below a running peak is mathematically the identical first-passage problem as losing a `D`-sized bankroll outright), `required_bankroll_bb` (closed-form inverse of `risk_of_ruin`, solving for `B` directly rather than a numeric search), `win_rate_standard_error`/`win_rate_confidence_interval` (`s/sqrt(n/100)`, and the z-scaled interval around an observed rate), and `recommend_max_buyin` (the poker-shaped half-Kelly analogue -- defaults to holding risk of ruin at HALF the caller's stated `target_ror`, since the bet size here isn't continuously scalable the way a blackjack wager is, so the equivalent conservatism is applied to the risk target instead, buffering against `win_rate_bb100`/`stdev_bb100` being estimates rather than known constants). Plan's own two verification tables reproduced **exactly**: `risk_of_ruin` at `w=5,s=100` gives `36.8%`/`13.5%`/`0.67%` for bankrolls `1000`/`2000`/`5000` bb, and at `w=2,s=100` gives `67.0%`/`44.9%`/`13.5%` for the same three bankrolls (all six to within `0.05pp`, `abs=0.05`); `win_rate_standard_error` at `s=100` gives `10.0`/`3.16`/`1.00` bb/100 for `10,000`/`100,000`/`1,000,000` hands, with the corresponding `95%` CI half-widths `19.6`/`6.2`/`2.0` reproduced from the SAME function via the `1.96` z-score, not hardcoded separately. Additional coverage beyond the plan's own tables: `risk_of_ruin` strictly decreasing in both bankroll and win rate (monotonicity, not just point values); `required_bankroll_bb` round-trips through `risk_of_ruin` back to its own target for three different `(w, s, target)` triples, and independently recovers `~1000bb` when asked for the `36.8%` target the plan's table already anchors; `recommend_max_buyin` verified via the same round-trip discipline -- the buy-in it returns, converted back to a bankroll-bb figure, reproduces `risk_of_ruin(...) == effective_target_ror` (`safety_factor * target_ror`) to `1e-9`, rather than trusting the closed-form algebra by inspection alone; a larger `total_bankroll` strictly grows the recommended buy-in while holding the SAME effective risk target; a looser `safety_factor` strictly grows the recommended buy-in at a fixed `target_ror`. Input validation covered directly: non-positive win rate or bankroll each independently forces certain ruin rather than a nonsensical negative-exponent result; `target_ror` outside `(0, 1)` and non-positive `n_hands`/`total_bankroll` all raise `ValueError` rather than silently producing `inf`/`nan`. `tests/poker/test_bankroll.py`: **28/28 passed** (0.05s -- this module is pure closed-form arithmetic, no simulation or solving, so the whole suite is instant unlike every other Phase 10/11-adjacent file). `py -m pytest tests/poker/ -q`: **219/219 passed** (686.6s). `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (105.5s) -- blackjack area unaffected. |
| 12 | Flask API Blueprint | `[x] Completed` | Built `src/poker/api.py` (`poker_bp`, a Flask `Blueprint` under `url_prefix="/api/poker"`) and registered it in `app.py` via **exactly the two permitted lines** (`from src.poker.api import poker_bp` / `app.register_blueprint(poker_bp)`) -- no other line of `app.py` touched, verified directly (`git diff app.py` shows only those two added lines). **All 10 routes from the plan's table built**: `GET /spec`, `POST /equity`, `POST /range/parse`, `POST /range/equity`, `GET /preflop`, `POST /advise`, `GET /pushfold`, `POST /icm`, `POST /solve`, `POST /bankroll`. **Three discrepancies found between the plan's own Implementation-section pseudocode/verification text and what actually exists in this repo, resolved in favour of the real artifacts rather than the plan's earlier speculation** (documented in `api.py`'s own module docstring, not silently papered over): (1) the plan's verification block curls `/api/blackjack/grid` -- the blackjack area's real routes (untouched by this phase) live directly under `/api/` (`/api/grid`, confirmed still responding `200` after this phase's changes), never under an `/api/blackjack/` prefix that was never actually built. (2) the plan's startup pseudocode loads `preflop_169x169.npy` -- Phase 3 actually persisted `preflop_169x169.npz` (already reflected in that phase's own tracking-table entry); no separate load path was added here regardless, since `src.poker.pushfold.solve_pushfold` already loads and caches it internally. (3) the plan's pseudocode says the evaluator's "124MB" table loads lazily on first equity request -- that figure was Strategy B, which Phase 2 explicitly never built; the real (Strategy A) table is ~152KB, and nothing extra was needed here since `evaluate_batch`'s own lazy `_tables_cache` already handles this. **Startup registry**: `PREFLOP = {spec_key: json for every data/poker/strategy/{spec_key}/preflop.json that actually exists}`, discovered by scanning the directory rather than assuming a fixed list (there is no poker-side equivalent yet of `shipped_rulesets()` to enumerate "the specs that are SUPPOSED to exist") -- currently finds both `hu-10bb-r5c3-s5` (the small end-to-end validation solve) and `hu-100bb-r5c3-s5` (Phase 10's real, honestly-under-converged solve). `GET /preflop` and `POST /advise` on any spec NOT in this registry return a `400` naming the exact fix command (`py scripts/poker/solve_preflop.py --spec {key}`), mirroring the blackjack side's `/api/stake` convention for a missing edge model. **`POST /solve` bounded by construction, per the plan's own `[!WARNING]`, THREE separate ways**: (a) a pre-construction combo-pair estimate (`hero_range.n_combos() * villain_range.n_combos()`, a cheap upper bound computed WITHOUT ever building `SpotGame`'s full deal list) rejected above `MAX_SOLVE_COMBO_PAIRS = 20,000` with a `400` telling the caller to narrow their ranges -- verified directly: `hero_range="100%", villain_range="100%"` (1,326 x 1,326 raw combos) is rejected before any solving starts; (b) `iterations` hard-capped at `MAX_SOLVE_ITERATIONS = 200,000` regardless of what's requested; (c) `max_seconds` hard-capped at `MAX_SOLVE_SECONDS = 30.0` regardless of what's requested -- verified by requesting `999,999,999` iterations and `999,999` seconds and confirming the response's actual `iterations` stays at or under the hard cap. **Every Monte-Carlo-carrying response includes its standard error in the SAME object** (`/equity`'s MC path, `/solve`'s sampled game value and sampled exploitability) and **every solved-strategy response includes `abstraction_exploitability_mbb` and `iterations`** (`/preflop`, `/solve`), per the plan's own `[!IMPORTANT]` -- verified directly in tests, not just by inspection. Manually verified the plan's own worked example end-to-end via Flask's test client before writing the corresponding test: `AsAh` vs `KsKh`, no board -> `equities=[0.826366..., 0.173634...]`, `method="exact"`, `runouts=1712304` -- matching the plan's illustrative `{"equities":[0.819...,0.181...],"method":"exact","runouts":1712304}` in structure exactly (the plan's own illustrative equity numbers were for a DIFFERENT hand pair than its adjacent runout-count figure, an inconsistency in the plan text itself, not in this implementation -- `runouts=1712304` is the figure that actually round-trips against a real `AsAh` vs `KsKh` call, confirmed against Phase 5's own locked equity baseline). **A genuine, project-wide realisation surfaced while building `POST /equity`'s MC-path test**: `equity()`'s dispatcher can NEVER actually reach its own MC branch for a real Hold'em query through this API, for any number of players or board length -- `runout_count`'s maximum possible value over the entire valid input space is `comb(48, 5) = 1,712,304` (achieved at the widest input, 2 known hole-card pairs and an empty board), permanently below `EXACT_LIMIT = 5,000,000`; a first draft of the corresponding test wrongly assumed a 3-way preflop spot would force MC and failed, which is what surfaced this. Not a bug (the exact path being always-available is a genuine, useful property of this constant's chosen value, not an error), but a fact worth recording plainly since a future caller might otherwise expect `standard_error` to ever appear from this route and never see it; the test was rewritten to assert exactly this property (always-exact, even at the widest spot and a large requested `n_samples`) rather than deleted. **Test coverage**: `tests/poker/test_api.py` (25 new tests, using Flask's own test client exactly as `tests/test_app.py` already does for the blackjack side -- no real server/port needed): the plan's own worked equity example, the always-exact-for-Holdem finding above, malformed-input rejection on every POST route, range parsing/equity/rejection, the missing-preflop-spec error message's exact command text, advise frequency-sum and unrecognised-spec rejection, pushfold monotonicity (shorter stacks jam wider, reusing Phase 9's own locked finding as a cross-check) and out-of-range rejection, the plan's own Appendix A.6 ICM anchor reproduced through the route, `/solve`'s combo-pair pre-check and both hard caps, bankroll's risk-of-ruin/CI/stake-advice fields each independently gated on their own optional inputs being present, and a final confirmation that the existing (untouched) blackjack `/api/grid` route still responds normally. **`py -m pytest tests/poker/ -q`: 244/244 passed** (740.4s). `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (106.7s) -- blackjack area unaffected. |
| 13 | Web UI | `[x] Completed (three deliberate, documented scope reductions)` | Built `static/poker.html`, `static/css/poker.css` (a full duplicate of the blackjack app's own glassmorphism design system, per Phase 13's own explicit instruction that poker gets its own entry point so neither bundle grows a dependency on the other's files), and 8 files under `static/js/poker/` (`app.js` -- the shared shell: tab navigation, `fetch()` helpers, toasts, the one `buildHandGrid`/`RANKS`/`handLabel` 169-grid-construction routine every other tab's JS reuses rather than redefining its own row/column order; `equity.js`, `ranges.js`, `preflop.js`, `pushfold.js`, `solver.js`, `bankroll.js`, `trainer.js` -- one per tab). Registered a new `GET /poker` route in `app.py` (`send_from_directory(..., "poker.html")`, mirroring the existing `/` route exactly) -- a real `app.py` edit beyond Phase 12's "exactly two lines" constraint, but that constraint was explicitly scoped to Phase 12's own Blueprint registration, not to every future phase touching the file. **All 7 tabs from the plan's list built**: Equity, Ranges, Preflop, Push/Fold & ICM, Solver, Bankroll, Trainer. The plan's own `[!CAUTION]` disclaimer (ToS violation for real-time use, abstraction-not-real-table exploitability, variance dwarfing edge) is rendered as a persistent banner above every tab, not buried in a README. **The plan's own `[!NOTE]` -- refusing to collapse a mixed strategy to a pure one by default -- implemented directly**: the Preflop tab's default "Mixed" view renders every cell as a `.split` stack of proportionally-widthed action segments from the SOLVED strategy's real per-action frequencies (never the argmax action alone); a "Simplified" toggle exists for memorisation but is opt-in, exactly as the plan requires. **A real gap surfaced and fixed while building the Equity tab**: the plan's own text names the equity distribution histogram as the tab's "headline chart... the picture that explains why a 55% hand can be a check-fold", but `/api/poker/equity` (Phase 12) never exposed `equity_distribution()` (Phase 3) at all -- added a `distribution` field to the route's response, attached whenever the exact path is taken (which, per Phase 12's own always-exact-for-real-Holdem finding, is every valid query this route can ever receive), with a new passing test (`test_api_equity_includes_a_distribution_on_the_exact_path`) locking in that it sums to 1.0 per player. **Three deliberate, documented scope reductions, made explicitly rather than silently** (this phase's size -- 7 tabs including a from-scratch drag-select grid editor, a bounded-solve results view, and a training loop -- is comparable to or larger than the ENTIRE existing blackjack frontend, ~1,366 lines across 5 tabs, so scoping choices were unavoidable to ship a genuinely working v1 rather than 7 shallow stubs): (1) the Preflop and Trainer tabs are restricted to the BTN **open** situation only (no facing-a-raise/3-bet/4-bet action-history navigation) -- full breadcrumb navigation through arbitrary betting lines is real additional UI work, and "open" is the single most commonly consulted chart regardless; (2) the Trainer scores by **frequency-loss in percentage points** (best action's solved frequency minus the chosen action's), not bb EV, because `advisor.py`'s `Advice` dataclass (built in Phase 10, prior to this session) has never computed or persisted per-action EV -- the UI states this caveat directly rather than fabricating a number the backend has never produced, while still implementing the plan's actual underlying point ("scoring against frequencies... picking the 30% action is not an error"); (3) the Solver tab's exploitability "curve" is built from **several independent bounded `/api/poker/solve` calls at increasing iteration counts** (500 -> 20,000), each one a real, complete solve, plotted as a trend -- not one continuously-updating solve, since the `/solve` route (Phase 12) is synchronous and one-shot with no server-side streaming of intermediate iterations; stated explicitly in both the tab's own UI copy and `solver.js`'s docstring so "watch the exploitability curve fall in real time" (the plan's own phrasing) is never mistaken for a live/incremental solve. **Verification actually performed, and its honest limits**: every one of the 10 new/existing static routes (`/poker`, `css/poker.css`, all 8 `js/poker/*.js` files) confirmed serving `200` two independent ways -- Flask's test client AND a real `py app.py` dev server queried live over HTTP with `curl` (including a live `POST /api/poker/equity` round-trip reproducing the exact `0.826366.../0.173634...` figures already locked in Phase 12's own verification); every `getElementById` call across all 8 JS files cross-checked PROGRAMMATICALLY against `poker.html`'s real element ids (all resolved, zero dangling references) and every literal `class`/`className` string cross-checked against `poker.css`'s real class definitions (one harmless, unstyled-but-functional span found -- `.pc-top` on the Trainer tab's card display, which needs no CSS rule of its own since flex children lay out correctly regardless of an inline element's default `display` value -- not a bug, left as-is rather than padded with an unnecessary empty rule). **What was NOT done, stated plainly rather than implied by omission**: no live browser click-through was performed -- no browser-automation tool (Playwright or equivalent) is available in this environment, so per `CLAUDE.md`'s own instruction ("if you can't test the UI, say so explicitly rather than claiming success"), this is recorded here as an open item for the user's own manual pass, not silently assumed to work end-to-end from static analysis alone. No new Python tests were needed for the static assets themselves (there is no JS test framework set up in this repo); the one real behavioural change (`/api/poker/equity`'s new `distribution` field) is covered by an updated `tests/poker/test_api.py`. **`py -m pytest tests/poker/ -q`: 245/245 passed** (815.4s). `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (166.0s) -- blackjack area (including its own now-two-routes-deep `app.py`, `/` and `/poker` both confirmed still serving correctly) unaffected. |
| 14 | Regression Harness & CI | `[x] Completed` | Built `tests/poker/regression_test.py`, mirroring `tests/regression_test.py`'s own architecture deliberately (`CheckResult` dataclass, `--fast`/`--generate`/`--generate-spec` flags, `_print_report` formatting, exit code 0/1) rather than inventing a different shape for the poker side. **Six checks, in order**: (1) evaluator source-hash freshness + distinct-value/category counts, full `C(52,7)` outside `--fast`, a deterministic stride-3000 sample checked against known-exact PROPORTIONS (not counts, which a subsample can't reproduce) in `--fast`; (2) all 8 equity anchors recomputed exactly and compared bit-for-bit; (3) Kuhn/Leduc vs the analytic constants and the sequence-form LP, reusing Phase 8's own `test_toy_games.py` check functions directly rather than re-deriving them; (4) every shipped preflop strategy's solver-hash freshness and `abstraction_exploitability_mbb` against a NEW `data/poker/baselines/preflop_baseline.json`; (5) push/fold structural facts; (6) ICM property identities, reusing Phase 9's own `test_icm.py`/`test_pushfold.py` functions the same way Check 3 reuses Phase 8's. **`preflop_baseline.json` is a real Phase-10-era gap being filled here, not a fresh invention**: that phase's own Files line named `data/poker/baselines/preflop_baseline.json` as a deliverable ("Record the realisation factors in `preflop_baseline.json` alongside the strategy... because changing them changes the answer"), but the actual Phase 10 work (in an earlier session) only ever wrote the per-spec `data/poker/strategy/{spec}/preflop.json` files and never created the separate baseline file the plan called for -- created now via a `--generate`/`--generate-spec` flow that locks whatever's ALREADY shipped and already reviewed (never re-solving; a real MCCFR re-solve of the plan's 100bb example costs ~30 minutes, an unreasonable cost for this gate to own, mirroring exactly how `edge_model_baseline.json`'s expensive artifact stays out of the blackjack gate's own default path). **A genuine, real bug was caught on this new gate's very first actual run, not a contrived example**: `preflop:hu-10bb-r5c3-s5` FAILED its solver-hash-freshness check immediately -- that spec's shipped `preflop.json` had been solved in an earlier session, BEFORE this session's own rake-application fix to `advisor.py` (`PreflopGame.utility()` never called `spec.pot_after_rake()` at showdown until fixed this session, see Phase 10's tracking-table entry), meaning the shipped artifact was silently computing the WRONG game and nothing had caught it until this check existed. Re-solved under the corrected code (`py scripts/poker/solve_preflop.py --spec hu-10bb-r5c3-s5 --iterations 100000 ...`, **107.6s** -- the 10bb tree is dramatically smaller than 100bb's) and re-locked via `--generate-spec hu-10bb-r5c3-s5`: `abstraction_exploitability_mbb` moved from the old, unraked **540.35** to the corrected, raked **482.58** -- a real, expected, and now correctly-locked change, exactly the kind of drift this gate exists to catch. **Honest substitution, inherited rather than invented**: push/fold's check does NOT compare against Miltersen & Sorensen's (2007) published jam/fold tables -- Phase 9's own tracking-table entry already documented that this environment has no network access to verify against them; this gate reuses the SAME structural-fact substitute Phase 9's own tests established (near-100% jam/call at 1bb, monotonicity across the full grid, call-tighter-than-jam from ~5bb on, the hand-verified crossover at 1.5bb), stated in every one of that check's own `[PASS]` detail lines so the limitation is visible in the gate's own output, not just in a comment. **CI**: added a genuinely separate `poker-regression` job to `.github/workflows/regression.yml` (checkout, setup-python, install, `pytest tests/poker/ --ignore=tests/poker/regression_test.py -q`, `python tests/poker/regression_test.py --fast`) alongside the existing blackjack `regression` job, per the plan's own "two jobs means the summary line tells you which engine broke" instruction. **One necessary companion edit to the EXISTING blackjack job, despite the plan's "do not alter the existing one" phrasing**: its own unit-test step ran bare `pytest tests/ --ignore=tests/regression_test.py -q`, which -- now that `tests/poker/` exists as a subdirectory of `tests/` -- silently already collected and ran every poker test INSIDE the blackjack job, exactly the log-mixing the plan's two-jobs instruction is meant to prevent. Narrowed to `--ignore=tests/regression_test.py --ignore=tests/poker` so a poker failure can genuinely never appear in the blackjack job's log; the blackjack job's own gate script, purpose, and every other line are untouched -- this is a minimal, necessary fix to actually achieve the plan's stated goal, not a violation of its spirit. Built `docs/poker_guide.md` (8 sections mirroring `docs/system_guide.md`'s own role and depth: why an equilibrium solver instead of a transcribed chart, CFR+/MCCFR and the two performance bugs plus the look-ahead exploitability bias, the equity-realisation compromise and what it does/doesn't justify, the `abstraction_exploitability_mbb` naming convention and why, push/fold's exact-not-abstracted design and its one honest gap, the risk-of-ruin closed-form derivation, this regression gate itself, and a final "known limitations, stated plainly" section listing every open item from Phases 10/13 in one place). **Verification**: `py tests/poker/regression_test.py --fast`: **19/19 checks passed** (179.0s, then re-confirmed 19/19 after the hu-10bb fix). `py tests/poker/regression_test.py` (full mode, real `C(52,7)` enumeration branch): **19/19 checks passed** (436.9s). `py -m pytest tests/poker/ -q`: **245/245 passed** (900.6s). `py tests/regression_test.py --fast`: `11/11 checks passed, ALL BASELINES PASS` (177.1s) -- blackjack area unaffected. **This was the last phase in the build plan (0-14); every phase is now complete.** |

> [!IMPORTANT]
> Update this table **the moment a phase is implemented**, before starting the next one — never batch the updates at the end of a session. Each completed row's Notes must record what was actually built (including any deviation from this plan and why), and the **concrete numbers** from that phase's Verification block — the real category counts, the real exploitability in mbb/g, the real timings — not a restatement of the expected output. A tracking table that lags behind reality is worse than none, because it actively misleads the next session.

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|:--------:|------------|
| Evaluator subtly wrong (wheel straights, board-plays, kickers) | 🔴 Critical | Phase 5's full C(52,7) category enumeration is an exact equality test; two independent evaluators must agree element-wise on all 133,784,560 hands |
| Range-vs-range equity computed without joint card removal | 🔴 Critical | Phase 4 computes as a joint sum over non-conflicting combo pairs; Phase 5 tests a constructed spot where the naive method provably differs by >0.5pp |
| CFR converges to something that is not equilibrium | 🔴 Critical | Phase 8 gates on Kuhn's analytic value (−1/18) *and* its frequency structure, plus a scipy LP solution of Leduc; a game-value-only test would pass a structurally wrong solver |
| Abstraction exploitability quoted as real-game exploitability | 🔴 Critical | Field is named `abstraction_exploitability_mbb` everywhere — JSON, API, UI, this plan. Abstraction pathology (Waugh et al. 2009) means refinement can *increase* real exploitability |
| Equity-realisation terminal values distort the preflop solve | 🟡 Medium | Factors are recorded in `preflop_baseline.json` as part of the game definition, not as tuning; the approximation is stated at every point the solve's numbers are reported |
| Mixed strategies silently collapsed to pure | 🟡 Medium | Frequency dict is the only storage format, purity expressed as `{"action": 1.0}`; the UI's simplified view is opt-in and displays its EV cost |
| Memory exhaustion on the 7.7GB dev machine | 🟡 Medium | `int32` numpy tables never Python lists; chunked enumeration; bounded abstractions; `if __name__ == "__main__":` guards on every script |
| Solve endpoint used as a DoS | 🟡 Medium | `/api/poker/solve` bounded by iterations *and* wall-clock, with a node-count pre-check that rejects before starting |
| Blackjack baselines moved by poker work | 🔴 Critical | Strictly additive file layout; `py tests/regression_test.py --fast` is in **every** phase's verification block, not just the last |
| Cached solves drift from solver code | 🟡 Medium | Reuse `src/utils/cache_manager.py`'s hash-validated manifest — imported, not copied — with `GameSpec` **and** abstraction parameters in the key |
| Users treating solver output as a guarantee, or using it live | 🟡 Medium | Explicit in-app statement of the ToS problem, the abstraction caveat, and the variance caveat; win-rate CIs shown next to every observed win rate |

---

## Regression Guard

> [!CAUTION]
> **This area is additive to a repo with locked baselines.** `py tests/regression_test.py --fast` must pass before and after every phase of this plan. The blackjack engine (`src/engine/`, `src/strategy/dealer_probs.py`, `src/strategy/ev_solver.py`) is frozen; poker work that requires touching it is poker work that has been designed wrong.
>
> Once Phase 5 and Phase 8 lock `evaluator_baseline.json`, `equity_baseline.json`, and `toy_game_baseline.json`, those numbers are frozen too — and they are a stronger class of frozen than the blackjack baselines, because they are **combinatorial and analytic constants rather than measurements**. The count of seven-card flushes and the value of Kuhn poker do not change when the code improves. If either moves, the change is a bug, with exactly one exception: a documented change to the definition of the game or category being counted.
>
> If a later change *does* move a baseline:
> 1. Establish that the move is a **correctness fix**, not a regression, and write down the mechanism.
> 2. Record the before/after numbers in this plan's tracking table and in `docs/poker_guide.md`.
> 3. Re-lock deliberately with `py tests/poker/regression_test.py --generate-spec <key>` — never a blanket `--generate` that silently absorbs unrelated drift.
>
> A baseline that moves without all three steps is indistinguishable from a bug that was papered over.

---

## Appendix A — Known-Answer Fixtures (Phases 5, 8, 9)

Unlike the blackjack area's Appendix A — a transcription of published charts — most of what follows is **combinatorially or analytically exact**. Where a value is a transcription of a published figure it is marked as such, and the standing rule applies: when the engine and the transcription disagree, the exact identities adjudicate and the transcription gets corrected.

### A.1 — Seven-Card Hand Category Counts (exact; Phase 5, Check 1)

All C(52,7) = **133,784,560** seven-card hands, each classified by its best five:

| Category | Count | Share |
|---|---:|---:|
| Straight flush | 41,584 | 0.031% |
| Four of a kind | 224,848 | 0.168% |
| Full house | 3,473,184 | 2.596% |
| Flush | 4,047,644 | 3.025% |
| Straight | 6,180,020 | 4.619% |
| Three of a kind | 6,461,620 | 4.830% |
| Two pair | 31,433,400 | 23.496% |
| One pair | 58,627,800 | 43.823% |
| High card | 23,294,460 | 17.412% |
| **Total** | **133,784,560** | **100%** |

Note the ordering inversion that catches people: a seven-card **flush is rarer than a full house** — the opposite of the five-card ranking — because seven cards give so many more ways to make a boat. The hand *ranking* does not change; only the frequency does. A test that "fixes" this apparent anomaly is a test that has broken the evaluator.

### A.2 — Five-Card Hand Category Counts (exact; Phase 5, Check 3)

All C(52,5) = **2,598,960** five-card hands, mapping onto exactly **7,462** distinct hand values:

| Category | Count |
|---|---:|
| Straight flush (incl. royal) | 40 |
| Four of a kind | 624 |
| Full house | 3,744 |
| Flush | 5,108 |
| Straight | 10,200 |
| Three of a kind | 54,912 |
| Two pair | 123,552 |
| One pair | 1,098,240 |
| High card | 1,302,540 |
| **Total** | **2,598,960** |

### A.3 — Structural Identities (exact; Phases 1, 4, 5)

| Identity | Value | Phase |
|---|---:|:---:|
| Starting-hand combinations, C(52,2) | 1,326 | 4 |
| Strategically distinct starting hands | 169 | 1 |
| Flops, C(52,3) | 22,100 | 1 |
| Flops distinct up to suit isomorphism | 1,755 | 1 |
| Preflop heads-up runouts, C(48,5) | 1,712,304 | 3 |
| Preflop three-way runouts, C(46,5) | 1,370,754 | 3 |
| Flop-to-river runouts, C(45,2) | 990 | 3 |
| Turn-to-river runouts | 44 | 3 |
| Equities in any spot sum to | exactly 1.0 | 5 |
| All 169 classes vs a random hand, combo-weighted | exactly 0.500 | 5 |

### A.4 — Preflop Equity Anchors (exact, computed by `equity_exact` in Phase 3; Phase 5, Check 5)

Heads-up, all five board cards run out, hero's equity including half of ties, **suits pinned exactly** — suit configuration moves these values by up to ~1.4pp, so "AA vs KK" is not a well-defined test case and `AsAh vs KsKh` is. These superseded an earlier from-memory transcription in this table (v1 draft) that had the shared-suit direction backwards — that draft claimed *fewer* shared suits meant *higher* equity for the pair; the real, now-exactly-computed relationship is the opposite (below), caught the moment `equity_exact` existed to check it against.

| Matchup | Hero equity (exact) | Note |
|---|---:|---|
| `AsAh` vs `KsKh` (2 shared suits) | 82.637% | More shared suits denies the underdog more flush outs, raising the pair's equity |
| `AsAh` vs `KsKd` (1 shared suit) | 81.946% | |
| `AsAh` vs `KdKc` (0 shared suits) | 81.255% | The classic "82%, 4.5:1" figure lands inside this ~1.4pp band depending on suits, never above it |
| `AsAh` vs `7s2d` | 88.206% | The widest realistic preflop gap |
| `AsAh` vs a random hand | 85.198% ± 0.109% (95% CI, n=400,000) | Monte Carlo, not exact — a true combo-weighted exact average over all 1,225 remaining opponent hands needs Phase 4's `Range` machinery and is deferred there |
| `AsKs` vs `QhQd` (no shared suit) | 46.214% | The classic "race" |
| `AsKs` vs `QsQd` (K shares suit w/ a Q) | 45.883% | |
| `AsKd` vs `QhQc` (offsuit) | 42.835% | Same race, offsuit — losing the backdoor-flush suit costs the AK side ~3.4pp here, more than the flush-blocker effect above |
| `AsKd` vs `2h2c` | 46.960% | Small pair a slight favourite over two overcards |

Tolerance for Phase 5, Check 5: **exact match** (float equality against the locked baseline) for the exact rows; the Monte Carlo row's tolerance is a multiple of its own reported standard error. There is no published-reference tolerance band here — `equity_exact` enumerates every one of C(48,5) = 1,712,304 runouts with zero sampling error, so these figures are ground truth, not an approximation to be compared against a book with a fudge factor.

### A.5 — Kuhn Poker Equilibrium (analytic; Phase 8, Check 1)

Three cards J/Q/K, one-chip ante, one-chip bet. The equilibria form a one-parameter family in **α ∈ [0, 1/3]**:

| Player | Situation | J | Q | K |
|---|---|---|---|---|
| P1 | First action (bet freq.) | α | 0 | 3α |
| P1 | Facing a bet after checking (call freq.) | 0 | α + 1/3 | 1 |
| P2 | Facing a bet (call freq.) | 0 | 1/3 | 1 |
| P2 | Facing a check (bet freq.) | 1/3 | 0 | 1 |

**Game value to player 1: −1/18 ≈ −0.0555556.**

The gate asserts all four rows plus the game value — not the value alone, which a structurally wrong solver can reproduce by accident.

### A.6 — ICM Worked Example (exact; Phase 9)

Malmuth-Harville, three players, stacks 5,000 / 3,000 / 2,000, payouts 50 / 30 / 20:

| Player | Chips | Chip share | ICM equity | Equity per 1,000 chips |
|---|---:|---:|---:|---:|
| A | 5,000 | 50.0% | **38.393** | 7.68 |
| B | 3,000 | 30.0% | **32.750** | 10.92 |
| C | 2,000 | 20.0% | **28.857** | 14.43 |
| **Total** | 10,000 | 100% | **100.000** | |

The chip leader holds 50% of the chips and 38.4% of the prize pool; the short stack holds 20% of the chips and 28.9% of the pool. Marginal chip value falls monotonically with stack size — this is the entire content of ICM, and the property test in Phase 9 asserts exactly it.

---

## Appendix B — Open Decisions

| # | Decision | Recommendation | Owner |
|---|---|---|---|
| 1 | Same repo as blackjack, or a new sibling repo? | **Same repo** — `C:\Python\Cards` is already a cards repo, the `.agents/` contract and cache manager are reused, and the additive layout keeps the blackjack gate as an ever-present guard. Implies renaming the GitHub repo from `Blackjack_Strategy_Engine` to something area-neutral (GitHub redirects the old URL) | User |
| 2 | Separate `/poker` SPA page, or a sixth tab in the blackjack app? | **Separate page** — seven poker tabs plus five blackjack tabs in one bar is unusable, and the bundles stay independent | Recommended |
| 3 | Heads-up only, or 6-max, in v1? | **Heads-up first**, 6-max preflop-only after Phase 10 passes. Multiway postflop is a different-sized problem | Recommended |
| 4 | Postflop scope | **Bounded single-spot solves only.** Full-tree HUNL and DeepStack-style continual resolving are explicitly out of scope for v1 | Recommended |
| 5 | Flop bucket count for the initial abstraction | Start at 200; it is a cache-key parameter, so raising it later costs a re-solve rather than a rewrite | Recommended |
| 6 | Where do equity-realisation factors come from? | Fit from bounded postflop solves once Phase 10 exists; hardcoded literature values in the interim, recorded in the baseline as part of the game definition | **Open — the plan's weakest link** |
| 7 | Default ICM model | Malmuth-Harville — every published table uses it, so comparability beats a small accuracy gain. Exposed as a parameter, never hardcoded | Recommended |
| 8 | Default rake | 5% capped at 3bb, `no_flop_no_drop=True` — a common online cash configuration. Rake-free solves available by setting `rake_pct=0`, but never the default: rake-free is a different game and its answers are wrong for real tables | Recommended |
| 9 | `numba` as a hard dependency? | **Resolved in Phase 3: yes.** The policy ("numpy-vectorise first, escalate only if measured too slow") did trigger — unlike the blackjack area, which never needed to escalate — once the Phase 3 preflop-equity-matrix build's estimated runtime dropped from ~8.4 days to ~23h with it. Real dependency now, `requirements.txt` updated, pure-numpy fallback retained | Resolved |
| 10 | Hand-history import / HUD integration | **Out of scope, deliberately.** Real-time assistance during online play violates site terms of service; off-table review of exported histories is a defensible v2 feature, live integration is not | Recommended |
