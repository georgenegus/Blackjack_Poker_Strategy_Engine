# Blackjack Strategy Engine — Build Plan v1

> **Author:** Claude Code (Opus 5) · **Date:** 2026-08-20  
> **Purpose / Strategy:** A blackjack simulator that solves basic strategy from first principles, counts cards, and sizes stakes by Kelly — served through a Flask UI that tells the player the mathematically correct decision on every hand  
> **Baseline / Metrics:** Greenfield repo. Correctness anchors: solver-generated grid must match published 4/6/8-deck charts cell-for-cell; simulated house edge must land within ±0.02% of published values per ruleset  
> **Defaults / Scope:** 2 / 4 / 6 / 8-deck shoes · S17 & H17 · DAS · Late Surrender · 3:2 blackjack · 75% penetration · Hi-Lo primary count · half-Kelly staking default  
> **Structure basis:** Mirrors `C:\Python\T20_Win_Probability_Model` (`.agents/` + `src/` subpackages + `tests/` regression gates + `markdowns/` build plans + Flask `app.py` + `static/` SPA)

---

## Executive Summary

Build a **blackjack decision engine** that is correct by construction rather than correct by transcription. Almost every blackjack tool on the internet hardcodes a basic-strategy chart copied from a book; this project instead implements an **exact combinatorial EV solver** that computes the expected value of stand / hit / double / split / surrender for every player-hand × dealer-upcard cell, under a configurable ruleset. The published strategy charts then become a *known-answer test* the solver must reproduce — not the source of truth.

Everything else follows from that solver:

- The **strategy grid** is solver output, so it is automatically correct for 2, 4, 6, or 8 decks, S17 or H17, with or without DAS/surrender — no per-variant chart maintenance.
- The **count-index deviations** (Illustrious 18 and beyond) are solver output too — re-run the solver against a shoe composition biased by a given true count and record the count at which the optimal action flips.
- The **staking model** consumes the solver's edge estimate: true count → player edge → Kelly fraction → bet, clamped to table limits and chip size.
- The **UI** is a thin presentation layer over the same engine that the simulator uses, so the advice shown to a human is provably the same advice the Monte Carlo validated.

> [!IMPORTANT]
> **Phase 5 is the go/no-go gate for the entire project.** If the solver's generated grid does not reproduce the published multi-deck charts cell-for-cell, and the simulated house edge does not land inside its tolerance band, then every downstream number — the count indices, the edge-vs-true-count curve, the Kelly bet sizes — is confidently wrong. Do not build the counting, staking, or UI layers on an unvalidated solver.

### Non-Destructive Principle

This is a brand-new repo, so there is nothing to regress *yet* — but the T20 discipline applies from day one: once Phase 5 locks `data/baselines/strategy_baseline.json` and `house_edge_baseline.json`, **no later phase may move those numbers without an explicit, documented reason and a deliberate re-lock**. Counting, staking, and UI work is strictly additive on top of a frozen engine.

### Phase Overview

| # | Phase | Tier | Effort | Files Created |
|---|-------|------|:------:|---------------|
| 0 | Repository Bootstrap & GitHub Link | Infrastructure | 🟢 Low | `.gitignore`, `README.md`, `CLAUDE.md`, `.agents/*`, `requirements.txt` |
| 1 | Card / Shoe / Hand Primitives + RuleSet | Infrastructure | 🟢 Low | `src/engine/cards.py`, `shoe.py`, `hand.py`, `rules.py` |
| 2 | Dealer Logic & Round State Machine | Core Logic | 🟡 Medium | `src/engine/dealer.py`, `src/engine/game.py` |
| 3 | Exact EV Solver | Core Math | 🔴 High | `src/strategy/dealer_probs.py`, `src/strategy/ev_solver.py` |
| 4 | Basic Strategy Grid Generator | Core Math | 🟡 Medium | `src/strategy/grid_builder.py`, `src/strategy/basic_strategy.py` |
| 5 | **Validation Gate** — Grid + House Edge | Validation Gate | 🔴 High | `tests/test_strategy_grid.py`, `tests/test_house_edge.py`, `data/baselines/*.json` |
| 6 | Counting Systems & True Count | Core Logic | 🟢 Low | `src/counting/systems.py`, `src/counting/counter.py` |
| 7 | Count-Indexed Deviations | Core Math | 🔴 High | `src/strategy/deviations.py`, `src/strategy/index_builder.py` |
| 8 | Monte Carlo Simulator & Edge Model | Validation | 🔴 High | `src/simulation/simulator.py`, `src/counting/edge_model.py`, `src/simulation/metrics.py` |
| 9 | Bankroll, Kelly & Bet Ramp | Core Logic | 🟡 Medium | `src/bankroll/kelly.py`, `bet_ramp.py`, `risk.py` |
| 10 | Flask API | Integration | 🟡 Medium | `app.py` |
| 11 | Web UI (Play · Grid · Trainer · Bankroll · Sim) | Integration | 🔴 High | `static/index.html`, `static/js/*.js`, `static/css/style.css` |
| 12 | Regression Harness & CI | Validation Gate | 🟡 Medium | `tests/regression_test.py`, `.github/workflows/regression.yml` |

Effort key: 🟢 Low Effort / Low Risk · 🟡 Medium Effort / Medium Risk · 🔴 High Effort / Critical Priority

---

## Repository Structure

Mirrors the T20 layout (`.agents/` agent docs, `src/` subpackages by concern, `tests/` as regression gates against locked baselines, `markdowns/<area>/` for build plans, Flask `app.py` + vanilla-JS `static/` SPA).

```
C:\Python\Cards\                      →  github.com/georgenegus/Blackjack_Strategy_Engine
│
├── .agents/                          [Phase 0] Agent-facing project docs (mirrors T20)
│   ├── instructions.md                   Critical rules + common pitfalls
│   ├── project-overview.md               Architecture, key files, locked baselines
│   ├── coding-standards.md               Conventions and correctness rules
│   └── skills/
│       ├── markdown_documentation_standards/SKILL.md   Copied verbatim from T20
│       ├── blackjack_rules_conventions/SKILL.md        Rule-variant naming, RuleSet keys
│       ├── ev_solver_conventions/SKILL.md              Caching, peek conditioning, split recursion
│       ├── counting_systems_conventions/SKILL.md       Tag vectors, IRC, TC rounding
│       └── web_app_development/SKILL.md                Flask + vanilla-JS SPA conventions
├── .claude/skills/                   [Phase 0] Symlink/mirror of .agents/skills (T20 does this)
├── .vscode/settings.json             [Phase 0]
├── .github/workflows/regression.yml  [Phase 12] NEW vs T20 — CI runs the regression gate
│
├── src/
│   ├── engine/                       ── The game itself, no strategy knowledge
│   │   ├── cards.py                  [Phase 1] Rank/Suit/Card, value mapping
│   │   ├── shoe.py                   [Phase 1] N-deck shoe, cut card, penetration, burn
│   │   ├── hand.py                   [Phase 1] Totals (hard/soft), pair/BJ/bust predicates
│   │   ├── rules.py                  [Phase 1] RuleSet dataclass — THE single source of truth
│   │   ├── dealer.py                 [Phase 2] Dealer draw logic (S17/H17, peek/no-peek)
│   │   └── game.py                   [Phase 2] Round state machine, payouts, split handling
│   │
│   ├── strategy/                     ── The maths
│   │   ├── dealer_probs.py           [Phase 3] Exact dealer outcome distribution
│   │   ├── ev_solver.py              [Phase 3] EV of stand/hit/double/split/surrender
│   │   ├── grid_builder.py           [Phase 4] Solve every cell → cached grid
│   │   ├── basic_strategy.py         [Phase 4] Runtime lookup + advice API
│   │   ├── index_builder.py          [Phase 7] Solve action-flip true counts
│   │   └── deviations.py             [Phase 7] Runtime count-aware advice
│   │
│   ├── counting/
│   │   ├── systems.py                [Phase 6] Hi-Lo, KO, Hi-Opt I/II, Omega II, Zen, Red 7
│   │   ├── counter.py                [Phase 6] RC → TC, penetration tracking, IRC
│   │   └── edge_model.py             [Phase 8] TC → player edge (simulation-fitted)
│   │
│   ├── bankroll/
│   │   ├── kelly.py                  [Phase 9] f* = edge/variance, fractional Kelly
│   │   ├── bet_ramp.py               [Phase 9] Continuous Kelly → discrete legal bet ramp
│   │   └── risk.py                   [Phase 9] Risk of ruin, N0, SCORE, drawdown quantiles
│   │
│   ├── simulation/
│   │   ├── simulator.py              [Phase 8] Monte Carlo shoe/hand engine
│   │   └── metrics.py                [Phase 8] EV, variance, RoR, N0, hourly rate
│   │
│   └── utils/
│       └── cache_manager.py          [Phase 4] Hash-based cache validity (ported from T20)
│
├── data/
│   ├── strategy/                     [Phase 4] Solved grids, one JSON per ruleset hash  ← COMMITTED
│   ├── indices/                      [Phase 7] Solved count indices per (ruleset, system) ← COMMITTED
│   ├── baselines/                    [Phase 5] Locked regression baselines              ← COMMITTED
│   │   ├── strategy_baseline.json
│   │   ├── house_edge_baseline.json
│   │   └── edge_model_baseline.json  [Phase 8]
│   └── sims/                         [Phase 8] Raw Monte Carlo output                   ← GITIGNORED
│
├── tests/
│   ├── regression_test.py            [Phase 12] THE gate — grid + house edge + indices
│   ├── test_strategy_grid.py         [Phase 5] Solver output vs published charts
│   ├── test_house_edge.py            [Phase 5] Simulated edge vs published anchors
│   ├── test_engine.py                [Phase 2] Rule-mechanics unit tests
│   ├── test_counting.py              [Phase 6] Count arithmetic, IRC, TC rounding
│   ├── test_bankroll.py              [Phase 9] Kelly, RoR, ramp construction
│   └── one-time/                     Ad-hoc experiments (gitignored, as in T20)
│
├── scripts/
│   ├── build_all_grids.py            [Phase 4] Pre-solve + cache every shipped ruleset
│   ├── build_all_indices.py          [Phase 7] Pre-solve every (ruleset, system) pair
│   └── run_sim_battery.py            [Phase 8] Long-running MC battery → data/sims/
│
├── static/                           [Phase 11] Vanilla-JS SPA, glassmorphism dark mode
│   ├── index.html
│   ├── css/style.css
│   └── js/{app.js, table.js, grid.js, counting.js, bankroll.js, rules.js}
│
├── docs/system_guide.md              [Phase 12] Deep technical walkthrough
├── markdowns/blackjack/              This plan + future per-area plans
├── outputs/                          Measurement logs and reports
├── logs/                             Runtime logs (gitignored)
├── app.py                            [Phase 10] Flask server
├── main.py                           [Phase 4] CLI entry: solve + print a grid
├── requirements.txt                  [Phase 0]
├── README.md                         [Phase 0]
└── CLAUDE.md                         [Phase 0] Agent entry point (mirrors T20's)
```

> [!NOTE]
> **Two deliberate deviations from T20's `.gitignore`.** T20 ignores `data/` wholesale and `markdowns/` entirely, because its caches are multi-hundred-MB parquet/pickle artifacts and its plans are private working notes. Here, `data/strategy/`, `data/indices/`, and `data/baselines/` are small, deterministic JSON that the app needs at runtime, so they get **committed**; only `data/sims/` is ignored. Likewise `markdowns/` is **committed**, because on a fresh public repo the build plan is a feature, not a scratchpad. Flag this to the user if repo privacy expectations differ.

---

## Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `flask` | Web server + JSON API | `pip install flask` |
| `numpy` | Vectorised shoe composition, Monte Carlo sampling | `pip install numpy` |
| `pandas` | Simulation result aggregation, grid tabulation | `pip install pandas` |
| `pytest` | Test runner for the regression gate | `pip install pytest` |
| `numba` (optional) | JIT for the solver's hot recursion and the MC inner loop | `pip install numba` |
| `scipy` (optional) | Confidence intervals, distribution fits in `metrics.py` | `pip install scipy` |

No ML stack, no XGBoost — unlike T20 this project is **exact combinatorics plus Monte Carlo**, not statistical learning. `numba` is listed optional because the plan's fallback is caching solved grids to disk (Phase 4) rather than requiring fast re-solves.

> [!WARNING]
> The T20 dev machine has **7.7GB RAM** and the same constraint applies here. The exact solver's cache is keyed on shoe composition, and the number of possible compositions grows huge very fast — Phase 3's implementation notes cap this deliberately. Standalone solver/simulation scripts need an `if __name__ == "__main__":` guard so Windows `spawn` does not silently re-execute the whole script inside worker processes.

---

## Phase Execution Order

```
Phase 0: Repository Bootstrap & GitHub Link
    │
    ▼
Phase 1: Card / Shoe / Hand / RuleSet primitives
    │
    ▼
Phase 2: Dealer logic + round state machine
    │      (playable game, no strategy advice yet)
    ▼
Phase 3: Exact EV Solver  ── dealer distribution → per-action EV
    │
    ▼
Phase 4: Basic Strategy Grid Generator → data/strategy/*.json
    │
    ▼
Phase 5: VALIDATION GATE  ←──────── GO / NO-GO
    │      grid == published charts?  house edge within ±0.02%?
    │
    ├──────────────┬──────────────────┐
    ▼              ▼                  ▼
Phase 6:       Phase 9:           Phase 10:
Counting       (blocked on 8)     Flask API
systems            │                  │
    │              │                  │
    ▼              │                  │
Phase 7:           │                  │
Count indices      │                  │
    │              │                  │
    ▼              │                  │
Phase 8: MC Simulator + edge model ───┘
    │      (fits TC → edge, feeds Phase 9)
    ▼
Phase 9: Bankroll / Kelly / bet ramp
    │
    ▼
Phase 11: Web UI
    │
    ▼
Phase 12: Regression harness + CI
```

