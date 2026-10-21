# System Guide — Poker Solver

> **Author:** Claude Code (Sonnet 5) · **Date:** 2026-08-28
> **Purpose:** A deep technical walkthrough of how the poker engine actually works — where CFR comes from, why MCCFR became necessary, what the equity-realisation approximation does and does not justify, why abstraction exploitability is not real-game exploitability, and the derivation of the risk-of-ruin form — for anyone (human or agent) who needs to reason about *why* the code is shaped the way it is, matching `docs/system_guide.md`'s own role on the blackjack side.
> **Companion docs:** `markdowns/poker/poker_build_plan_v1.md` (the full phased build history, every deviation and bug found along the way, and the Implementation Tracking table with real verification numbers per phase), `.agents/skills/poker_*/SKILL.md` (the rules this guide explains the reasoning behind).

---

## 1. Why an equilibrium solver instead of a transcribed chart

The blackjack side computes exact EV by combinatorial enumeration over a shoe and treats published charts as a known-answer test, never a source of truth. Poker's analogue is CFR (Counterfactual Regret Minimisation): rather than transcribing a published preflop chart, `src/poker/cfr.py` finds an approximate Nash equilibrium of the actual (abstracted) betting tree by self-play, and the small number of published references this repo has (Appendix A of the build plan — Kuhn's analytic equilibrium, ICM worked examples, risk-of-ruin/win-rate tables) are used the same way blackjack uses its Appendix A: as a known-answer test the solver either passes or is presumed wrong against.

Everything downstream is a consequence of one recursive traversal:

```
GameSpec ──▶ evaluator.py / equity.py / ranges.py (mechanics: hand strength,
             │                                       equity, card removal)
             ▼
tree.py (betting-tree structure, no card knowledge) ──▶ cfr.py (regret
             │                                            matching / MCCFR)
             ▼
exploit.py (best response, the number a CFR run has actually earned the
             │                                right to report)
     ┌───────┼──────────────────────────────┐
     ▼                                       ▼
toy.py (Kuhn/Leduc — validation gate,   pushfold.py / icm.py (short-stack
 CFR checked against an INDEPENDENT      jam/fold, fictitious play over the
 sequence-form LP before trusting        equity matrix directly, no CFR)
 it on anything real)
             │
             ▼
advisor.py / solve_preflop.py (the REAL preflop game: 169-class
     abstraction, equity-realisation terminal values) ──▶ solve_spot.py
             │                                            (bounded river-only
             ▼                                             postflop spot)
     bankroll.py (risk of ruin, win-rate CI)
             │
             ▼
     api.py (Flask Blueprint) ──▶ static/poker.html (web UI)
```

`GameSpec` (`src/poker/spec.py`) plays exactly the role `RuleSet` plays on the blackjack side: every EV, equity, and exploitability figure is a function of it, never a hardcoded stack depth or bet-size grid.

---

## 2. CFR: why CFR+ by default, and why MCCFR became necessary

### 2.1 The one idea that matters

At every information set, CFR tracks each action's counterfactual regret and plays proportionally to positive regret (regret matching). The **average** strategy over all iterations is what's proven to converge to a Nash equilibrium — the **current** iterate oscillates and can be arbitrarily far from equilibrium at any single point. Every `solve()`/`solve_mccfr()` result reports the average strategy; nothing in this codebase ever reads the raw regret-matched strategy as if it were the answer. The same "average converges, current oscillates" property shows up twice more elsewhere in this codebase, independently rediscovered rather than assumed: classical fictitious play (`pushfold.py`, Phase 9 — an earlier damped-iterate version genuinely never converged) and, trivially, in the sense that CFR+'s own linear averaging is a *weighted* version of the same idea.

### 2.2 Three full-tree variants, one traversal

`vanilla`, `cfr+`, and `dcfr` share one recursion (`_traverse`) differing only in which players update each iteration, how regrets floor/discount, and how the strategy sum is weighted — built this way deliberately, since three separately-written near-duplicate traversals is exactly the kind of divergence-prone code this project has hit real bugs from elsewhere (the equity-shape-collision bug in `build_preflop_equity.py`, the min-raise-legality naming bug in `tree.py`). `cfr+` is the shipped default per the plan; measured on Kuhn it is markedly *slower* to converge than vanilla/DCFR at matched small iteration counts (CFR+'s alternating updates halve each player's effective per-iteration learning rate on a game this tiny) but is the standard choice at real scale, where its regret-flooring and linear averaging give better empirical convergence.

