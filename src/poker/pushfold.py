"""Phase 9: heads-up jam-or-fold equilibrium. See
markdowns/poker/poker_build_plan_v1.md Phase 9.

At short effective stacks the game collapses to one decision each: the small
blind either shoves all-in or folds; the big blind, facing a jam, either
calls or folds. This is small enough to solve EXACTLY over the already-
locked 169x169 preflop equity matrix (Phase 3) with no abstraction, no
betting tree, and no CFR -- deliberately wired to depend only on Phase 5
(equity_exact -> the matrix), not on Phase 8's CFR/toy-game machinery, per
the build plan's own reasoning: it is the cheapest available proof that the
equity layer is sound in a genuinely strategic (not just arithmetic)
setting.

Weighting convention (documented once, matches how the plan phrases this
phase: "exact up to the equity matrix"): a class's prior likelihood is its
raw combo count (6 pairs / 4 suited / 12 offsuit, summing to 1,326), NOT
re-derived per opposing hand to account for card removal between the two
hands' own combos -- the matrix entries themselves are already exact,
combo-weighted equities for each class pair, so the only remaining
approximation is treating the OTHER 168 classes' relative likelihoods as
unperturbed by which specific class is being evaluated. This is the same
simplification real push/fold solvers (ICMIZER, HRC, SnapShove, ...) use;
Appendix B item 6 discusses the general accuracy/cost tradeoff this project
takes elsewhere with "equity realisation".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from src.poker.icm import icm_equity
from src.poker.ranges import CLASS_LABELS, Range, hand_classes
from src.poker.spec import GameSpec

MATRIX_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "poker" / "equity" / "preflop_169x169.npz"

TOTAL_COMBOS = 1326.0

_matrix_cache: dict | None = None


def _load_matrix() -> dict:
    global _matrix_cache
    if _matrix_cache is not None:
        return _matrix_cache
    if not MATRIX_PATH.exists():
        raise FileNotFoundError(
            f"Preflop equity matrix not found at {MATRIX_PATH}. Run "
            "`py scripts/poker/build_preflop_equity.py` first."
        )
    data = np.load(MATRIX_PATH, allow_pickle=True)
    labels = list(data["labels"])
    _matrix_cache = {
        "matrix": data["matrix"],
        "labels": labels,
        "index": {label: i for i, label in enumerate(labels)},
        "class_weight": {label: len(combos) for label, combos in zip(*hand_classes())},
    }
    return _matrix_cache


def _fold_payoffs(spec: GameSpec) -> tuple[float, float, float]:
    """(sb_fold_cost, bb_fold_win_for_sb, ante_per_player). sb_fold_cost is
    what SB loses by folding (their sb + their own ante, if any);
    bb_fold_win_for_sb is what SB wins if BB folds to a jam (BB's bb + BB's
    own ante contribution)."""
    ante_sb = 0.0 if spec.bb_ante else spec.ante_bb
    ante_bb_extra = spec.ante_bb if spec.bb_ante else 0.0
    ante_bb_total = (0.0 if spec.bb_ante else spec.ante_bb) + ante_bb_extra
    sb_fold_cost = spec.sb + ante_sb
    bb_fold_win_for_sb = spec.bb + ante_bb_total
    return sb_fold_cost, bb_fold_win_for_sb, ante_sb


def _sb_jam_ev(label: str, call_weights: dict[str, float], stack_bb: float, m: dict) -> float:
    """SB's EV (bb) of jamming with `label`, given BB's calling-range
    weights {class: weight in [0,1]}."""
    i = m["index"][label]
    matrix = m["matrix"]
    ev = 0.0
    for b, j in m["index"].items():
        cw = m["class_weight"][b]
        call_w = call_weights.get(b, 0.0)
        eq = matrix[i, j]
        payoff_if_called = stack_bb * (2.0 * eq - 1.0)
        ev += cw * (call_w * payoff_if_called + (1.0 - call_w) * 1.0)
    return ev / TOTAL_COMBOS


def _bb_call_ev(label: str, jam_weights: dict[str, float], stack_bb: float, m: dict) -> float | None:
    """BB's EV (bb) of calling with `label`, given SB's jamming-range
    weights. None if SB never jams (the comparison is then moot)."""
    j = m["index"][label]
    matrix = m["matrix"]
    weighted_eq_sum = 0.0
    total_w = 0.0
    for h, i in m["index"].items():
        jw = jam_weights.get(h, 0.0)
        if jw <= 0.0:
            continue
        cw = m["class_weight"][h]
        eq_b = 1.0 - matrix[i, j]
        weighted_eq_sum += cw * jw * eq_b
        total_w += cw * jw
    if total_w <= 0.0:
        return None
    avg_eq_b = weighted_eq_sum / total_w
    return stack_bb * (2.0 * avg_eq_b - 1.0)


@dataclass
class PushFoldResult:
    stack_bb: float
    jam: dict = field(repr=False)  # class label -> weight in [0,1]
    call: dict = field(repr=False)
    iterations: int

    @property
    def jam_range(self) -> Range:
        return Range.from_combos(
            {c: w for label, w in self.jam.items() if w > 0 for c in _class_combos(label)}
        )

    @property
    def call_range(self) -> Range:
        return Range.from_combos(
            {c: w for label, w in self.call.items() if w > 0 for c in _class_combos(label)}
        )

    @property
    def jam_pct(self) -> float:
        return sum(w * _class_weight(label) for label, w in self.jam.items()) / TOTAL_COMBOS * 100.0

    @property
    def call_pct(self) -> float:
        return sum(w * _class_weight(label) for label, w in self.call.items()) / TOTAL_COMBOS * 100.0


_label_combos_cache: dict | None = None


def _class_combos(label: str):
    global _label_combos_cache
    if _label_combos_cache is None:
        labels, groups = hand_classes()
        _label_combos_cache = dict(zip(labels, groups))
    return _label_combos_cache[label]


def _class_weight(label: str) -> int:
    return len(_class_combos(label))


def solve_pushfold(spec: GameSpec, iterations: int = 300) -> PushFoldResult:
    """Solve the heads-up jam-or-fold equilibrium at `spec.stack_bb` by
    classical fictitious play (Robinson 1951): each iteration, EACH player
    plays a PURE best response to the OTHER's TIME-AVERAGE strategy so far
    (not to the other's single most recent move -- that variant does not
    converge here, see below), and the reported jam/call ranges are the
    TIME-AVERAGE of both players' decisions across all iterations, not the
    final iteration's raw (still-oscillating) pure response.

    An earlier version of this function used damped, iterate-to-iterate
    updates and checked whether THAT iterate stopped changing -- caught
    during this phase's own testing as never converging (jam/call class
    counts kept cycling between ~65 and ~170 over 200 iterations, never
    settling). The raw pure best-response dynamic genuinely does not
    converge here (a known feature of fictitious play on games with a hard
    decision threshold); what Robinson's theorem actually guarantees is
    convergence of the TIME-AVERAGE for zero-sum games -- exactly the same
    "current strategy oscillates, average strategy converges" property CFR
    itself is built around (see src/poker/cfr.py's own module docstring).
    Treating the raw iterate as the answer was the bug, not the algorithm.
    """
    m = _load_matrix()
    sb_fold_cost, _bb_fold_win, _ante_sb = _fold_payoffs(spec)
    # BB's cost of folding to a jam is exactly what BB has posted: their bb plus
    # their own ante contribution (spec.ante_bb, in either ante mode -- per-player
    # mode has BB posting it directly, bb_ante mode has BB posting the WHOLE ante,
    # which is the same spec.ante_bb value either way).
    bb_fold_cost = spec.bb + spec.ante_bb

    jam_avg = {label: 0.5 for label in CLASS_LABELS}
    call_avg = {label: 0.5 for label in CLASS_LABELS}
    jam_sum = {label: 0.0 for label in CLASS_LABELS}
    call_sum = {label: 0.0 for label in CLASS_LABELS}

    for t in range(1, iterations + 1):
        jam_pure = {
            label: (1.0 if _sb_jam_ev(label, call_avg, spec.stack_bb, m) > -sb_fold_cost else 0.0)
            for label in CLASS_LABELS
        }
        call_pure = {}
        for label in CLASS_LABELS:
            ev_call = _bb_call_ev(label, jam_avg, spec.stack_bb, m)
            call_pure[label] = 1.0 if (ev_call is not None and ev_call > -bb_fold_cost) else 0.0

        for label in CLASS_LABELS:
            jam_sum[label] += jam_pure[label]
            call_sum[label] += call_pure[label]
        jam_avg = {label: jam_sum[label] / t for label in CLASS_LABELS}
        call_avg = {label: call_sum[label] / t for label in CLASS_LABELS}

    return PushFoldResult(spec.stack_bb, jam_avg, call_avg, iterations)


def build_pushfold_grid(
    spec_template: GameSpec | None = None, stacks: tuple[float, ...] | None = None
) -> dict[float, PushFoldResult]:
    """A jam range and call range for every effective stack depth on the
    plan's specified grid: 1-25bb in 0.5bb steps (49 depths)."""
    if spec_template is None:
        spec_template = GameSpec()
    if stacks is None:
        stacks = tuple(1.0 + 0.5 * i for i in range(49))  # 1.0, 1.5, ..., 25.0

    results = {}
    for stack in stacks:
        spec = GameSpec(
            num_players=spec_template.num_players,
            stack_bb=stack,
            sb=spec_template.sb,
            bb=spec_template.bb,
            ante_bb=spec_template.ante_bb,
            bb_ante=spec_template.bb_ante,
            rake_pct=spec_template.rake_pct,
            rake_cap_bb=spec_template.rake_cap_bb,
            no_flop_no_drop=spec_template.no_flop_no_drop,
            bet_sizes=spec_template.bet_sizes,
            allow_allin=spec_template.allow_allin,
            raise_cap=spec_template.raise_cap,
            variant=spec_template.variant,
        )
        results[stack] = solve_pushfold(spec)
    return results


# ---------------------------------------------------------------------------
# ICM-adjusted push/fold
# ---------------------------------------------------------------------------


def solve_pushfold_icm(
    stacks_bb: list[float],
    payouts: list[float],
    shover: int,
    caller: int,
    sb: float = 0.5,
    bb: float = 1.0,
    iterations: int = 300,
) -> PushFoldResult:
    """ICM-adjusted jam/call ranges for a shove between `stacks_bb[shover]`
    and `stacks_bb[caller]` at a table of `len(stacks_bb)` players
    competing for `payouts`, replacing chip-EV comparisons with ICM $EV
    comparisons -- the same fictitious-play structure as solve_pushfold,
    labelled separately (a distinct function, a distinct PushFoldResult)
    rather than silently mixed into the chip-EV ranges, per the build
    plan's explicit requirement.

    Other players at the table are NOT modelled as acting themselves
    (their stacks matter to the ICM math -- risking against a leader when
    short stacks are still live is scarier in $EV terms than in chip-EV
    terms -- but they do not fold/call anything here); this solves the
    shover/caller subgame only, holding everyone else's stacks fixed. That
    is the standard scope for "ICM push/fold" tools.

    Exploits that ICM equity depends only on CHIP AMOUNTS, never on which
    hand is held: the four possible post-confrontation ICM states (fold,
    called-and-won, called-and-lost, and the do-nothing baseline) are each
    computed with icm_equity() exactly ONCE per call, not once per one of
    the 169 hand classes -- reusing chip-EV push/fold's O(169) per-class
    loop structure, just substituting these four precomputed $EV numbers
    in place of raw chip deltas.
    """
    m = _load_matrix()
    effective = min(stacks_bb[shover], stacks_bb[caller])

    def icm_for(shover_delta: float) -> float:
        s = list(stacks_bb)
        s[shover] += shover_delta
        s[caller] -= shover_delta
        return icm_equity(s, payouts)[shover]

    equity_fold = icm_for(-sb)
    equity_bb_folds = icm_for(bb)
    equity_win = icm_for(effective)
    equity_lose = icm_for(-effective)

    def sb_jam_icm_ev(label: str, call_weights: dict[str, float]) -> float:
        i = m["index"][label]
        matrix = m["matrix"]
        ev = 0.0
        for b, j in m["index"].items():
            cw = m["class_weight"][b]
            call_w = call_weights.get(b, 0.0)
            eq = matrix[i, j]
            showdown_icm = eq * equity_win + (1.0 - eq) * equity_lose
            ev += cw * (call_w * showdown_icm + (1.0 - call_w) * equity_bb_folds)
        return ev / TOTAL_COMBOS

    def bb_call_icm_ev(label: str, jam_weights: dict[str, float]) -> float | None:
        j = m["index"][label]
        matrix = m["matrix"]
        weighted_sum, total_w = 0.0, 0.0
        for h, i in m["index"].items():
            jw = jam_weights.get(h, 0.0)
            if jw <= 0.0:
                continue
            cw = m["class_weight"][h]
            eq_b = 1.0 - matrix[i, j]
            weighted_sum += cw * jw * eq_b
            total_w += cw * jw
        if total_w <= 0.0:
            return None
        avg_eq_b = weighted_sum / total_w
        s = list(stacks_bb)
        s[caller] += effective
        s[shover] -= effective
        equity_caller_win = icm_equity(s, payouts)[caller]
        s2 = list(stacks_bb)
        s2[caller] -= effective
        s2[shover] += effective
        equity_caller_lose = icm_equity(s2, payouts)[caller]
        return avg_eq_b * equity_caller_win + (1.0 - avg_eq_b) * equity_caller_lose

    equity_bb_fold_for_caller = icm_equity(
        [s - bb if idx == caller else (s + bb if idx == shover else s) for idx, s in enumerate(stacks_bb)], payouts
    )[caller]

    jam_avg = {label: 0.5 for label in CLASS_LABELS}
    call_avg = {label: 0.5 for label in CLASS_LABELS}
    jam_sum = {label: 0.0 for label in CLASS_LABELS}
    call_sum = {label: 0.0 for label in CLASS_LABELS}

    for t in range(1, iterations + 1):
        jam_pure = {label: (1.0 if sb_jam_icm_ev(label, call_avg) > equity_fold else 0.0) for label in CLASS_LABELS}
        call_pure = {}
        for label in CLASS_LABELS:
            ev_call = bb_call_icm_ev(label, jam_avg)
            call_pure[label] = 1.0 if (ev_call is not None and ev_call > equity_bb_fold_for_caller) else 0.0

        for label in CLASS_LABELS:
            jam_sum[label] += jam_pure[label]
            call_sum[label] += call_pure[label]
        jam_avg = {label: jam_sum[label] / t for label in CLASS_LABELS}
        call_avg = {label: call_sum[label] / t for label in CLASS_LABELS}

    return PushFoldResult(effective, jam_avg, call_avg, iterations)