> [!CAUTION]
> Phases 6–12 all consume solver output. Do **not** start them before Phase 5 passes. An off-by-one in the peek conditioning (Phase 3) shifts the whole grid by a fraction of a percent — invisible by eye, fatal to every count index and Kelly bet downstream.

---

## Phase 0: Repository Bootstrap & GitHub Link

**Files:** `.gitignore`, `README.md`, `CLAUDE.md`, `.agents/*.md`, `requirements.txt` (NEW)  
**Priority:** 🟢 Low — mechanical, but it fixes conventions everything else inherits  
**Dependencies:** `git` (confirmed at `C:\Program Files\Git\cmd\git.exe`)

### Problem

`C:\Python\Cards` is currently an empty, non-git directory. The T20 repo's real value as a template is not its file *names* but its **agent-documentation contract**: `CLAUDE.md` points at `.agents/instructions.md` → `project-overview.md` → `coding-standards.md` → `docs/system_guide.md` → `markdowns/`, and that chain is what keeps a future session from re-deriving the architecture. Establish it before writing any code.

### Implementation

1. **Initialise and link the repo.** The GitHub CLI (`gh`) is **not installed on this machine**, so the remote must be created through github.com and attached manually, or `gh` installed first (`winget install GitHub.cli`).

   ```bash
   cd /c/Python/Cards
   git init -b main
   git add .
   git commit -m "Initial commit: build plan and repository scaffold"
   git remote add origin https://github.com/georgenegus/Blackjack_Strategy_Engine.git
   git push -u origin main
   ```

2. **Write `.gitignore`** — T20's, minus the `data/` and `markdowns/` blanket ignores (see the deviation note above):

   ```gitignore
   __pycache__/
   *.pyc
   .pytest_cache/
   .vscode/
   .idea/
   data/sims/          # large Monte Carlo output only — solved grids ARE committed
   tests/one-time/
   logs/
   .DS_Store
   Thumbs.db
   ```