### 2.3 MCCFR: the escalation Phase 7 explicitly deferred, and Phase 10 needed anyway

Phase 7's own text called external-sampling MCCFR "unnecessary for preflop and toy games." That held for Kuhn and Leduc. It did **not** hold for the real preflop game: the plan's own example spec (`hu-100bb-r5c3-s5`) builds a 23,869-node, 7,957-infoset card-agnostic betting tree; combined with the lossless-but-large 169-class deal (169×169 = 28,561 chance outcomes), a single full-tree traversal is on the order of 680 million node-visits — discovered empirically at the start of Phase 10, not anticipated at Phase 7. `solve_mccfr` (Lanctot et al. 2009) samples chance's and the opponent's actions to one branch each, fully exploring only the updating player's own actions, and converges to the same equilibrium in expectation at a fraction of the per-iteration cost.

Two real performance bugs were found building this, both instructive about where the actual cost hides in a sampling-based solver:

- **Re-extracting chance probabilities every iteration.** `_traverse_mccfr` recomputed and renormalised a probability array from the root chance node's outcome list on every single call — for a 28,561-outcome root, this dominated per-iteration cost. Fixed via `_cached_probs()`, keyed by the outcome list's own object identity (stable across iterations for any game that builds its chance list once, like `PreflopGame` — no-op for Kuhn/Leduc's tiny per-call lists). ~7.8× speedup measured.
- **Computing the final game value exactly, even for a game too large to enumerate.** `solve_mccfr`'s reported `game_value` defaulted to full exact enumeration (`_expected_value`) — profiling showed this one call consuming 99.96% of *total* runtime on a spec far smaller than the plan's own example, completely defeating the point of using MCCFR at all. Fixed by adding `exact_value=False` (Monte Carlo estimate of the value under the final strategy, with a standard error) — required for any large game.

### 2.4 The look-ahead bias in sampled exploitability

`sampled_exploitability()` (`exploit.py`) extends Phase 8's exact best-response algorithm to a sampled subset of deals, for the same reason MCCFR exists: exact enumeration is intractable at real scale. It carries a real, understood, **directional** bias: at small `n_deals`, it always *overestimates* true exploitability (confirmed via a regression test at Kuhn's exact equilibrium, where the true answer is 0 — measured at 0.135 at `n_deals=6`, shrinking to 0.0086 at `n_deals=2000`, never fully vanishing at small samples even across many independent trials). The mechanism: each trial's own best-response pass *selects* the responder's best action via argmax over that trial's own noisy sampled totals, then the *same* trial's second pass evaluates that selection using the identical sample — whenever two actions are genuinely close in true value (which an equilibrium guarantees for every on-path action), a small sample can make a not-quite-best action look best by chance, and evaluating it on that same sample confirms its own mistake. This is a one-sided error (a wrong pick can only look *better* than the truly-best action within that noisy sample, never worse), so the bias is safe-directioned for this project's purposes — but it means a reported exploitability figure at a small `exploit-deals` is a **ceiling**, not a point estimate to be trusted at face value.

---

## 3. Equity realisation: the largest modelling compromise in this codebase

Preflop lines that end without seeing a flop (a fold, or an all-in that runs to showdown) have **exact** terminal values — no cards are needed for a fold; a showdown-after-all-in uses the exact, combo-weighted 169×169 equity matrix (Phase 3). Lines that instead see a flop do **not** have exact values here: solving the real postflop game is out of scope for this project (Appendix B item 4 of the build plan). `advisor.py`'s `PreflopGame` approximates a flop-seeing line's value as the same all-in equity, shifted toward the in-position player by an amount that peaks at a coinflip (vanishes for a near-lock) and grows with the stack-to-pot ratio (more room for postflop skill to matter deep).

This is a **larger** compromise than blackjack's `2 × one_hand_EV` split approximation. Blackjack's approximation is worth about 0.01% and was validated by matching published charts built on the identical assumption. Equity realisation is worth considerably more, and there is no published reference built on the same assumption to validate against. What follows from this, and must be respected everywhere this module's numbers are used: the solved strategy is an equilibrium **of the approximated game**, not of real no-limit hold'em; its exploitability is measured against that same approximated game; and neither number transfers to a real table without that qualification attached. The realisation parameters (`POSITION_BONUS_MAX`, `SPR_CAP`) are recorded in every solved strategy file's `realisation_factors` field precisely because changing them changes the answer — they are part of the game's definition, not a tuning knob applied after the fact.

`solve_spot.py` (Phase 10) sidesteps this compromise entirely for postflop, by construction: it is scoped to a **complete (river) board only**. With all 5 board cards fixed, every showdown has an exact value via `evaluator.evaluate(hole + board)` — no equity-realisation approximation anywhere in that module. The cost of that scope decision is that `solve_spot.py` cannot solve a flop or turn spot; it answers "given we've already reached the river with these ranges, this pot, and these stacks, how should this betting round be played," not "solve the flop."

---

## 4. `abstraction_exploitability_mbb`: never bare "exploitability"

Every exploitability figure this repo reports on real (abstracted) poker — as opposed to Kuhn/Leduc, whose trees *are* the real games — is measured **inside** whatever card/bet abstraction was actually solved, not at a real table. A 2,271.62 mbb/g figure on the real `hu-100bb-r5c3-s5` solve (Phase 10's honestly-locked result) means "this strategy can be beaten by 2.27 bb/hand *within this specific abstraction*," not "at a real table" — real-table exploitability could be higher (the abstraction itself is lossy on the betting-tree side, even though the 169-class card abstraction is lossless) or the figure could simply reflect under-convergence rather than an abstraction ceiling. `.agents/skills/poker_solver_conventions/SKILL.md` mandates the `abstraction_exploitability_mbb` name specifically so this qualification travels with the number wherever it's read, rather than getting silently dropped the first time someone copies it into a sentence.

---

## 5. Push/fold and ICM: exact, not abstracted — and one honest gap

`pushfold.py`/`icm.py` deliberately depend only on Phase 5 (the equity matrix), not on CFR or the betting tree — the jam-or-fold game is small enough (one decision each) to solve exactly by classical fictitious play (Robinson 1951) over the already-exact matrix, with no abstraction of any kind. Malmuth-Harville ICM is the standard choice (over Malmuth-Weitzman or Roberts) purely for comparability with every published table and competing tool, per the build plan's Appendix B item 6 — it's known to overstate short stacks' finishing probabilities, and that's accepted deliberately.

**One honest, stated gap**: no literal comparison against Miltersen & Sørensen's (2007) published exact jam/fold tables exists anywhere in this codebase. This development environment has no network access to independently verify against them, and fabricating an agreement claim without the reference in hand would be worse than not claiming it. The regression gate (`tests/poker/regression_test.py`, §7 below) substitutes the same structural facts Phase 9's own tests already established instead — near-100% jam/call below ~2bb, monotonicity across the full stack grid, call-tighter-than-jam from ~5bb on, and the hand-verified crossover below that (BB's pot-odds-only calling threshold is looser than SB's fold-equity-adjusted jamming threshold at the very shortest stacks) — real, independently-derivable evidence of correctness that needs no external table.

---

## 6. Risk of ruin: derivation and units

`src/poker/bankroll.py`'s `risk_of_ruin(bankroll_bb, win_rate_bb100, stdev_bb100) = exp(-2·B·w/s²)` is the classical closed-form ruin probability for a random walk approximated as Brownian motion with drift: a walk with per-step drift `μ` and variance `σ²` that starts at distance `B` from a lower absorbing barrier is ruined with probability `exp(-2μB/σ²)`. Substituting `w` (bb/100) and `s` (bb/100) for the per-*hundred-hand* drift and standard deviation, and `B` in bb, the implicit hands-to-100-hands conversion factor cancels inside the exponent — which is exactly why the compact form is correct as written and must never be "fixed" by reintroducing a hands-based normalisation (a comment to that effect sits directly in the function). The same closed form, with a downswing depth in place of the bankroll, gives the probability of ever enduring a downswing of that depth (`probability_of_downswing`) — mathematically the identical first-passage problem, not a separate derivation.

`required_bankroll_bb` is the closed-form inverse (solving for `B` given a target ruin probability), used both directly and inside `recommend_max_buyin`'s stake-sizing logic — the poker-shaped analogue of the blackjack area's half-Kelly: since a poker stake isn't continuously scalable the way a blackjack wager is, the equivalent conservatism is applied to the **risk target** instead, defaulting to holding risk of ruin at half the caller's stated tolerance.

The companion honesty check, `win_rate_confidence_interval` (`s / sqrt(n/100)`, then `±z·SE`), exists because a win rate without its confidence interval is not a measurement: a 1,000,000-hand sample at `s=100` bb/100 still carries a `±2` bb/100 interval, and most winning players' *true* win rates live inside that interval end to end. The Bankroll tab renders this as a standalone banner, not a buried metric card, for exactly this reason.

---

## 7. The regression gate

`py tests/poker/regression_test.py` (Phase 14) is the poker area's twin to `tests/regression_test.py` — kept genuinely separate (its own script, its own CI job) so a poker failure can never mask a blackjack one, or vice versa. Six checks, each against either a fresh recomputation or an already-reviewed locked artifact:

1. **Evaluator** — source-hash freshness against `evaluator_baseline.json`, the 7,462 distinct-value count, the five-card category counts (always), and the seven-card category counts — full `C(52,7)` enumeration outside `--fast` (numba-accelerated, ~83s per Phase 5's own measurement), a deterministic stride-sampled subset checked against known exact *proportions* (not counts, which a subsample can't reproduce) in `--fast`.
2. **Equity** — every anchor in `equity_baseline.json`, recomputed exactly via `equity_exact` and compared bit-for-bit (deterministic, so any drift is real).
3. **Kuhn / Leduc** — game value and full frequency structure against the analytic constants (Kuhn) and the sequence-form LP (Leduc), reusing Phase 8's own `test_toy_games.py` check functions directly.
4. **Preflop** — every shipped strategy's solver-hash freshness and `abstraction_exploitability_mbb` against `preflop_baseline.json`. This does **not** re-solve from scratch (a real MCCFR solve of the plan's own 100bb example costs on the order of 30 minutes — an unreasonable CI cost); it only confirms the shipped artifact hasn't silently drifted from the specific solve that was reviewed and locked, the same relationship `edge_model_baseline.json` has to `scripts/run_sim_battery.py` on the blackjack side. `preflop_baseline.json` itself is a real Phase-10-era gap filled during Phase 14, not a fresh invention — Phase 10's own Files line named it as a deliverable, but Phase 10 (in an earlier session) only ever wrote the per-spec `data/poker/strategy/{spec}/preflop.json` files and never created the separate baseline file the plan called for.
5. **Push/fold** — the structural facts described in §5 above, in place of a published-table comparison this environment cannot perform.
6. **ICM** — the Appendix A.6 worked example plus the "marginal chip value falls monotonically with stack size" property identity.