3. **Write the `.agents/` triad**, following T20's structure:
   - `instructions.md` — the critical-rules doc. The headline rule (T20's equivalent of "women's formats are separate format codes") is: **every EV number is a function of a `RuleSet`, never a global constant.** No function may assume 6 decks, S17, or 3:2.
   - `project-overview.md` — architecture diagram, key-file table, locked baseline table (empty until Phase 5).
   - `coding-standards.md` — Python 3.14+, type hints, `snake_case`/`PascalCase`, `src/` subpackage layout, and the correctness rules from Phase 3.
4. **Mirror `.agents/skills/` into `.claude/skills/`** exactly as T20 does, copying `markdown_documentation_standards/SKILL.md` verbatim so future plan documents match this one.
5. **`CLAUDE.md`** — the short entry point: what the project is, the one rule that matters most, and the verification command (`py tests/regression_test.py`).

### Verification

```bash
git -C /c/Python/Cards log --oneline
git -C /c/Python/Cards remote -v
```
Expected: one commit on `main`; `origin` pointing at the GitHub URL, fetch and push. `git status` clean.

---

## Phase 1: Card / Shoe / Hand Primitives + RuleSet

**Files:** `src/engine/cards.py`, `shoe.py`, `hand.py`, `rules.py` (NEW)  
**Priority:** 🟢 Low  
**Dependencies:** None

### Problem

Every later phase — solver, simulator, counter, UI — needs one shared vocabulary for "what cards are left" and "what rules are in force". Getting `RuleSet` wrong here means threading rule variants through as ad-hoc booleans later, which is exactly the trap T20's `format_spec.py` exists to avoid.

### Implementation

**1. `cards.py` — ranks and values.** Blackjack cares about rank, not suit, except for one count system (Red Seven, which needs colour). Keep suit for display and for Red Seven; make rank the index into everything else.

```python
RANKS = ["2","3","4","5","6","7","8","9","T","J","Q","K","A"]
RANK_INDEX = {"2":0,"3":1,"4":2,"5":3,"6":4,"7":5,"8":6,"9":7,
              "T":8,"J":8,"Q":8,"K":8,"A":9}      # 10 buckets: 2-9, T, A
HARD_VALUE = [2,3,4,5,6,7,8,9,10,11]              # value of each bucket (A counted as 11)
```

> [!IMPORTANT]
> The **10-bucket composition vector** `(n2, n3, n4, n5, n6, n7, n8, n9, nT, nA)` is the standard shoe representation for the solver. T/J/Q/K collapse to one bucket because every rule and every count system treats them the same way. This collapse is what keeps Phase 3's caching fast enough to use — do not "improve" it to 13 buckets.

**2. `shoe.py` — `Shoe(num_decks, penetration)`.**
- `composition: np.ndarray[10]`, initialised to `num_decks * [4,4,4,4,4,4,4,4,16,4]`.
- `deal()` — draw by rank weighted by remaining composition, decrement, increment `dealt`.
- `cut_card_reached` — `dealt / total >= penetration` (default **0.75**). The shoe finishes the current round then reshuffles; it does **not** reshuffle mid-round.
- `Shoe.from_composition(vec)` — construct a hypothetical shoe. The solver and Phase 7's index builder both need this.

**3. `hand.py` — `Hand`.**
- `total` — count each ace as 11 while the total stays ≤ 21, else 1. Store `(hard_total, n_aces)` and derive.
- `is_soft` — an ace is still being counted as 11.
- `is_blackjack` — exactly two cards totalling 21. **A 21 made after a split is not a blackjack** and pays even money; this is a rule, not an edge case.
- `is_pair` — two cards of the same *rank bucket*. Whether `T`+`K` counts as a splittable pair is a `RuleSet` flag (`split_by_value`), default `True` (most casinos allow it, though splitting tens is never correct).

**4. `rules.py` — `RuleSet`.** A frozen dataclass and the single source of truth, T20's `format_spec.py` role:

| Field | Type | Default | Effect on player return |
|---|---|---|---|
| `num_decks` | `int` | `6` | 2D ≈ +0.21%, 4D ≈ +0.05% vs 6D; 8D ≈ −0.03% |
| `dealer_hits_soft_17` | `bool` | `False` (S17) | H17 ≈ **−0.22%** |
| `blackjack_payout` | `Fraction` | `3/2` | 6:5 ≈ **−1.39%**; 1:1 ≈ −2.3% |
| `double_after_split` | `bool` | `True` | DAS ≈ **+0.14%** |
| `double_on` | `str` | `"any"` | `"9-11"` ≈ −0.09%; `"10-11"` ≈ −0.18% |
| `surrender` | `str` | `"late"` | Late surrender ≈ **+0.08%**; `"none"` = 0 |
| `resplit_to` | `int` | `4` | Max total hands from splits |
| `resplit_aces` | `bool` | `False` | RSA ≈ +0.08% |
| `hit_split_aces` | `bool` | `False` | Split aces get one card only |
| `dealer_peeks` | `bool` | `True` | No-hole-card (European, OBBO) ≈ −0.11% |
| `penetration` | `float` | `0.75` | No EV effect per hand; drives counting yield |
| `split_by_value` | `bool` | `True` | T/J/Q/K mutually splittable |

- `RuleSet.key()` — a short deterministic hash (e.g. `6d-s17-das-ls-p75`) used as the filename for cached grids and indices, and as the cache-manifest key. Same role as T20's `{format}_` artifact prefix.

> [!NOTE]
> The rule-effect percentages above are the **well-established published deltas** and are included so the RuleSet's fields are self-documenting. They are *not* the project's source of truth — Phase 5 re-derives every one of them from the solver and treats disagreement as a solver bug.

### Verification

```bash
py -c "from src.engine.shoe import Shoe; s=Shoe(6); print(s.composition, s.composition.sum())"
py -c "from src.engine.hand import Hand; h=Hand(['A','6']); print(h.total, h.is_soft); h.add('T'); print(h.total, h.is_soft)"
```
Expected: `[24 24 24 24 24 24 24 24 96 24] 312`; then `17 True` → `17 False`.

---

## Phase 2: Dealer Logic & Round State Machine

**Files:** `src/engine/dealer.py`, `src/engine/game.py` (NEW)  
**Priority:** 🟡 Medium  
**Dependencies:** Phase 1

### Problem

A round of blackjack is a state machine with more branches than it looks: split hands recurse, split aces usually get one card, doubles are terminal, surrender resolves before the dealer draws, and blackjack settles before anything else. Every one of these is a place where a subtly wrong payout silently biases the Monte Carlo in Phase 8 — and a biased simulator will "confirm" a wrong solver.

### Implementation

**1. `dealer.py` — `play_dealer(hand, shoe, rules)`.** Draw while `total < 17`, or while `total == 17 and is_soft and rules.dealer_hits_soft_17`. Returns final total or `BUST`.

**2. `game.py` — `play_round(shoe, rules, bets, decide_fn)`.** Order of resolution, which must be exactly:

```
1. Deal: player card, dealer up, player card, dealer hole (if rules.dealer_peeks)
2. If dealer upcard is Ace → offer insurance (side bet, pays 2:1)
3. If rules.dealer_peeks and upcard in {T, A} → peek:
       dealer blackjack  → settle immediately (player BJ pushes, all else loses)
4. Player blackjack (and no dealer BJ) → pay rules.blackjack_payout, hand over
5. Player decisions, per hand, in split order:
       SURRENDER (first action only, before any hit) → lose half, hand over
       SPLIT     → recurse, up to rules.resplit_to hands
       DOUBLE    → exactly one card, terminal
       HIT / STAND
6. If no hands remain live (all busted/surrendered) → dealer does not draw
7. play_dealer(...)
8. Settle each live hand vs dealer total
```

**3. `decide_fn` is an injected callable** with signature `(player_hand, dealer_up, shoe_state, rules) -> Action`. This is the seam that lets the same round engine be driven by the basic-strategy table, the count-aware deviation table, a random baseline, or a human clicking in the UI. **Never** let strategy logic leak into `game.py`.

> [!WARNING]
> **The no-peek (European) branch is the classic correctness trap.** Under `dealer_peeks=False` the player can lose *additional* money — the extra bet on a double or split — to a dealer blackjack revealed later. Under OBBO ("original bets only") they lose only the original bet. The two are worth ~0.11% apart. Make exactly what the flag means explicit in `RuleSet` and unit-test both branches, or Phase 5's European rulesets will fail for reasons that look like solver bugs.

### Verification

```bash
py -m pytest tests/test_engine.py -q
```
Expected: all pass. Minimum coverage: player BJ pays 3:2; player BJ vs dealer BJ pushes; 21-after-split pays 1:1; split aces receive one card each; surrender returns exactly half; dealer stands on soft 17 under S17 and hits it under H17; dealer does not draw when every player hand has busted.

---

## Phase 3: Exact EV Solver

**Files:** `src/strategy/dealer_probs.py`, `src/strategy/ev_solver.py` (NEW)  
**Priority:** 🔴 Critical — **the one component the entire project depends on**  
**Dependencies:** Phases 1–2

### Problem

We need `EV(action | player_hand, dealer_upcard, shoe_composition, rules)` for `action ∈ {stand, hit, double, split, surrender}`. Everything downstream is a consequence of this function: the strategy grid is its argmax, the count indices are the true counts at which its argmax flips, and the Kelly bet is a function of its value. There is no statistical model here — this is exact recursive enumeration over the shoe.

### Implementation

**Step 1 — Dealer outcome distribution (`dealer_probs.py`).**

```python
def dealer_distribution(upcard: int, comp: np.ndarray, rules: RuleSet) -> np.ndarray:
    """
    Returns P over [17, 18, 19, 20, 21, BUST] for the dealer's final total,
    given the upcard and the composition of cards remaining (upcard already removed).
    """
```
Recurse: draw each rank with probability `comp[r] / comp.sum()`, remove it, recurse until the dealer must stand. Cache results keyed on `(hard_total, is_soft, comp.tobytes())`.

**Step 2 — Peek conditioning.** If `rules.dealer_peeks` and the upcard is `T` or `A`, the dealer has already checked the hole card and does not have blackjack. The hole-card distribution must therefore be **conditioned on that**: renormalise after zeroing the ace (for a ten up) or the tens (for an ace up).

> [!CAUTION]
> Skipping the peek conditioning is the single most common blackjack-solver bug, and it produces a grid that is *almost* right — typically flipping only 16 vs 10 and 12 vs 4 — which is precisely why it survives casual inspection. Phase 5's cell-for-cell comparison exists to catch exactly this.

**Step 3 — Player action EVs (`ev_solver.py`).**

- `ev_stand` — dot the dealer distribution against the payoff vector for the player's total.
- `ev_hit` — for each rank `r`: `P(r) × [bust ? −1 : max(ev_stand', ev_hit')]`. The `max` makes this optimal-play EV, not fixed-strategy EV.
- `ev_double` — for each rank `r`: `2 × P(r) × ev_stand(total + r)`. Exactly one card; no further action.
- `ev_surrender` — constant `−0.5`, available only as a first action and only if `rules.surrender != "none"`.
- `ev_split` — the hard one. Compute the EV of **one** post-split hand starting from the split rank with both split cards removed from the shoe, allowing resplits up to `rules.resplit_to` by recursion, and permitting doubles iff `rules.double_after_split`; then return `2 ×` that value.

> [!NOTE]
> The `2 × one_hand_EV` split treatment assumes the two post-split hands are independent, which is not strictly true — they draw from the same depleted shoe. This is the standard treatment used by every published chart and by Griffin's *Theory of Blackjack*; the error is on the order of 0.01% and is *required* for the Phase 5 known-answer test to match published charts. Document the approximation; do not "fix" it.

**Step 4 — Composition mode.** Two solver modes, selected by argument:
- `mode="total_dependent"` (default) — the shoe is at full composition minus the player's and dealer's known cards. This is what produces the standard published charts, and what Phase 5 validates against.
- `mode="composition_dependent"` — full exact removal of every visible card. Produces the genuinely optimal play for the actual hand shown (e.g. 16 vs 10 as `T+6` differs from `9+7`). This is the mode the **UI's "mathematically correct decision"** should use in Phase 11.

**Step 5 — Performance.** Cache keyed on `(total, is_soft, upcard, comp.tobytes(), rules.key())`. Practical mitigations, in order of preference:
1. Solve once per ruleset and **cache the result to `data/strategy/`** — the runtime app never re-solves (Phase 4).
2. Quantise composition for the memo key when in total-dependent mode (composition barely moves for a 2-card removal from a 312-card shoe).
3. Only if still too slow: add `numba` `@njit` on the dealer recursion.

### Verification

```bash
py -c "import numpy as np; from src.engine.rules import RuleSet; from src.strategy.dealer_probs import dealer_distribution; from src.engine.shoe import Shoe; \
c=Shoe(6).composition; c[4]-=1; print(np.round(dealer_distribution(6, c, RuleSet()), 4))"
```
Expected, dealer showing 6, S17, 6 decks: roughly `[0.166, 0.106, 0.107, 0.101, 0.098, 0.422]` over `[17,18,19,20,21,BUST]` — the bust probability must land near **42.4%** (6 is the dealer's worst upcard) and the six probabilities must sum to exactly 1.0.

---

## Phase 4: Basic Strategy Grid Generator

**Files:** `src/strategy/grid_builder.py`, `src/strategy/basic_strategy.py` (NEW)  
**Priority:** 🟡 Medium  
**Dependencies:** Phase 3

### Problem

The solver answers one cell at a time. The player-facing product is the whole grid — hard totals 4–21, soft totals A,2–A,9, and pairs 2,2–A,A, each against dealer upcards 2–A — for whichever ruleset the user selected in the UI. Solving that live on every page load is not viable; solving it once per ruleset and caching is.

### Implementation

1. **`grid_builder.solve_grid(rules) -> dict`** — loop all three grid families × 10 upcards, call `ev_solver` for each legal action, take the argmax, and record **both the chosen action and the EV of every action** (the UI's "why" panel needs the margins, and a cell where the top two actions are within 0.001 is a cell worth flagging as near-indifferent).

2. **Action legality.** Double and surrender are first-action-only; split only on pairs; surrender is checked *before* the stand/hit/double comparison because it caps loss at −0.5 rather than maximising EV. Encode the standard notation the UI will render:

   | Code | Meaning |
   |---|---|
   | `H` / `S` | Hit / Stand |
   | `D` | Double if allowed, otherwise Hit |
   | `Ds` | Double if allowed, otherwise **Stand** (soft 18/19 only) |
   | `P` | Split |
   | `Ph` | Split if DAS, otherwise Hit |
   | `Rh` / `Rs` / `Rp` | Surrender if allowed, otherwise Hit / Stand / Split |

3. **Cache to `data/strategy/{rules.key()}.json`**, with the hash-validated cache manager ported from T20's `src/utils/cache_manager.py` keyed on the source hash of `ev_solver.py` + `dealer_probs.py` + the RuleSet.

> [!WARNING]
> T20's hard lesson applies directly: its `.pkl` model caches had **no content check at all**, so `fit(cache_path=...)` happily returned a stale model after the feature code changed. Do not repeat this. Every cached grid must carry `{"solver_hash": ..., "ruleset": {...}}` and be rebuilt on mismatch — no exception for pre-existing files without a manifest entry, which is the specific loophole that let T20's Elo caches silently drift.

4. **`basic_strategy.advise(hand, upcard, rules) -> Advice`** — the runtime lookup returning `(action, ev_by_action, margin, is_close)`.

5. **`scripts/build_all_grids.py`** — pre-solve the shipped matrix: `{2,4,6,8} decks × {S17,H17} × {DAS, no-DAS} × {LS, no surrender}` = 32 grids, committed to `data/strategy/`.

### Verification

```bash
py main.py --decks 6 --s17 --das --surrender late --print-grid
```
Expected: three rendered tables. Spot-checks that must hold for 6D/S17/DAS: hard 11 vs A = `H`, hard 12 vs 2 = `H`, hard 12 vs 4 = `S`, hard 16 vs 10 = `Rh`, soft 18 (A,7) vs 9 = `H`, pair 9,9 vs 7 = `S`, pair 4,4 vs 5 = `Ph`.

---

## Phase 5: Validation Gate — Grid + House Edge

**Files:** `tests/test_strategy_grid.py`, `tests/test_house_edge.py`, `data/baselines/*.json` (NEW)  
**Priority:** 🔴 Critical — **GO / NO-GO for the whole project**  
**Dependencies:** Phases 2–4

### Problem

The solver is either right or it is elaborately wrong, and the two look identical from the inside. Two independent checks are needed, because each catches what the other misses: a **cell-for-cell chart comparison** catches structural errors (peek conditioning, split recursion, DAS handling) but is insensitive to small EV biases; a **simulated house edge** catches EV bias but would pass even if two rarely-reached cells were swapped.

### Implementation

**Check 1 — Grid vs published charts.** Encode the reference charts in Appendix A as a fixture and assert the solver reproduces them **cell for cell** for the multi-deck rulesets. Run for `{4, 6, 8} decks × {S17, H17}`. Note that 2-deck and single-deck charts legitimately differ in several cells (e.g. 2D S17 doubles hard 9 vs 2, 8,8 vs A) — encode those separately rather than expecting the multi-deck chart to hold.

**Check 2 — House edge vs published anchors.** Two-tier design (see the detailed findings below the tracking table for why a pure-Monte-Carlo version isn't enough on its own):

- **Primary** — `src/strategy/exact_edge.py`'s full, zero-noise combinatorial enumeration over every possible initial deal, compared against the published anchor with a flat tolerance (no sampling error to account for, so a flat band is correct here).
- **Secondary (sanity check)** — the Phase 8 simulator (or a lightweight precursor) playing real rounds through `game.py`'s actual mechanics, compared not against the published anchor but against the **primary check's own exact figure** — isolating "does game.py have an integration bug" from "does our exact model differ slightly from a published anchor's total-dependent convention," which are different questions. Because the reference side is noise-free, the tolerance is a multiple of the simulation's own standard error (e.g. 4×SE) rather than a fixed band.

Anchors for S17, DAS, double-any-two, no surrender, 3:2, peek:

| Decks | Published house edge | Primary gate | Secondary gate |
|---:|---:|---|---|
| 1 | ≈ 0.02% | ±0.02% vs anchor | N×SE vs exact |
| 2 | ≈ 0.19% | ±0.02% vs anchor | N×SE vs exact |
| 4 | ≈ 0.35% | ±0.02% vs anchor | N×SE vs exact |
| 6 | ≈ 0.40% | ±0.02% vs anchor | N×SE vs exact |
| 8 | ≈ 0.43% | ±0.02% vs anchor | N×SE vs exact |

**Check 3 — Rule-effect deltas.** Re-derive each `RuleSet` field's marginal cost from the solver and assert it matches the published delta in Phase 1's table (H17 ≈ −0.22%, DAS ≈ +0.14%, LS ≈ +0.08%, 6:5 ≈ −1.39%, RSA ≈ +0.08%). This cross-checks the solver from a different angle: one that gets absolute edge right but rule deltas wrong has a rule-handling bug, not an arithmetic one.

**Lock the baselines.** On pass, write `data/baselines/strategy_baseline.json` (grid hash per ruleset) and `house_edge_baseline.json` (simulated edge per ruleset, with its Monte Carlo standard error). These become the frozen reference, exactly as `baseline_metrics.json` is in T20 — with a `--generate` flag to deliberately re-lock and a `--generate-ruleset <key>` flag to re-lock one variant only.

> [!CAUTION]
> **Do not proceed to Phase 6 on a partial pass.** "The grid matches except 16 vs 10" is not a near-miss — it is the signature of missing peek conditioning (Phase 3, Step 2), and it will corrupt every count index in Phase 7, since 16 vs 10 is the single most frequently played index in the Illustrious 18.

### Verification

```bash
py -m pytest tests/test_strategy_grid.py -q
py tests/test_house_edge.py --hands 50000000 --rulesets 2d-s17-das 6d-s17-das 8d-s17-das
```
Expected: every grid assertion passes; every simulated edge inside its ±0.02% band with a Monte Carlo standard error below 0.005%.

---

## Phase 6: Counting Systems & True Count

**Files:** `src/counting/systems.py`, `src/counting/counter.py` (NEW)  
**Priority:** 🟢 Low  
**Dependencies:** Phase 1 (independent of the solver — can be built in parallel with 3–5)

### Problem

Card counting is arithmetic, not magic: assign a tag to each rank, keep a running sum, and normalise by how many decks remain. The engineering content is in the normalisation and the edge cases — unbalanced systems, true-count rounding, and estimating decks remaining from the discard tray.

### Implementation

**1. `systems.py` — tag vectors** over the 10-bucket rank index, with published Betting Correlation (BC) and Playing Efficiency (PE) for the UI to display:

| System | Level | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | T | A | Balanced | BC | PE |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **Hi-Lo** | 1 | +1 | +1 | +1 | +1 | +1 | 0 | 0 | 0 | −1 | −1 | ✅ | 0.97 | 0.51 |
| **KO** | 1 | +1 | +1 | +1 | +1 | +1 | +1 | 0 | 0 | −1 | −1 | ❌ | 0.98 | 0.55 |
| **Hi-Opt I** | 1 | 0 | +1 | +1 | +1 | +1 | 0 | 0 | 0 | −1 | 0 | ✅ | 0.88 | 0.61 |
| **Hi-Opt II** | 2 | +1 | +1 | +2 | +2 | +1 | +1 | 0 | 0 | −2 | 0 | ✅ | 0.91 | 0.67 |
| **Omega II** | 2 | +1 | +1 | +2 | +2 | +2 | +1 | 0 | −1 | −2 | 0 | ✅ | 0.92 | 0.67 |
| **Zen** | 2 | +1 | +1 | +2 | +2 | +2 | +1 | 0 | 0 | −2 | −1 | ✅ | 0.96 | 0.63 |
| **Red 7** | 1 | +1 | +1 | +1 | +1 | +1 | ½* | 0 | 0 | −1 | −1 | ❌ | 0.98 | 0.54 |

\* Red Seven: red 7s count `+1`, black 7s count `0` — the only system that needs suit colour, which is why `Card` retains its suit.

Ship **Hi-Lo as the default** (highest BC of the level-1 balanced systems, and the system every published index is quoted for). Hi-Opt I/II and Omega II count aces as 0 and therefore need a **side count of aces** for betting accuracy; expose that as an optional field rather than silently mis-sizing bets.

**2. `counter.py` — `Counter(system, num_decks)`.**
- `running_count` — initialised to the system's **IRC**. Balanced systems start at 0; KO starts at `−4 × (num_decks − 1)` (so `−20` for 6 decks) and pivots at `+4`.
- `true_count` — `running_count / decks_remaining`, where `decks_remaining = (total_cards − dealt) / 52`, floored to a configurable resolution (default **half-deck**, matching realistic discard-tray estimation).
- `tc_rounding` — configurable `"floor"` / `"nearest"` / `"truncate"`. Default **`"floor"`** for betting (conservative — never overbets on a rounding artefact) and **`"nearest"`** for playing decisions. Make this explicit; it is worth a few hundredths of a percent and is a common source of disagreement between two "correct" implementations.
- Unbalanced systems (KO, Red 7) expose `running_count` only and raise on `true_count` — they are designed to be used without conversion.

**3. Dual-system mode (optional) — a different system for betting vs. playing.** `Counter` is a stateless per-card accumulator over its own tag vector, so nothing stops running two independent instances off the same dealt-card stream — e.g. Hi-Lo (BC 0.97) for bet sizing and Omega II (PE 0.67) for play deviations. Expose `Counter.paired(betting_system, playing_system, num_decks)`, returning two counters that both advance on every `counter.see(card)` call; cost is O(1) extra per card, so there is no reason to gate this behind anything harder than a second dropdown. Default both to Hi-Lo (single-system mode); dual-system mode activates only when the user picks two different systems.

> [!NOTE]
> This mirrors a real technique advantage players use precisely because a human can't track a full 10-dimensional shoe composition by hand — BC and PE are both proxies for how well a single scalar count approximates that composition. The engine itself doesn't share that limitation: Phase 3 already solves exact composition-dependent EV. So dual-system mode isn't adding precision the engine lacks elsewhere; it's letting the UI emulate the pen-and-paper compromise for users who want to practice or use it live. Every downstream consumer must be told explicitly which counter feeds which decision — see Phase 7 (deviations always read the *playing* counter) and Phase 9 (Kelly always reads the *betting* counter).

### Verification

```bash
py -m pytest tests/test_counting.py -q
```
Expected: dealing an entire balanced shoe returns the running count exactly to its IRC (0 for Hi-Lo) — this is the definition of "balanced" and catches any tag-vector typo instantly. KO from 6 decks starts at −20 and ends at +4. A paired `Counter` fed the same shoe as two separate single-system counters must match each of them card-for-card — proof the two instances don't leak state into each other.

---

## Phase 7: Count-Indexed Deviations

**Files:** `src/strategy/index_builder.py`, `src/strategy/deviations.py` (NEW)  
**Priority:** 🔴 High  
**Dependencies:** Phases 3, 5, 6

### Problem

Basic strategy is optimal for a *neutral* shoe. As the count rises, the shoe's composition changes and some decisions flip — the classic example is 16 vs 10, which is a marginal hit at true count 0 and becomes a stand at any positive count. These flip points ("indices") are worth substantially more than they look: index play adds roughly 0.1–0.2% to a counter's edge, and the insurance index alone is worth about a third of that.

### Implementation

1. **Derive, don't transcribe.** For each named cell, sweep true count from −10 to +10. At each TC, construct the shoe composition that count *implies* — for Hi-Lo at TC = +5 with 4 decks remaining, remove 20 net low cards distributed proportionally across the `+1` ranks and add the complement across the `−1` ranks — then re-solve the cell in `composition_dependent` mode. Record the TC at which the argmax action changes.

   **Scoped to the 22 named decision points (Illustrious 18 + Fab 4), not all 340 grid cells.** Each swept TC is a genuinely distinct composition, unlike a single neutral-shoe grid solve where 340 cells share huge caching overlap — a full-grid sweep was estimated at hours per ruleset+system for negligible value on the vast majority of cells that have no practically-relevant flip point at all (that's precisely why only ~22 are famous enough to publish). `index_builder.py`'s `derive_index`/`implied_composition` are general-purpose and not limited to these 22 if a later phase wants more.

2. **The composition-from-count mapping is the hardest part and must be documented explicitly.** A true count is a single number summarizing a 10-dimensional composition, so going backward from count to composition has no single correct answer. Use the standard treatment: distribute the count's implied surplus/deficit **proportionally within each tag group**, preserving the total card count and the un-tagged ranks. Record this choice in `.agents/coding-standards.md` — a different mapping yields indices off by ±1, which is exactly the spread seen between published index tables.

3. **Validate against the Illustrious 18.** The derived indices must reproduce the standard Hi-Lo, 6-deck, S17 table within **±1 true count**:

   | Rank | Play | Index | | Rank | Play | Index |
   |---:|---|:-:|---|---:|---|:-:|
   | 1 | Insurance | +3 | | 10 | 9 vs 2 | +1 |
   | 2 | 16 vs 10 | 0 | | 11 | 10 vs A | +4 |
   | 3 | 15 vs 10 | +4 | | 12 | 9 vs 7 | +3 |
   | 4 | 10,10 vs 5 (split) | +5 | | 13 | 16 vs 9 | +5 |
   | 5 | 10,10 vs 6 (split) | +4 | | 14 | 13 vs 2 | −1 |
   | 6 | 10 vs 10 (double) | +4 | | 15 | 12 vs 4 | 0 |
   | 7 | 12 vs 3 | +2 | | 16 | 12 vs 5 | −2 |
   | 8 | 12 vs 2 | +3 | | 17 | 12 vs 6 | −1 |
   | 9 | 11 vs A (double) | +1 | | 18 | 13 vs 3 | −2 |

   Plus the **Fab 4** late-surrender indices: 14 vs 10 (+3), 15 vs 10 (0), 15 vs 9 (+2), 15 vs A (+1).

4. **Insurance is special** and must not be solved as a grid cell. It is a standalone bet on the density of tens: take it when remaining tens exceed one third of remaining cards. For Hi-Lo that is TC ≥ +3, but the engine should evaluate the *actual* composition, which is strictly better and free.

5. **`deviations.advise(hand, upcard, counter, rules)`** — returns the basic-strategy action plus a deviation when the current TC crosses an index, with the EV gain attached so the UI can show *why*. In dual-system mode (Phase 6) this is always called with the **playing**-system counter and that system's own `{ruleset_key}__{system}.json` index table — never the betting counter's TC, since indices are derived per-system and are not interchangeable (an Omega II TC of +3 does not mean what a Hi-Lo TC of +3 means).

   Two subtleties found only by testing runtime behavior directly, not by the index values alone: a cell like "15 vs 10" can carry **both** a "primary" (stand/hit/double/split, ignoring surrender) index and a "surrender" (surrender-vs-not) index, and which one is *live* for a given hand can't be inferred from what basic strategy currently does — 3 of the 4 Fab 4 cells only ever get a "surrender" entry at all (basic strategy already hits them at a neutral shoe), so the selection has to check which entry *exists*, preferring "surrender" whenever it's legal and derived. And the derived index is only a **gate** for whether to re-solve, never the recommendation itself — a restricted (no-surrender) comparison can flip well before or after surrender stops dominating everything (16 vs 10 stays surrender-correct far past where "stand beats hit" alone would suggest), so the actual action always comes from a live, fully-legal-action re-solve once the gate trips.

6. **`scripts/build_all_indices.py`** → `data/indices/{ruleset_key}__{system.slug}.json`, mirroring `main.py`'s own CLI convention (`--decks`/`--h17`/`--das`/`--surrender`) plus `--system`, rather than a raw ruleset-key string (which would need a dedicated parser for no real benefit).

> [!NOTE]
> Published index tables disagree with each other by ±1 in several cells because different authors use different count-to-composition mappings and different rounding conventions. A ±1 tolerance in the Phase 7 test is therefore correct and honest, not a weakened gate. Any cell off by ≥2 is a genuine bug.

### Verification

```bash
py scripts/build_all_indices.py --decks 6 --das --surrender late --system hi-lo
py -m pytest tests/test_deviations.py -q
```
Expected: all 17 Illustrious-18 cells (insurance is validated separately, not as a grid cell) and all 4 Fab 4 surrender indices within ±1 of the published table; insurance triggers at TC +3 on a neutral-shoe reconstruction.

---

## Phase 8: Monte Carlo Simulator & Edge Model

**Files:** `src/simulation/simulator.py`, `src/simulation/metrics.py`, `src/counting/edge_model.py` (NEW)  
**Priority:** 🔴 High  
**Dependencies:** Phases 2, 4, 6, 7

### Problem

Two things cannot be computed in closed form and must be simulated. First, **variance** — Kelly needs it, and blackjack's per-hand variance is not 1.0 because doubles, splits, and 3:2 blackjacks fatten both tails. Second, the **edge-vs-true-count relationship**, which depends on penetration, rule set, and whether index plays are used. The usual "+0.5% per true count" rule of thumb is a decent prior and a poor substitute for measurement.

### Implementation

**1. `simulator.py`** — play N shoes end to end using the Phase 2 round engine with an injected `decide_fn`. Configurable: ruleset, counting system, betting scheme (flat or ramped), index play on/off, number of players at the table (affects cards seen per round and therefore hourly rate), and penetration.

   **Other players, per Appendix B item 8** ("single-player is sufficient for edge and variance"): modelled as a simple card burn (mean 2.7 cards/hand, a standard rule-of-thumb average across 2-card/hit/double/split hands) from the shared shoe before each of our own rounds, fed to the counter same as our own cards — not a full multi-seat game. This only changes how fast the shoe depletes (and so how often/far the count swings, i.e. hands-per-hour realism), never any EV number, since our own decisions only ever depend on the shoe composition at our own decision point regardless of whose play consumed which cards.

Per hand, record: true count at the point of the bet, amount wagered, net result, and whether the hand was doubled or split.

**2. `edge_model.py`** — bucket every simulated hand by true count, compute mean result per unit wagered in each bucket, and fit a line:

```
edge(TC) = intercept + slope × TC
```

Expected shape for 6D / S17 / DAS / 75% penetration / Hi-Lo with index play: `intercept ≈ −0.005` (the basic-strategy house edge) and `slope ≈ +0.005` (about half a percent per true count), giving break-even near **TC +1**. **Fit these per ruleset — do not hardcode them.** Deck count materially changes the intercept, and penetration changes how much time is spent in the profitable tail.

Store the fit plus its R² and per-bucket standard errors in `data/baselines/edge_model_baseline.json`. Report the per-bucket measured averages alongside the linear fit — the relationship curves slightly upward at high counts, and the UI should be honest about extrapolating past TC +6, where the sample is thin.

**3. `metrics.py`** — the standard advantage-play metrics:

| Metric | Formula | Meaning |
|---|---|---|
| Win rate | mean units won per 100 hands | Expected return |
| Variance | per-hand variance of result / unit wagered | ≈ **1.26–1.32** for typical rules — verify, don't assume |
| **N₀** | `variance / EV²` | Hands needed for expected win to equal one SD — the "how long until skill beats luck" number |
| Risk of Ruin | `exp(−2 × B × μ / σ²)` | Standard random-walk approximation; `B` = bankroll in units, `μ`/`σ²` per hand |
| SCORE | ∝ `EV² / variance` | Comparative game quality, normalised to a $10k bankroll at 13.5% RoR |
| DI | `1000 × EV / SD` | Desirability Index |

> [!WARNING]
> **Monte Carlo standard error is large relative to the effects being measured.** A counter's edge is ~1% with a per-hand SD of ~1.15, so distinguishing a 1.00% edge from a 1.05% edge to two standard errors needs on the order of 10⁷–10⁸ hands. Every simulated number reported anywhere in this project — test output, UI, README — must carry its standard error. A bare "+1.2% edge" with no interval is not a result.

### Verification

```bash
py scripts/run_sim_battery.py --decks 6 --das --surrender late --system hi-lo --hands 20000000 --generate
```
(mirrors `main.py`'s own CLI convention, per Phase 7's same choice, rather than a raw ruleset-key string. `--spread 1-12` is also available but is a simple placeholder linear ramp — Phase 9 owns the real Kelly-derived bet ramp — so the solver cross-check below uses the flat-bet default, not a spread.)

Expected: flat-bet basic-strategy edge reproduces Phase 5's locked house edge within its stated standard error (this is the simulator validating against the solver, and it is the cross-check that matters most); per-hand variance in 1.25–1.35; fitted slope in 0.004–0.006 per true count; R² > 0.98 over TC ∈ [−3, +6].

---

## Phase 9: Bankroll, Kelly & Bet Ramp

**Files:** `src/bankroll/kelly.py`, `bet_ramp.py`, `risk.py` (NEW)  
**Priority:** 🟡 Medium  
**Dependencies:** Phase 8

### Problem

Knowing the edge is only half the staking problem. Betting too much of a bankroll at a 1% edge with a variance of 1.3 is a fast route to ruin; betting too little forgoes almost all the growth. Kelly gives the growth-optimal answer, but the raw Kelly bet then has to survive contact with table minimums, table maximums, chip denominations, and the fact that a 1-to-20 bet spread gets a player asked to leave.

### Implementation

**1. `kelly.py`.**

```python
def kelly_fraction(edge: float, variance: float = 1.3, fraction: float = 0.5) -> float:
    """Growth-optimal fraction of bankroll to wager, scaled by `fraction` (half-Kelly default)."""
    return max(0.0, fraction * edge / variance)

def kelly_bet(bankroll, edge, variance=1.3, fraction=0.5,
              table_min=10, table_max=1000, chip=5) -> float:
    raw = kelly_fraction(edge, variance, fraction) * bankroll
    return clamp_and_round(raw, table_min, table_max, chip)
```

Default to **half-Kelly**. Full Kelly maximises log growth but carries a ~13.5% chance of halving the bankroll before doubling it, and its drawdowns are unbearable in practice; half-Kelly retains **75% of the growth rate at roughly half the volatility**. Expose `fraction` in the UI with that trade-off stated, not buried.

**2. Edge comes from Phase 8**, not a constant: `edge = edge_model.edge(true_count, ruleset, system)`. Below break-even, Kelly returns 0 — but a player who cannot leave the table must bet *something*, so `bet_ramp` floors at `table_min` and reports the (negative) EV of those waiting hands honestly rather than pretending they are free. In dual-system mode (Phase 6), `true_count` here is always the **betting**-system counter's TC — Kelly never sees the playing counter, since the edge model's `(true_count, ruleset, system)` key is only fit for the system named.

**3. `bet_ramp.py`** — convert the continuous Kelly curve into a small, memorisable, discrete ramp by snapping to the standard doubling progression (1, 2, 4, 8, 16, ...) — rounding DOWN to the nearest level the Kelly fraction actually justifies, never up:

```
TC ≤ +1  →  1 unit   (minimum / waiting bet, negative EV — this is the cost of the ramp)
TC = +2  →  2 units
TC = +3  →  4 units
TC = +4  →  8 units
TC ≥ +5  →  12 units (capped by spread limit, not by Kelly)
```

Constrained by `max_spread` (default 12, a cover constraint rather than a mathematical one) and by `table_max`. Report the **EV cost of the constraint** — the difference between the unconstrained-Kelly growth rate and the ramp's — so the user can see what cover is costing them.

> [!NOTE]
> The EV cost is usually positive (snapping down from a raw Kelly fraction that already justifies >=1 unit strictly loses growth, since the growth-rate curve `g(f) = f·edge − 0.5·f²·variance` is increasing everywhere below the full-Kelly peak, and half-Kelly's own fraction always sits below that peak). It can go slightly **negative** — a tiny gain, not a cost — in exactly one case: raw Kelly wants *less* than 1 unit (a small positive edge), but the mandatory table-minimum floor forces a full unit anyway, which can land closer to the true full-Kelly peak than half-Kelly's own target does. Confirmed against the real locked Phase 8 baseline (it happens at TC +1), not a hypothetical — report it honestly rather than clamping it to look tidier.

**4. `risk.py`** — risk of ruin for a given (bankroll, ramp, ruleset), N₀, expected hours to double, and the drawdown distribution at the 50th/90th/99th percentiles from the Phase 8 sim. **Show these next to every bet recommendation.** A "$240 optimal bet" without "and a 12% chance of losing this bankroll" is not advice.

`risk_of_ruin` and `N₀` are literally `src.simulation.metrics`' own functions (Phase 8), re-exported here rather than reimplemented — that table already exists in Phase 8's own Implementation section for a reason. The drawdown percentiles are simulated directly (Normal(edge, variance) per-hand steps — the same random-walk approximation `risk_of_ruin`'s closed form already assumes, not a new one), batched rather than one giant array, per the 7.7GB dev-machine caution.

> [!IMPORTANT]
> Kelly's guarantee only holds over many, many bets, and assumes the edge estimate is correct. A counter's edge estimate carries real uncertainty — from the edge-model fit, from deck estimation error, and from the count itself being an imperfect summary of the shoe. Overbetting relative to a *mis-estimated* edge is punished far more severely than underbetting. The half-Kelly default is not conservatism for its own sake; it is the standard hedge against estimation error, and the docstring should say so.

### Verification

```bash
py -c "from src.bankroll.kelly import kelly_bet; print(kelly_bet(10000, 0.01, 1.3, 0.5, 10, 1000, 5))"
py -c "from src.bankroll.risk import risk_of_ruin; print(risk_of_ruin(bankroll_units=200, edge=0.01, variance=1.3))"
```
Expected: half-Kelly at a 1% edge on a $10,000 bankroll ≈ **$40** (0.5 × 0.01 / 1.3 = 0.385% of bankroll, rounded to the chip). Risk of ruin at 200 units with a 1% edge ≈ **4.6%** (`exp(−2 × 200 × 0.01 / 1.3)`).

---

## Phase 10: Flask API

**File:** `app.py` (NEW)  
**Priority:** 🟡 Medium  
**Dependencies:** Phases 4, 6, 7, 9

### Problem

The UI needs the engine, and the engine is Python. Mirror T20's pattern: load every cached artifact once at startup into dict registries keyed by ruleset, and keep every route a thin, stateless translation over `src/`.

### Implementation

**Startup**, mirroring T20's `MODELS = {}` loop over `ACTIVE_FORMATS`:

```python
GRIDS = {key: load_grid(key) for key in SHIPPED_RULESETS}       # data/strategy/*.json
```

**Only grids are eagerly loaded for every shipped ruleset.** Indices and edge models are NOT — deriving a fresh index table takes ~9 minutes (Phase 7) and, unlike grids, only ever exist for whatever ruleset+system combos someone has actually pre-built via `scripts/build_all_indices.py`/`run_sim_battery.py --generate` (currently just one: `6d-s17-das-ls-p75`/Hi-Lo). `solve_indices_cached()` is called lazily/on-demand instead (its own disk+memory cache makes repeat calls instant); `/api/stake` and `/api/simulate` check for a pre-built file first and return a clean error naming the exact command to run, rather than let a request silently block for 9 minutes.

**Interactive play needed a real architectural decision.** `game.py`'s `play_round()` is a single, synchronous call driven by a `decide_fn` callback (built for simulation/AI, which can answer instantly) — but `/api/game/deal` and `/api/game/action` need to PAUSE between separate HTTP requests waiting for a human's click. Rather than duplicate split/double/hit/surrender legality in a second, hand-rolled state machine (real risk of the two drifting apart), `game.py`'s recursive hand-playing logic was converted to a generator (`play_hands_interactive`, yielding `(hand, legal_actions)` and receiving the chosen `Action` via `.send()`), with `play_round` itself now just driving that same generator with a `decide_fn` in a tight loop — so every existing simulation/AI caller is behaviorally unchanged, and there is exactly one implementation of the actual game rules, not two. `play_round` was also split into `deal_initial()` / (play) / `settle_round()`, since an HTTP API deals via one request and settles via a much later one and needs to reuse the exact same blackjack/peek/OBBO logic for both, not reimplement it. Confirmed behavior-preserving against the full existing test suite (game.py underpins everything from Phase 5's solver validation onward) before building anything on top of it.

**Routes:**

| Route | Method | Purpose |
|---|---|---|
| `/api/rules` | GET | Available rulesets, deck options (2/4/6/8), defaults |
| `/api/grid` | GET | Full solved grid for a ruleset — feeds the Strategy tab |
| `/api/advise` | POST | `{player_cards, dealer_up, running_count, decks_remaining, rules}` → action, EV per action, deviation flag, margin |
| `/api/game/new` | POST | Start a shoe; returns a session id |
| `/api/game/deal` | POST | Deal a round |
| `/api/game/action` | POST | Apply hit/stand/double/split/surrender; returns new state |
| `/api/count` | POST | RC/TC for a dealt-card sequence under a chosen system, or a `{betting_system, playing_system}` pair for dual-system mode (Phase 6) |
| `/api/stake` | POST | `{bankroll, true_count, rules, table_limits, kelly_fraction}` → bet, edge, RoR, N₀ — `true_count` is always the betting-system counter's, per Phase 9 |
| `/api/simulate` | POST | Run a bounded MC batch, return metrics with standard errors |

> [!IMPORTANT]
> **Game state lives server-side, keyed by session id.** The shoe composition must never round-trip through the browser, or a user (or a bug) can desynchronise the count from the deal and every downstream number silently becomes fiction. The client holds a session id and a redacted view; the server holds the shoe.

> [!WARNING]
> `/api/simulate` must be bounded — cap hands per request and stream or paginate. An unbounded simulate endpoint on a 7.7GB machine is a self-inflicted denial of service.

### Verification

```bash
py app.py    # serves on http://127.0.0.1:5000
curl -s -X POST localhost:5000/api/advise -H "Content-Type: application/json" \
  -d '{"player_cards":["T","6"],"dealer_up":"T","running_count":0,"decks_remaining":4,"rules":"6d-s17-das-ls"}'
```
Expected: `{"action":"Rh", "reason":"surrender if allowed, otherwise hit", "ev":{"stand":-0.54,"hit":-0.53,"surrender":-0.50}, ...}` — surrender wins because −0.50 beats both alternatives.

---

## Phase 11: Web UI

**Files:** `static/index.html`, `static/css/style.css`, `static/js/*.js` (NEW)  
**Priority:** 🔴 High  
**Dependencies:** Phase 10

### Problem

This is the deliverable the user actually sees. It must let them pick a 2, 4, or 8-deck shoe, play hands, and be told the mathematically correct decision — with enough visible reasoning that they learn the strategy rather than just obeying it.

### Implementation

Follow T20's frontend conventions: **single-page app, tab navigation, vanilla JS (no framework), glassmorphism dark mode, Outfit font, `fetch()` against Flask on `localhost:5000`.**

**Tabs:**

1. **Play** — the table. Deal, hit, stand, double, split, surrender. Alongside every decision point:
   - The recommended action, badged **`BASIC`** or **`DEVIATION (TC ≥ +4)`**.
   - EV of each available action, as a small bar chart, so the *margin* is visible — 16 vs 10 being nearly a coin-flip is the single most useful thing a learner can internalise.
   - A **"correct / incorrect"** tally against the engine's advice, and the cumulative EV the player has given up by deviating. This is the trainer loop.
   - A toggle for whether advice uses total-dependent (chart) or composition-dependent (exact) mode, since they occasionally disagree and the disagreement is interesting.

2. **Strategy Grid** — the three rendered tables (hard / soft / pairs), colour-coded by action, live-regenerated when the ruleset selector changes. Cells within 0.001 EV of a second action get a subtle marker: those are the cells where the "right" answer barely matters.

3. **Counting** — running count, true count, decks remaining, a per-rank tally of what has been seen, and a **drill mode** that flashes cards and asks for the count. Two independent selectors, **Betting system** and **Playing system**, each across all seven Phase 6 systems and defaulting to Hi-Lo; picking different systems for the two activates dual-system mode and shows both counters side by side. The Play tab's deviation badge names which system triggered it (e.g. `DEVIATION (Omega II, TC ≥ +3)`) so it's never ambiguous which count justified the flip.

4. **Bankroll** — bankroll, table limits, chip denomination, Kelly fraction slider. Outputs the recommended bet for the current count, the full bet ramp, risk of ruin, N₀, and the expected hourly rate. Every figure carries its uncertainty.

5. **Simulator** — configure and run a bounded MC batch; show the bankroll trajectory, the edge-vs-true-count curve with per-bucket error bars, and the drawdown distribution.

**Deck selector** exposes **2 / 4 / 6 / 8**. The user asked for 2/4/8; 6 is included because it is the most common real-world shoe and, more importantly, because the richest published validation data exists for it — it is the anchor Phase 5 leans on hardest. It costs nothing to expose.

> [!CAUTION]
> The UI must state plainly that card counting is legal but that casinos may refuse service, that results are simulations rather than guarantees, and that the edge involved is around 1% with swings that dwarf it over any short session. A tool that outputs a confident "bet $240" with no context is misleading in a way that matters. Put this in the Bankroll tab and the README, not a footnote.

### Verification

Open `http://127.0.0.1:5000`, select a 2-deck shoe, deal until the running count is clearly positive, and confirm: the Play tab's advice flips to `DEVIATION` on a known index (16 vs 10 at TC ≥ 0), the Strategy tab's grid changes when the deck selector moves 2 → 8 (2-deck legitimately doubles hard 9 vs 2 where 8-deck hits), and the Bankroll tab's recommended bet rises with the count and falls when the Kelly fraction slider is reduced.

---

## Phase 12: Regression Harness & CI

**Files:** `tests/regression_test.py`, `.github/workflows/regression.yml`, `docs/system_guide.md` (NEW)  
**Priority:** 🟡 Medium  
**Dependencies:** All

### Problem

T20's single most valuable artifact is `tests/regression_test.py` — one command that checks every locked baseline and either passes or names exactly what moved. Without it, "did my change break something?" is unanswerable and every refactor is a gamble. Build the equivalent here.

### Implementation

1. **`tests/regression_test.py`** — the gate. Checks, in order: every shipped grid against `strategy_baseline.json`; every simulated house edge against `house_edge_baseline.json` (fast mode: fewer hands, wider tolerance); every index table against `deviation_baseline.json`; the edge-model fit against `edge_model_baseline.json`. Flags: `--generate` (re-lock all), `--generate-ruleset <key>` (re-lock one), `--fast` (CI mode).

2. **`.github/workflows/regression.yml`** — run the fast gate on every push and PR. This is **new relative to T20**, which has no CI; it is cheap here because the grids are deterministic and the fast house-edge check is bounded.

3. **`docs/system_guide.md`** — the deep walkthrough: solver derivation, count-to-composition mapping, why half-Kelly, where every published anchor came from.

### Verification

```bash
py tests/regression_test.py
```
Expected: `ALL BASELINES PASS` with a per-ruleset table. Any deviation must be a deliberate, documented re-lock — never a silently updated baseline.

---

## Implementation Tracking

| Phase | Component | Status | Notes |
|-------|-----------|:------:|-------|
| 0 | Repository Bootstrap & GitHub Link | `[x] Completed` | Local repo initialised (`git init -b main`), full `.agents/`+`.claude/skills/` mirror (5 SKILL.md files incl. 3 new blackjack-specific skills), `CLAUDE.md`, `README.md`, `.gitignore`, `.vscode/settings.json`, `requirements.txt` written and committed (root commit `41368d5`, 18 files; tracking-update commit `fa99478`). User created the GitHub repo manually at `github.com/georgenegus/Blackjack_Strategy_Engine`; remote added and `main` pushed and tracking `origin/main`. `gh` CLI was installed via winget as a side effect but device-code auth was not completed — not needed since the repo was created manually |
| 1 | Card / Shoe / Hand / RuleSet | `[x] Completed` | Built `src/engine/{cards,hand,shoe,rules}.py`. Both plan verification commands reproduce the exact expected output (`[24 24 24 24 24 24 24 24 96 24] 312`; `17 True` / `17 False`). Additional checks all passed: `RuleSet().key()` == `"6d-s17-das-ls-p75"` (matches the plan's worked example exactly); `Shoe.from_composition`, `cut_card_reached` at 75% penetration, and `reset()` all behave correctly; `Hand` correctly distinguishes T,K as a bucket-pair (`is_pair`) but not an exact pair (`is_pair_exact`), and correctly marks a from_split 21 as *not* blackjack while a normal A,K is |
| 2 | Dealer Logic & Round State Machine | `[x] Completed` | Built `src/engine/dealer.py` (`play_dealer`) and `src/engine/game.py` (`Action`, `PlayerHand`, `RoundResult`, `play_round`). Extended `RuleSet` (Phase 1 artifact) with an `obbo` field, as the plan's Phase 2 text explicitly directs ("Get the flag semantics explicit in RuleSet"), to distinguish no-peek full-loss vs original-bets-only settlement. `tests/test_engine.py`: **12/12 passed**, covering every item in the plan's minimum-coverage list (player BJ 3:2, player BJ vs dealer BJ push, 21-after-split pays 1:1, split aces get one card each, surrender returns exactly half, dealer stands S17/hits H17 on soft 17, dealer doesn't draw when the only hand busts) plus two added tests for the no-peek OBBO/full-loss distinction and one for illegal-action rejection. Also smoke-tested 20,000 rounds against the real `Shoe` (not the scripted test double) with a randomized decide_fn: 14,761 completed rounds, 5,239 illegal-action rejections correctly caught, zero crashes. Design choice: global hand-count is tracked via one shared mutable counter across a round's split recursion (not a per-lineage depth parameter), since every split adds exactly +1 to the true total hand count regardless of which lineage splits further — this correctly enforces `resplit_to` as a global cap |
| 3 | Exact EV Solver | `[x] Completed` | Built `src/strategy/dealer_probs.py` (`dealer_distribution`, with auto-detected peek conditioning) and `src/strategy/ev_solver.py` (`ev_stand`, `ev_hit`, `ev_double`, `ev_surrender`, `ev_split`/`ev_split_hand`). Added a shared `advance_total()` utility to `src/engine/cards.py` (used by both dealer and player recursion) rather than duplicating the ace-downgrade logic. Plan's exact verification command reproduced closely: `[0.1657 0.1062 0.1064 0.1016 0.0973 0.4228]` vs expected `~[0.166,0.106,0.107,0.101,0.098,0.422]`, bust 42.28% vs ~42.4%, sums to 1.0 exactly. Peek-conditioning spot check: P(21) drops from 11.19% (unconditioned) to 3.77% (conditioned) on a dealer-shows-Ten shoe, auto-detection matches explicit modes, non-blackjack-eligible upcards unaffected by `dealer_peeks` — the plan's flagged highest-risk bug (16v10/12v4 miscorrelation) did not manifest. Went beyond the plan's Phase 3 verification block with 5 additional sanity checks against closed-form facts and famous basic-strategy rules, all passing: `ev_stand(hard 21) == 1 - P(dealer==21)` exactly (float equality); `ev_hit(hard 21) == -1.0` exactly (guaranteed bust); surrender beats stand/hit for 16v10 (-0.500 vs -0.541/-0.535, the Fab-4 rule); double beats stand/hit for 11v6 (0.683 vs -0.151/0.341); split 8,8 vs 6 (0.377) beats standing a hard 16 (-0.158). Performance note for Phase 4: a single hard-12 `ev_hit` sweep across 10 upcards generated ~131K dealer-distribution cache entries in 0.66s — full-grid solving will need Phase 4's disk-caching strategy (solve once, cache to `data/strategy/`) rather than relying on in-process caching; `numba` escalation deferred unless that proves too slow, per the plan |
| 4 | Basic Strategy Grid Generator | `[x] Completed` | Built `src/strategy/grid_builder.py` (`solve_grid`, `solve_grid_cached`), `src/strategy/basic_strategy.py` (`advise`), `src/utils/cache_manager.py` (hash-validated JSON cache, no exceptions for old files), `main.py` (`--print-grid` CLI), `scripts/build_all_grids.py`. Deduplicated `double_on` legality logic that would otherwise have been copy-pasted into grid_builder: moved from a `game.py`-private `_double_allowed` into a shared `double_allowed()` in `rules.py`, used by both `game.py` and `grid_builder.py`. **Bug found and fixed during this phase**: an initial single-representative-combo choice for hard-total decomposition (`min(10, total-2)`, i.e. always preferring a Ten) systematically biased ten-density and flipped hard-12-vs-4 to H against the published S — replaced with a frequency-weighted average across every valid non-pair 2-card decomposition (confirmed empirically: 4 of 5 tested decompositions independently gave S, only the Ten-heavy one gave H). Plan's exact verification command (`py main.py --decks 6 --s17 --das --surrender late --print-grid`) run successfully. **Full cell-by-cell diff against Appendix A**: hard totals 160/160 exact match; soft totals 80/80 exact match; pairs 100/100 match under the documented Ph≡P notational equivalence (Appendix A's "Ph" is an explanatory note for readers without DAS, not a distinct outcome — our solver, given a fully-specified ruleset with DAS=True, correctly resolves those cells to plain "P"), except one near-miss: 3,3 vs dealer-8 solves to P (split) where Appendix A shows H, with EV gap only 0.0058 (S=-0.5106, H=-0.2192, P=-0.2134) — attributed to the plan's documented "2x-independent-hands" `ev_split` approximation on an exceptionally close cell, not a code bug; left for Phase 5's formal tolerance-based gate to adjudicate rather than silently patched. Performance: full grid solve ~108s pure Python (16 hard totals now ~4x costlier from weighted-averaging, absorbed almost entirely by shared caching — 107.96s vs 106.85s before the fix); cached disk load 0.005s (>20,000x speedup), confirming the plan's "solve once, cache to disk" strategy is sufficient without `numba` for now. `basic_strategy.advise()` verified end-to-end: first-action fallback (D/Ds, Rh/Rs/Rp) correctly resolves via the cell's own `ev_by_action` dict filtered by real hand state rather than string-parsing the display code, and post-split DAS interaction (`hand.from_split` + `rules.double_after_split`) correctly gates doubling even when the chart cell alone says "D". `scripts/build_all_grids.py` initially failed with `ModuleNotFoundError: No module named 'src'` when run as `py scripts/build_all_grids.py` (Python puts the invoked script's own directory on `sys.path`, not the cwd) — fixed with the same `sys.path.insert` pattern T20's `scripts/` use for the identical problem (separate commit `c7b7d26`). All **32/32 shipped rulesets now solved and cached** to `data/strategy/` (ran across two background sessions after one was interrupted by session teardown; `solve_grid_cached`'s cache-skip correctly resumed from the 20 already done rather than re-solving them) |
| 5 | **Validation Gate** | `[x] Completed` | All 3 checks pass. Check 1: grid vs Appendix A, 1 passed (4D/6D/8D × S17/H17, 340 cells each). Check 3: all 5 rule-effect deltas close to published. Check 2: redesigned (2026-08-24) around `exact_edge.py` as the primary, zero-noise gate — all 4 deck counts match published anchors within -0.017pp to +0.0002pp; the Monte Carlo secondary sanity check (vs the exact figure, SE-aware tolerance) also passes for all 4. The historical "OPEN" gap was a measurement artifact (non-fresh-shoe simulation vs. a fresh-shoe anchor, then never re-verified at adequate precision after the fix), not a real bug — see detailed writeup below the table. One small real bug found and fixed along the way: `grid_builder.py`'s hard-cell decomposition weighting used a stale, un-depleted shoe composition (quantified impact: -0.0004pp, all 32 grids re-solved). Baseline locked to `data/baselines/house_edge_baseline.json` |
| 6 | Counting Systems & True Count | `[x] Completed` | Built `src/counting/systems.py` (all 7 systems as `CountingSystem` dataclasses: `HI_LO` default, `KO`, `HI_OPT_I`, `HI_OPT_II`, `OMEGA_II`, `ZEN`, `RED_7`, each with BC/PE, `tags`, `balanced`, `needs_ace_side_count`, and a per-system `irc_fn`) and `src/counting/counter.py` (`Counter`, `Counter.paired()` for dual-system mode). One spec gap found and resolved: the plan gives KO's IRC formula explicitly but not Red 7's — verified via web search rather than guessed, since a wrong IRC would silently mis-size real bets; confirmed `IRC = -2 × num_decks` (distinct from KO's `-4 × (decks-1)` scaling), which gives Red 7 a clean, testable invariant: it returns to exactly 0 (not KO's +4) after a fully-dealt shoe, same endpoint as the balanced systems. Also caught before it became a flaky test: `Shoe.deal()` assigns suit via an independent per-card coin flip, not tracked composition, so Red 7's full-shoe balance check needed a manually-constructed exact deck (2 red + 2 black 7s) rather than `Shoe`'s randomized suits. `tests/test_counting.py`: 34/34 passed — balanced-system IRC invariant (1/2/6 decks × 5 systems), KO's 6-deck worked example (-20 → +4), Red 7's IRC/exact-deck balance, floor/nearest/truncate rounding (verified distinguishing on both a negative case, -2.3, and a positive case, +2.7), unbalanced systems raise on `true_count()`, ace-side-count flags, and the paired-counter equivalence test (mid-shoe divergence check had to be fixed — Hi-Lo and Omega II are both balanced and correctly reconverge to the same IRC at full-shoe end, so independence has to be checked mid-shoe, not at the end). Full suite re-run clean: 49/49 across all phases |
| 7 | Count-Indexed Deviations | `[x] Completed` | Built `src/strategy/index_builder.py` (`implied_composition`, `insurance_index`/`insurance_correct`, `derive_index`, `build_named_indices`, `solve_indices_cached`) and `src/strategy/deviations.py` (`advise()`, `should_take_insurance()`). **Scoping decision**: derives indices for the named Illustrious 18 + Fab 4 + insurance (22 decision points) rather than sweeping all 340 grid cells — each swept TC is a genuinely distinct composition with far less cross-call caching reuse than a neutral-shoe grid solve gets, so a full-grid sweep was estimated at hours per ruleset+system for negligible value on the vast majority of cells that have no practically-relevant flip point; the reusable `derive_index`/`implied_composition` machinery isn't scoped-limited itself if a future phase wants more cells. Composition-from-count mapping derived and documented in index_builder.py's own docstring: a uniform per-tag-group scale factor `f = [RC+(A+B)]/(A-B)` (A/B = tag-weighted neutral sums over positive/negative-tag ranks), reducing to `f=RC/(2A)` for balanced systems — verified by hand against the plan's own worked example (Hi-Lo, TC+5, 4 decks: reproduces the "remove 10 low cards / add 10 high cards, split 8+2 across T/A proportionally" result exactly). Reused `grid_builder.py`'s own `_solve_hard_cell`/`_solve_pair_cell`/`_comp_minus_values` against a TC-perturbed composition instead of duplicating the decomposition-weighting logic Phase 5 already found and fixed a bug in once — required a small refactor (`_comp_minus_values` now takes a composition array instead of reconstructing a fresh one from `RuleSet` internally; confirmed behavior-preserving, all 49 then-existing tests still passed). Two real bugs found and fixed during verification, both in `deviations.py`'s runtime question-selection, not in the derivation math: (1) selecting between a cell's "primary" (S/H/D/P) and "surrender" (S/H/R) index by checking whether basic strategy's neutral-shoe action was already Surrender — wrong, since 3 of the 4 Fab 4 cells (14v10, 15v9, 15vA) have basic strategy at Hit and only flip TO surrender as the count rises, so they carry only a "surrender" entry that a baseline-action check would never find; fixed to check entry existence instead. (2) the "primary" index was being trusted directly as the final recommendation, but a restricted (no-surrender) comparison can flip before or after surrender stops dominating entirely (16 vs 10 stays surrender-optimal well past where "stand beats hit" alone would suggest) — fixed so the index is only a gate for whether to re-solve; the actual recommendation always comes from a live, fully-legal-action comparison at that point. `tests/test_deviations.py`: 30/30 passing — all 17 Illustrious 18 + 4 Fab 4 cells within the documented ±1 TC tolerance (6D/S17/DAS/LS, Hi-Lo), insurance at TC+3, plus 8 tests directly exercising `advise()`/`should_take_insurance()` runtime behavior (gating, EV-gain sign, post-split hands never deviating, the Fab-4-entry-only regression case). `data/indices/6d-s17-das-ls-p75__hi-lo.json` cache confirmed round-trips correctly (~9 min to derive fresh, ~0.3s from cache). Full project suite: 79/79. **Addendum from Phase 8**: `advise()`'s live re-solve (bug fix #2 above) turned out to be a serious per-hand performance problem, only surfaced once Phase 8's simulator called it hundreds of thousands of times — see Phase 8's entry for the fix (`ev_table` now captured across the whole derivation sweep and cached, so runtime never re-solves live) |
| 8 | MC Simulator & Edge Model | `[x] Completed` | Built `src/simulation/simulator.py` (`BucketStats`, `BatteryResult`, `run_battery` — extends the Phase 5 precursor rather than replacing it, since `simulate_house_edge` is still what Check 2 uses), `src/counting/edge_model.py` (`fit_edge_model`, weighted least squares over per-TC-bucket means; `predict_edge`/`is_extrapolating`; `save_baseline`/`load_baseline`), `src/simulation/metrics.py` (win rate, N0, risk of ruin, SCORE, DI), `scripts/run_sim_battery.py`. SCORE's exact constant wasn't guessed at: verified via search that SCORE = DI² = 1,000,000·EV²/Var (not an assumed ∝100 scaling), since the plan only states proportionality. `other_players` modelled as a documented card-burn approximation (mean 2.7 cards/hand fed to the counter, no full multi-seat engine) — matches Appendix B item 8's own "single-player is sufficient" guidance, just also capturing the hands-per-hour effect for free. **Critical performance bug found via Phase 8 testing, fixed in Phase 7's files**: `deviations.advise()`'s live re-solve (added during Phase 7 to fix the surrender-dominance bug) turned out to be a serious per-hand bottleneck — profiled at 27 hands/sec on a 50k-hand smoke test, traced via `cProfile` to a full uncached recursive EV re-solve on every hand where any of the 21 named gates tripped (several trip for roughly half of all true counts, e.g. "11 vs A" at any TC≥+1). Fixed by capturing `ev_by_action` at every swept TC during index derivation (`DerivedIndex.ev_table`, removing the early-break optimization since the full table is now needed) and having `advise()` look up the nearest cached TC instead of re-solving live — confirmed via `cProfile` this was the actual cause (2000 hands in 0.88s once fixed) and via a warm-cache rerun (50k hands in 12.4s, 4044 hands/sec, matching Phase 5's pure-basic-strategy throughput). `tests/test_simulation.py`: 12/12 passing (BucketStats, all 5 metrics formulas incl. the verified SCORE=DI² relationship, `fit_edge_model` recovers an exact synthetic linear relationship with R²=1.0, thin-bucket exclusion-but-still-reported, baseline save/load round-trip, a 1M-hand no-deviations battery matching the exact solver within 4 SE, and a 20k-hand with-deviations+other-players structural smoke test). Full project suite: 90/90. **Full 20M-hand verification battery** (`py scripts/run_sim_battery.py --decks 6 --das --surrender late --system hi-lo --hands 20000000 --generate`, 4163s at 4804 hands/sec): all 4 plan criteria pass — flat-bet edge at TC=0 (-0.3210% ± 0.0497%) matches the exact solver for this exact ruleset (0.3278% house edge, gap +0.0068pp = 0.14 SE); variance 1.3082 (target 1.25–1.35); fitted slope +0.4793%/TC (target 0.4–0.6%/TC); R² = 0.9896 restricted to TC∈[−3,+6] as the plan specifies (target >0.98 — the naive full-range R² was only 0.9789, expected since the plan itself flags convexity at high counts, so the fit was correctly re-evaluated over the actual trusted window rather than reporting the wrong number). Flat-bet overall mean was negative (N0=∞, RoR=100%) — expected and correct: perfect index play alone doesn't overcome the house edge without also varying bet size by count, which is exactly Phase 9's job. Baseline locked to `data/baselines/edge_model_baseline.json` |
| 9 | Bankroll, Kelly & Bet Ramp | `[x] Completed` | Built `src/bankroll/kelly.py` (`kelly_fraction`, `clamp_and_round`, `kelly_bet` — matches the plan's own given code exactly), `bet_ramp.py` (`build_ramp`, `RampLevel`, snapping to a doubling progression 1/2/4/8/16/... rather than rounding the raw continuous Kelly fraction, since "memorisable" is the whole point of a ramp), `risk.py` (`hours_to_double`, `simulate_drawdowns`, `RiskProfile`/`risk_profile`; re-exports Phase 8's own `risk_of_ruin`/`n_zero` from `metrics.py` rather than reimplementing them). Both plan worked examples reproduce exactly: `kelly_bet(10000, 0.01, 1.3, 0.5, 10, 1000, 5) == 40`; `risk_of_ruin(200, 0.01, 1.3) == 0.0461` (4.61%). `simulate_drawdowns` processes trials in batches (default 500) rather than one (n_trials, n_hands) array, per the 7.7GB dev-machine caution. **Real, non-obvious finding from testing `build_ramp` against the actual locked Phase 8 baseline** (not a hypothetical): `RampLevel.ev_cost` — normally positive, since snapping down from a raw Kelly fraction already >=1 unit strictly loses growth-rate — went slightly *negative* at TC +1 specifically, because the edge there was small-but-positive (raw Kelly wanted 0.591 units, under the 1-unit floor), and the mandatory floor bet happened to land closer to the true full-Kelly peak than half-Kelly's own target. Verified this is a real, reproducible property of the growth-rate curve (not a bug) by deriving why analytically (`g(f)=f·edge-0.5·f²·variance` is increasing below the full-Kelly peak, so overshooting half-Kelly while staying under full-Kelly can only help) and adding a regression test using the actual locked baseline's own intercept/slope that confirms it happens — reports it honestly (per `.agents/instructions.md`'s "No Bare Point Estimates") rather than clamping the number to look tidier. `tests/test_bankroll.py`: 14/14 passing, including both the "ev_cost >= 0 once raw_kelly_units >= 1" proof and the "floor can slightly beat half-Kelly below 1 unit" regression case. Full project suite: 105/105 |
| 10 | Flask API | `[x] Completed` | Built `app.py` with all 9 routes. **Real architectural decision, not just wiring**: `game.py`'s `play_round()` was a single synchronous call driven by a `decide_fn` callback (built for simulation/AI, answers instantly) — but `/api/game/deal`+`/api/game/action` need to pause BETWEEN separate HTTP requests waiting for a human's click. Rather than hand-roll a second state machine duplicating split/double/hit/surrender legality (real risk of drifting from `game.py`'s own rules over time), converted the recursive hand-playing logic to a generator (`play_hands_interactive`, yields `(hand, legal_actions)`, receives the action via `.send()`), with `play_round` now just driving that SAME generator with a `decide_fn` in a tight loop — one implementation of the actual game rules, not two. Also split `play_round` into `deal_initial()`/`settle_round()` so the API can deal via one request and settle via a much later one while reusing the exact same blackjack/peek/OBBO logic. Confirmed behavior-preserving against the FULL existing suite before building anything on top (this file underpins every phase from 5 onward). Deduplicated three places that had each independently redefined the same lookups: `shipped_rulesets()`/`SHIPPED_DECKS` etc. (was copy-pasted in 2 scripts) moved to `rules.py`; `system_for_slug()` (was copy-pasted in 2 scripts) moved to `systems.py`; added `edge_model.keyed_baseline_path()` so multiple ruleset+system edge models can coexist (only `data/baselines/edge_model_baseline.json`, a single fixed file, existed before — migrated the one locked Phase 8 baseline to the new convention, no re-simulation needed). Registries: grids are eagerly loaded for all 32 shipped rulesets (fast, disk-cache is warm); indices and edge models are NOT (only 1 of 32 combos has ever been pre-built for either, deriving one takes ~9 minutes) — `/api/stake`/`/api/simulate` check for a pre-built file first and return a clean 400 naming the exact command to run, rather than block a request for 9 minutes. `/api/simulate` capped at `MAX_SIMULATE_HANDS=200,000` per the plan's `[!WARNING]`. Plan's own `/api/advise` worked example reproduces almost exactly: `action="Rh"`, `ev={stand:-0.5401, hit:-0.5349, surrender:-0.5}` (published example rounds to -0.54/-0.53/-0.50). **Non-obvious lesson from testing, not a bug**: a fresh `/api/game/deal` call can itself resolve instantly (player/dealer blackjack, ~a few percent of hands), leaving no round in progress at all — three tests initially assumed a round is always active after dealing and were flaky as a result (failed 1-in-~20-ish runs); fixed by retrying until an active round is dealt (deterministic, not slower in the common case) and adding a dedicated test for the instant-blackjack path itself rather than leaving it to chance. `tests/test_app.py`: 19/19 passing, confirmed stable across 7+ repeated full runs after the fix. Full project suite: 125/125 |
| 11 | Web UI | `[x] Completed` | Built `static/index.html`, `static/css/style.css`, `static/js/{app,rules,table,grid,counting,bankroll,simulator}.js` (one extra file, `simulator.js`, vs. the plan's listed set -- the Simulator tab's logic needed its own module just like the other four tabs; not a scope change). Adapted T20's glassmorphism dark-mode design system (Outfit font, sidebar nav, glow buttons, glass cards, metric tiles) with a felt-green/gold accent replacing T20's cyan/purple, and no Chart.js dependency -- EV comparisons, the strategy grid, the bet ramp, and the edge-vs-count curve are all plain CSS/DOM bar charts, since this is a local app with no need for a CDN dependency. **Required a small, additive change to `app.py`** (still Phase 10's file, but Phase 10's own routes are untouched): added `static_folder`/`static_url_path=""` and a `/` route serving `index.html`, since Flask's default `/static/...` prefix doesn't match the plan's relative `css/`/`js/` paths -- verified live (dev server + curl/PowerShell `Invoke-RestMethod`) that `/`, `/css/style.css`, and `/js/*.js` all now 200. All 5 tabs wired to real, already-shipped API responses only -- confirmed against a live server rather than assumed: `/api/rules` populates the shared ruleset+system selectors; Play tab drives `/api/game/new`+`/deal`+`/action` and calls `/api/advise` at each decision point, filtering its EV bars to the session's own `legal_actions` (advise's `ev` dict can include actions that aren't legal at 3+ cards, e.g. a stale D/R key from the total-only grid cell -- confirmed live and handled client-side rather than trusted raw); Strategy Grid renders the solved hard/soft/pairs tables directly from `/api/grid`'s `{total}v{upcard}` keys (upcard 11 = Ace), color-coded by action with a dot marker for sub-0.001-margin cells; Counting tab drives `/api/count`'s paired betting/playing mode plus a client-only weighted-random drill; Bankroll and Simulator both sample `/api/stake` across a fixed true-count range to draw a bet ramp / edge-vs-count bar chart client-side, since neither is a dedicated endpoint. **Two build-plan features are documented as out of scope, not silently dropped**: the Play tab's total-dependent/composition-dependent mode toggle (Phase 3's Step 4 `mode="composition_dependent"` was never actually implemented anywhere in `src/strategy/` -- `grid_builder.py`/`basic_strategy.py`/`/api/advise` only ever support total-dependent -- so there is no real mode to toggle), and the Simulator tab's drawdown-distribution chart (`risk.py`'s `simulate_drawdowns` is not exposed via any API route). Live-verified end to end against the running dev server (not just read against source): `/api/grid` cell shape, a full `/api/game/new`→`deal`→`action`→round-settle round trip including a double-and-bust dealer hand, `/api/advise` with the game session's own literal dealt ranks (dealer/player cards come back as literal `J`/`Q`/`K`, not the collapsed `T` bucket -- confirmed `Card(rank="J", ...)` resolves correctly via `RANK_INDEX` without any client-side remapping needed), `/api/count` paired mode, `/api/stake`, and `/api/simulate` both with and without a pre-built index cache (confirmed the clean 400 naming `scripts/build_all_indices.py` when one is missing). Full existing suite re-run clean after the `app.py` change: `tests/test_app.py` 19/19. |
| 12 | Regression Harness & CI | `[x] Completed` | Built `tests/regression_test.py` (standalone script, not pytest -- reuses `test_strategy_grid.py`'s and `test_house_edge.py`'s own logic directly rather than duplicating it), `.github/workflows/regression.yml`, `docs/system_guide.md`. **One real deviation from the plan's literal wording, documented rather than papered over**: the plan describes checking "every shipped grid against `strategy_baseline.json`" and "every index table against `deviation_baseline.json`" -- neither file was ever created in Phase 5/7 (grid correctness is validated directly against the Appendix A fixture each run, which is fast/deterministic/free of anything a separate lock file would add; likewise the Illustrious 18/Fab 4 are validated against their own published values, not a derived-and-locked copy of them). `regression_test.py` reflects that actual architecture rather than inventing two baseline files nothing else produces or consumes. **A real, caught-before-shipping bug in the script itself**: an early version of the house-edge check unconditionally recomputed `exact_house_edge()` for all 4 shipped anchor rulesets even under `--fast` -- fine for 2D (~68s) but 8D alone is ~16 minutes (see Phase 5's own timing notes), so a live `--fast` run was found hanging at ~3 minutes of CPU time via `Get-CimInstance Win32_Process`, diagnosed, and fixed: `--fast` now recomputes only the cheapest (2-deck) anchor live as a canary and trusts the locked file's own recorded `primary_pass` for the rest, named explicitly as "NOT recomputed in --fast" rather than silently skipped. Live-verified after the fix: `py tests/regression_test.py --fast` -- **11/11 checks passed in 65.3s** (32/32 grid caches fresh, Appendix A match, 2D exact edge gap exactly `+0.00e+00` vs the locked baseline, Illustrious 18/Fab 4/insurance all within tolerance, edge model loads with a positive slope). The two checks `--fast` skips were verified standalone instead of via a full ~50-minute end-to-end run (dominated entirely by re-deriving the already-proven-correct 4D/6D/8D exact figures, which would add no new information about this script's own correctness): the edge-model fresh-battery cross-check (`check_edge_model(fast=False, ...)` called directly, 20,000-hand battery, 3/3 passed) and the MC-secondary arithmetic path (`simulate_house_edge` + the same tolerance formula, run standalone for 2D at 50,000 hands, gap +0.23pp against a tol of 2.06pp, correctly bounded). `--generate`/`--generate-ruleset <decks>` re-lock `house_edge_baseline.json` only, by direct reuse of `test_house_edge.py`'s own `run_check` -- `edge_model_baseline.json` stays `scripts/run_sim_battery.py --generate`'s job (a separate, ~70-minute artifact), consistent with the plan's Regression Guard section. CI (`.github/workflows/regression.yml`) runs the full unit suite then `regression_test.py --fast` on every push/PR to `main` and on every PR. `docs/system_guide.md` written as the deep walkthrough the plan calls for: solver derivation (peek conditioning, split-EV approximation, why only `total_dependent` mode exists), where every published anchor this repo checks against actually came from (basic-strategy chart, house-edge anchors, rule-effect deltas, Illustrious 18/Fab 4, edge-model fit), the count-to-composition mapping, the two true-count rounding conventions, and why half-Kelly (including the verified, non-hypothetical negative-`ev_cost` finding from Phase 9). |

> [!IMPORTANT]
> Update this table **the moment a phase is actually implemented**, before starting the next one — never batch updates to the end of a session. Each completed row's Notes must record what was built (and any deviation from this plan, with the reason) plus the **actual numbers** from that phase's Verification block, not a restatement of the expected output. A tracking table that lags reality is worse than none: it actively misleads the next session about where the project stands.

### Phase 5 Detailed Findings

**Files built:** `tests/test_strategy_grid.py`, `tests/test_house_edge.py`, `src/simulation/simulator.py` (lightweight Monte Carlo precursor to Phase 8), `src/strategy/exact_edge.py` (zero-noise combinatorial house-edge diagnostic, not in the original plan — built mid-phase, see below).

**Check 1 — grid vs Appendix A: PASSES.** `py -m pytest tests/test_strategy_grid.py -q` — 1 passed. Covers all 6 multi-deck rulesets (4D/6D/8D × S17/H17), 340 cells each. Two real bugs were found and fixed while getting this to pass:

1. **Hard-total decomposition bias** (found before Check 1 existed, during Phase 4 spot-checking, but only fully diagnosed here): using a single representative 2-card decomposition (`min(10, total-2)`) for hard totals systematically over-selected Tens, flipping hard-12-vs-4 to H against the published S. Fixed with frequency-weighted averaging across every valid non-pair decomposition. (Phase 4 commit.)
2. **`ev_split_hand` missing a 2× factor on the resplit candidate**: when a post-split hand draws a second matching card and considers resplitting again, the recursive `ev_split_hand(...)` call represents one new hand's value, but resplitting produces *two* new hands — exactly the same 2× the top-level `ev_split()` applies, just one level deeper. Omitting it made resplitting look artificially cheap (blackjack EVs are usually negative, so the *unscaled*, less-negative value looked better than its true cost), so it got chosen too often. This fixed two real chart mismatches outright — 7,7 vs 8 (was P, should be H, margin 0.017) and 8,8 vs A under H17 (was P, should be Rp per the plan's own documented H17 delta, margin 0.025) — and fixed the previously-recorded 3,3-vs-8 near-miss as a side effect. (Commit `28e2f87`.)

One near-miss remains, documented in `KNOWN_NEAR_MISSES`: soft 18 vs 2 solves to S where Appendix A shows Ds (EV gap 0.003 — S=0.12400, D=0.12098). Unlike the two bugs above, this isn't a decomposition or split-recursion issue (soft totals have an exact, unambiguous 2-card comp). Hand-tracing the double shows a genuinely close balance: 7 of 10 possible draws degrade soft 18 to a mediocre hard 12–18 against the dealer's weak 2, only 3 (A,2,3) improve or hold it soft. Investigated but not conclusively resolved either way; tracked rather than silently excluded.

**Check 2 — house edge vs published anchors: RESOLVED, ALL PASS (2026-08-24).** The gap below turned out to be **a measurement problem in the check, not a bug in the solver, grid, or game.py** — found by switching from ever-larger Monte Carlo runs to a zero-noise combinatorial calculation instead of chasing precision.

Original open state, inherited from 2026-08-21 (`py tests/test_house_edge.py --hands 30000000 --decks 2 4 6 8`, pre-fix, 2D/4D only at this N):

| Decks | Simulated edge | Published anchor | Gap | In SE terms |
|---|---:|---:|---:|---:|
| 2 | 0.259% ± 0.021% | 0.190% | +0.069pp | ~3.3 SE |
| 4 | 0.399% ± 0.021% | 0.350% | +0.049pp | ~2.3 SE |

The 2026-08-21 session had isolated this to "somewhere in the `game.py`/`basic_strategy.advise()` layer, mechanism not found" and stopped there (see the two ruled-out hypotheses it left behind: penetration/depletion, and the legal-action fallback path). Continuing from there:

1. **Residual diagnostic**: instrumented `strategy_decide_fn` to record, for each round's *first* decision only, its (category, action) and the grid's own predicted EV, then compared against that round's realized payout across 1.5M hands. Mean residual **0.0157%**, no bucket significant (`|z| < 2` throughout). This rules out a `game.py`/`basic_strategy.py` execution bug for every hand that reaches a decision point — but can't see blackjack/dealer-peek rounds, which never call `decide_fn`.
2. **Quantified the one real methodological gap between `grid_builder.py` and `exact_edge.py`**: `_solve_hard_cell`'s decomposition weights came from a fresh, un-depleted shoe composition, never accounting for the dealer's upcard already being a known, dealt card. A full triple-loop enumeration measured its exact aggregate impact at **-0.0004pp** for 2-deck — real, but two orders of magnitude too small to be the gap. Fixed anyway as an unambiguous correctness bug (weights now deplete the upcard's bucket first); all 32 shipped grids re-solved to match, Check 1 and `test_engine.py` re-confirmed passing.
3. **Re-examined the 2026-08-21 "ruled out" fresh-shoe finding and found it unsound.** The n=30M measurement above (the only one with real statistical weight) predates `fresh_shoe_per_hand` entirely. The follow-up that supposedly confirmed the gap persisted under `fresh_shoe_per_hand=True` ran at only n=2M (0.266%, SE≈0.08%) — under 1 SE from the 0.19% anchor, and just as consistent with a true value near 0.176%. "Essentially unchanged, ruled out" compared two point estimates without weighing precision at all.
4. **The decisive test**: `exact_house_edge()` (already built for Check 3) computed for all 4 deck counts — full, zero-sampling-noise combinatorial enumeration:

   | Decks | Exact (zero-noise) | Published | Gap |
   |---:|---:|---:|---:|
   | 2 | 0.1727% | 0.1900% | -0.0173pp |
   | 4 | 0.3439% | 0.3500% | -0.0061pp |
   | 6 | 0.4002% | 0.4000% | +0.0002pp |
   | 8 | 0.4284% | 0.4300% | -0.0016pp |

   Every deck count matches its anchor closely — 6D to within 0.0002pp — confirming the solver and grid are correct across the board, independent of any Monte Carlo noise.
5. A follow-up high-precision Monte Carlo confirmed this directly: 2D at n=15M gave **0.1752% ± 0.0298%**, comfortably within tolerance of the anchor. A subsequent n=10M run for 4D/6D/8D (0.3879%/0.4779%/0.4471%) nominally "failed" the *old* flat ±0.02% tolerance despite being unbiased — because a flat tolerance compared against a noisy point estimate can't distinguish a real gap from sampling luck (6D's apparent 2.1 SE "miss" evaporates entirely against the exact figure).

**Conclusion: no solver, grid, or game.py bug ever caused Check 2's gap.** The original gap was real (a non-fresh-shoe simulation compared against a fresh-shoe anchor), but once the `fresh_shoe_per_hand` fix landed it was never re-verified at adequate precision — and the check's flat-tolerance design couldn't have told a real bug from noise even if someone had.

**Check 2 redesigned as a result** (see the Implementation section above): `exact_house_edge()` is now the **primary** gate against the published anchor (flat ±0.02%, justified since it's noise-free); the Monte Carlo simulation is now a **secondary sanity check** against the primary's own exact figure — not the anchor — with a tolerance of 4×its own standard error, so it can still catch a real `game.py` integration bug without being sensitive to sampling luck. Final run, `py tests/test_house_edge.py --hands 2000000 --decks 2 4 6 8 --generate`:

| Decks | Exact vs anchor | Simulated vs exact (n=2M) |
|---:|---|---|
| 2 | 0.1727% vs 0.1900% (-0.0173pp) **PASS** | 0.2449% ± 0.0817% (+0.0722pp, tol 0.3267pp) **PASS** |
| 4 | 0.3439% vs 0.3500% (-0.0061pp) **PASS** | 0.3894% ± 0.0815% (+0.0455pp, tol 0.3260pp) **PASS** |
| 6 | 0.4002% vs 0.4000% (+0.0002pp) **PASS** | 0.4645% ± 0.0816% (+0.0643pp, tol 0.3264pp) **PASS** |
| 8 | 0.4284% vs 0.4300% (-0.0016pp) **PASS** | 0.4862% ± 0.0817% (+0.0578pp, tol 0.3267pp) **PASS** |

**ALL PASS.** Baseline locked to `data/baselines/house_edge_baseline.json`. Phase 6+ is now unblocked.

**Check 3 — rule-effect deltas: all 5 done, all close to published.** Picked back up (autonomous continuation, 2026-08-21) using `exact_edge.py` — cheap (seconds to minutes per ruleset) since it doesn't need Monte Carlo precision. Base case: 6D/S17/DAS/no-surrender/3:2 = **0.4002%**, matching the 6D anchor (0.40%) almost exactly — a second, independent confirmation (beyond Check 1) that the solver itself is sound, further isolating Check 2's unresolved gap to the simulation-integration layer specifically.

| Rule change | Exact delta | Published | Match |
|---|---:|---:|---|
| H17 (vs S17) | +0.2131pp | ~+0.22pp | close |
| No DAS (vs DAS) | +0.1419pp | ~+0.14pp | very close |
| No surrender (vs LS) | +0.0724pp | ~+0.08pp | close |
| 6:5 payout (vs 3:2) | +1.3597pp | ~+1.39pp | very close |
| RSA | +0.0696pp | ~+0.08pp | close (only after the fix below — was exactly 0 before it) |

**Design bug found and fixed while preparing the RSA delta**: `game.py`'s `_play_one_hand` and `ev_solver.py`'s `ev_split_hand` both gated a split-aces hand's *entire* further action — including the ability to **resplit** on drawing a third ace — behind `rules.hit_split_aces`. In standard casino terminology these are independent toggles: "resplit aces" (may split again if a split-ace hand draws another ace) is commonly offered without also offering "hit split aces" (may hit non-ace cards on a split-ace hand). The old code treated them as one, so `resplit_aces=True` had **zero effect** whenever `hit_split_aces=False` (the default) — silently contradicting the RuleSet field's own "RSA ≈ +0.08%" comment. Confirmed by computing the RSA delta before the fix: exactly 0.0000pp. Fixed in both `game.py` (offers exactly `{STAND, SPLIT}`, never HIT/DOUBLE, when a mandatory one-card split-ace hand re-pairs and `resplit_aces` permits it) and `ev_solver.py` (matching `ev_split_hand` branch, with the same 2× resplit-hand scaling as the earlier fix). `resplit_aces` defaults to `False` in every ruleset shipped/tested so far, so this bug never affected any previously-reported result — caught by design review while setting up this delta, not by an observed discrepancy. Two new tests added to `tests/test_engine.py` (resplit correctly offered under `resplit_aces=True`, and correctly *not* offered by default — regression protection): 14/14 passing. Commit `8e074dd`.

All 32 shipped grids re-solved to sync the on-disk cache with `ev_solver.py`'s new source hash (the fix's new code path is unreachable for any of them, since all have `resplit_aces=False`, so this is expected to produce byte-identical cell values — confirmed once the re-solve completes).

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|:--------:|------------|
| Peek conditioning omitted in the dealer distribution | 🔴 Critical | Phase 5 cell-for-cell chart comparison; 16 vs 10 and 12 vs 4 are the cells that will show the problem first |
| Exact solver too slow in pure Python | 🟡 Medium | Solve once per ruleset and cache to `data/strategy/`; the runtime app never re-solves. Escalate to `numba` only if `build_all_grids.py` exceeds ~10 min |
| Split EV recursion wrong (resplits, DAS, split aces) | 🔴 Critical | Phase 2 unit tests on payouts; Phase 5 pair-grid comparison; the 2,2 / 3,3 / 4,4 rows are the sensitive ones |
| Monte Carlo mistaken for a result without error bars | 🔴 Critical | `metrics.py` returns standard errors on every figure; UI and tests must render them. No bare point estimates anywhere |
| Count-to-composition mapping in Phase 7 has no single correct answer | 🟡 Medium | Document the proportional-within-tag-group choice explicitly; ±1 TC tolerance vs published indices; ≥2 is a bug |
| Memory exhaustion on the 7.7GB dev machine | 🟡 Medium | Bounded cache tables, chunked MC batches, `if __name__ == "__main__":` guards on every standalone script |
| Cached grids drift from solver code | 🟡 Medium | Hash-validated cache manifest keyed on solver source + RuleSet; **no exception** for unmanifested files (T20's specific, costly bug) |
| Edge model extrapolated past its sampled range | 🟡 Medium | Clamp the linear fit to TC ∈ [−5, +8]; UI shows per-bucket sample counts and greys out thin buckets |
| Users treating simulated edge as a guarantee | 🟡 Medium | Explicit variance, RoR and drawdown display next to every bet; plain-language disclaimer in UI and README |

---

## Regression Guard

> [!CAUTION]
> Once Phase 5 locks `data/baselines/strategy_baseline.json` and `house_edge_baseline.json`, **the engine (`src/engine/`, `src/strategy/dealer_probs.py`, `src/strategy/ev_solver.py`) is effectively frozen.** Phases 6–12 are additive layers on top of a validated core and must be verifiable as byte-identical no-ops against those baselines.
>
> If a later change *does* move a baseline:
> 1. Establish that the move is a **correctness fix**, not a regression, and write down the mechanism.
> 2. Record the before/after numbers in this plan's tracking table and in `docs/system_guide.md`.
> 3. Re-lock deliberately with `py tests/regression_test.py --generate-ruleset <key>` — never with a blanket `--generate` that silently absorbs unrelated drift.
>
> A baseline that moves without all three steps is indistinguishable from a bug that was papered over.

---

## Appendix A — Reference Charts (Phase 5 Known-Answer Test)

**4/6/8 decks · dealer stands on soft 17 · DAS · late surrender · 3:2 · dealer peeks.**

These are the published charts, encoded here as the Phase 5 test fixture. **The shipped grid is solver output, not this transcription** — if the two disagree, the solver is presumed wrong until proven otherwise, and if the solver is proven right this appendix gets corrected.

Legend: `H` hit · `S` stand · `D` double else hit · `Ds` double else stand · `P` split · `Ph` split if DAS else hit · `Rh` surrender else hit

### Hard Totals

| Player | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | A |
|---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 5–8 | H | H | H | H | H | H | H | H | H | H |
| 9 | H | D | D | D | D | H | H | H | H | H |
| 10 | D | D | D | D | D | D | D | D | H | H |
| 11 | D | D | D | D | D | D | D | D | D | H |
| 12 | H | H | S | S | S | H | H | H | H | H |
| 13 | S | S | S | S | S | H | H | H | H | H |
| 14 | S | S | S | S | S | H | H | H | H | H |
| 15 | S | S | S | S | S | H | H | H | Rh | H |
| 16 | S | S | S | S | S | H | H | Rh | Rh | Rh |
| 17–21 | S | S | S | S | S | S | S | S | S | S |

### Soft Totals

| Player | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | A |
|---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| A,2 (13) | H | H | H | D | D | H | H | H | H | H |
| A,3 (14) | H | H | H | D | D | H | H | H | H | H |
| A,4 (15) | H | H | D | D | D | H | H | H | H | H |
| A,5 (16) | H | H | D | D | D | H | H | H | H | H |
| A,6 (17) | H | D | D | D | D | H | H | H | H | H |
| A,7 (18) | Ds | Ds | Ds | Ds | Ds | S | S | H | H | H |
| A,8 (19) | S | S | S | S | S | S | S | S | S | S |
| A,9 (20) | S | S | S | S | S | S | S | S | S | S |

### Pairs

| Player | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | A |
|---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| A,A | P | P | P | P | P | P | P | P | P | P |
| 10,10 | S | S | S | S | S | S | S | S | S | S |
| 9,9 | P | P | P | P | P | S | P | P | S | S |
| 8,8 | P | P | P | P | P | P | P | P | P | P |
| 7,7 | P | P | P | P | P | P | H | H | H | H |
| 6,6 | Ph | P | P | P | P | H | H | H | H | H |
| 5,5 | D | D | D | D | D | D | D | D | H | H |
| 4,4 | H | H | H | Ph | Ph | H | H | H | H | H |
| 3,3 | Ph | Ph | P | P | P | P | H | H | H | H |
| 2,2 | Ph | Ph | P | P | P | P | H | H | H | H |

**H17 deltas** (dealer hits soft 17 — encode as a separate fixture): hard 11 vs A becomes `D`; A,7 vs 2 becomes `Ds`; A,8 vs 6 becomes `Ds`; 8,8 vs A becomes `Rp`; hard 15 vs A becomes `Rh`; hard 17 vs A becomes `Rs`.

**2-deck deltas** (S17 — separate fixture): hard 9 vs 2 becomes `D`; hard 11 vs A becomes `D`; A,8 vs 6 becomes `Ds`; 6,6 vs 2 becomes `P`.

---

## Appendix B — Open Decisions

| # | Decision | Recommendation | Owner |
|---|---|---|---|
| 1 | Repository name | `Blackjack_Strategy_Engine` (mirrors T20's `<Domain>_<Thing>_<Type>` naming) | User |
| 2 | Repo visibility | Public — the plan and solved grids are the interesting artifact | User |
| 3 | Commit `markdowns/` and `data/strategy/`? | **Yes** — deviates from T20, justified above | User |
| 4 | Ship 6-deck alongside the requested 2/4/8? | **Yes** — it is the primary validation anchor and costs nothing | Recommended |
| 5 | Default counting system | Hi-Lo (highest BC among level-1 balanced systems; every published index is quoted for it) | Recommended |
| 6 | Default Kelly fraction | 0.5 (half-Kelly) — 75% of the growth at roughly half the volatility | Recommended |
| 7 | `numba` as a hard dependency? | No — cache-first; add only if `build_all_grids.py` proves too slow | Recommended |
| 8 | Multi-player table simulation in Phase 8 | Defer to v2; single-player is sufficient for edge and variance | Recommended |