`--fast` (used by the `poker-regression` job in `.github/workflows/regression.yml`, kept as a genuinely separate job from the blackjack `regression` job) runs the stride-sampled evaluator check instead of the full enumeration; every other check is already cheap enough to run in both modes. `--generate` / `--generate-spec <key>` re-lock `preflop_baseline.json` only, and only from whatever solve is *already shipped* under `data/poker/strategy/` — never by re-solving, mirroring exactly how the blackjack gate's `--generate-ruleset` re-locks from a fresh but cheap recomputation while `edge_model_baseline.json`'s far more expensive artifact stays out of its default path.

Per `.agents/coding-standards.md`'s Regression Gate Discipline (written for the blackjack engine, applied here identically): once a baseline is locked, moving it requires establishing the move as a correctness fix, recording before/after numbers in the build plan's tracking table, and a deliberate re-lock — never a blanket `--generate` that silently absorbs unrelated drift.

---

## 8. Known limitations, stated plainly

- **The real `hu-100bb-r5c3-s5` preflop solve is honestly under-converged.** 1,000,000 MCCFR iterations against ~1.34 million realised infosets leaves `abstraction_exploitability_mbb` at 2,271.62 ± 44.43 — the plan's own sanity bar (AA opens ~100%, 72o opens ~0%) is not met by this solve. The user was asked and chose to lock this figure as-is rather than commit further compute of uncertain payoff; see Phase 10's tracking-table entry for the full reasoning and the options considered.
- **The Preflop and Trainer UI tabs are scoped to the BTN-open situation only** — no facing-a-raise/3-bet/4-bet action-history navigation. See Phase 13's tracking-table entry.
- **The Trainer scores by frequency-loss (percentage points), not bb EV** — `advisor.py`'s `Advice` has never computed or persisted per-action EV.
- **The Solver tab's exploitability "curve" is built from several independent bounded solves at increasing iteration counts**, not one continuously-updating solve — `/api/poker/solve` is synchronous and one-shot.
- **No live browser click-through of the web UI has been performed** — no browser-automation tool is available in this environment. Verification consisted of confirming every route serves correctly (both via Flask's test client and a live dev server), and programmatically cross-checking every DOM/CSS reference in the JS against the real HTML/CSS. A manual pass by a human in an actual browser remains an open item.
