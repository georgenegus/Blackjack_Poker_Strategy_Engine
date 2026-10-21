"""Phase 7: deviations.advise() -- basic strategy plus a count-triggered
deviation, with the EV gain attached so the UI can show *why*. See
index_builder.py for how indices are derived and cached, and
.agents/coding-standards.md's True-Count Rounding Convention: playing decisions
round to "nearest", distinct from betting's "floor".

In dual-system mode (build plan Phase 6 Step 3), this must always be called with
the PLAYING-system counter -- never the betting counter's TC, since indices are
derived per-system and are not interchangeable (an Omega II TC of +3 does not
mean what a Hi-Lo TC of +3 means).
"""

from dataclasses import dataclass
from typing import FrozenSet, Optional

from src.counting.counter import Counter
from src.engine.cards import Card, HARD_VALUE
from src.engine.game import Action, DecideFn
from src.engine.hand import Hand
from src.engine.rules import RuleSet
from src.engine.shoe import Shoe
from src.strategy.basic_strategy import advise as basic_advise
from src.strategy.basic_strategy import strategy_decide_fn as basic_decide_fn
from src.strategy.grid_builder import PAIR_RANKS
from src.strategy.index_builder import TC_SWEEP_MAX, implied_composition, insurance_correct, solve_indices_cached

_ACTION_FOR_KEY = {"S": Action.STAND, "H": Action.HIT, "D": Action.DOUBLE, "R": Action.SURRENDER, "P": Action.SPLIT}
_KEY_FOR_ACTION = {v: k for k, v in _ACTION_FOR_KEY.items()}


def should_take_insurance(counter: Counter) -> bool:
    """Insurance is a standalone bet on ten-density, not a grid cell (build plan
    Phase 7 Step 4) -- evaluated directly against the counter's ACTUAL current
    composition (exact and free) rather than a precomputed TC threshold like
    index_builder.insurance_index(), which exists only as a reference value to
    validate against, not something this looks up at runtime."""
    comp = implied_composition(counter.system, counter.decks_remaining, counter.running_count)
    return insurance_correct(comp)


@dataclass
class DeviationAdvice:
    action: Action
    code: str                          # basic-strategy display code, unchanged even when deviating
    is_deviation: bool
    deviation_reason: Optional[str]    # e.g. "TC >= +3", None when not deviating
    basic_action: Action
    ev_gain: float                     # deviated EV - basic EV at the counter's ACTUAL composition; 0.0 if not deviating
    true_count: float
    running_count: float


def _cell_key_for(hand: Hand, upcard_value: int, rules: RuleSet) -> Optional[str]:
    """Indices only cover first-action 2-card hands -- matches the Illustrious 18
    / Fab 4's own scope. Anything else (post-split, 3+ cards) falls back to plain
    basic strategy: returning None here means "no index to consult", not an error."""
    if len(hand.cards) != 2 or hand.from_split:
        return None
    is_pair = hand.is_pair if rules.split_by_value else hand.is_pair_exact
    if is_pair:
        rank_char = PAIR_RANKS[hand.cards[0].bucket]
        return f"{rank_char}{rank_char}v{upcard_value}"
    return f"{hand.total}v{upcard_value}"


def advise(hand: Hand, upcard: Card, counter: Counter, rules: RuleSet) -> DeviationAdvice:
    upcard_value = HARD_VALUE[upcard.bucket]
    basic = basic_advise(hand, upcard, rules)
    tc = counter.true_count(rounding="nearest")

    no_deviation = DeviationAdvice(
        action=basic.action, code=basic.code, is_deviation=False, deviation_reason=None,
        basic_action=basic.action, ev_gain=0.0, true_count=tc, running_count=counter.running_count,
    )

    cell_key = _cell_key_for(hand, upcard_value, rules)
    if cell_key is None:
        return no_deviation

    # "15 vs 10" (etc.) can carry two independent questions: the traditional
    # Illustrious-18-style S/H/D/P one, and the Fab 4's own surrender-vs-not one --
    # but three of the four Fab 4 cells (14v10, 15v9, 15vA) have ONLY a surrender
    # entry, since basic strategy already hits them at a neutral shoe (there's no
    # interesting S-vs-H question to ask). So this can't be decided from what
    # basic strategy currently does -- it has to check which entry actually
    # exists: prefer "surrender" whenever surrender is legal and derived for this
    # cell (surrender is checked before stand/hit/double in real play too -- see
    # ev_solver_conventions/SKILL.md), falling back to "primary" otherwise.
    named = solve_indices_cached(counter.system, counter.num_decks, rules)
    surrender_legal = len(hand.cards) == 2 and not hand.from_split and rules.surrender != "none"

    idx = named.get(f"{cell_key}:surrender") if surrender_legal else None
    if idx is None:
        idx = named.get(f"{cell_key}:primary")
    if idx is None:
        return no_deviation

    reason = None
    if idx.positive_index is not None and tc >= idx.positive_index:
        reason = f"TC >= {idx.positive_index:+d}"
    elif idx.negative_index is not None and tc <= idx.negative_index:
        reason = f"TC <= {idx.negative_index:+d}"
    if reason is None:
        return no_deviation

    # The index is only a GATE for whether TC has crossed a point where the
    # restricted (S/H/D/P, or S/H/R) comparison flips -- it doesn't by itself
    # prove that's the true best action once every legal action is considered
    # together. 16 vs 10 is the clean example: basic strategy there is already
    # Surrender, and "primary"'s own flip (stand beats hit) can happen at a TC
    # where surrender STILL beats both -- restricted comparisons don't compare
    # against each other. So once gated, the actual recommendation always comes
    # from the FULL ev_by_action table AT THIS TC, looked up from idx.ev_table
    # (captured across the whole -10..+10 sweep when the index was derived) --
    # never a fresh live re-solve. A live composition is essentially unique per
    # hand (the counter's exact decks_remaining/running_count basically never
    # repeats), so it gets zero benefit from ev_solver.py's own memoization and
    # was the actual bottleneck found running Phase 8's simulator battery: one
    # gate tripping (e.g. "11 vs A" at any TC>=+1, true for roughly half of all
    # counts) meant a full uncached recursive re-solve on every matching hand.
    # This trades the counter's exact fractional decks_remaining for the
    # canonical decks_remaining=num_decks reference the table was built at,
    # clamped to the swept +/-10 TC range -- extrapolating past that range is
    # already flagged elsewhere (see edge_model.py's own "don't trust past
    # TC+/-6" framing), and the TC+/-10 action is a reasonable stand-in beyond it.
    clamped_tc = max(-TC_SWEEP_MAX, min(TC_SWEEP_MAX, tc))
    ev_by_action = idx.ev_table[clamped_tc]

    legal_keys = set(ev_by_action)
    if not surrender_legal:
        legal_keys.discard("R")
    best_key = max(legal_keys, key=lambda k: ev_by_action[k])
    basic_key = _KEY_FOR_ACTION[basic.action]

    if best_key == basic_key:
        return no_deviation

    return DeviationAdvice(
        action=_ACTION_FOR_KEY[best_key],
        code=basic.code,
        is_deviation=True,
        deviation_reason=reason,
        basic_action=basic.action,
        ev_gain=ev_by_action[best_key] - ev_by_action[basic_key],
        true_count=tc,
        running_count=counter.running_count,
    )


def make_decide_fn(counter: Counter) -> DecideFn:
    """A game.py-compatible decide_fn (Phase 8's simulator) bound to one live
    Counter, using advise()'s count-aware recommendation. advise() can recommend
    something the ACTUAL round doesn't currently allow (e.g. SPLIT past
    resplit_to) exactly like basic_strategy.advise() can -- fall back to
    strategy_decide_fn's own legal-action handling rather than duplicating it."""

    def decide_fn(hand: Hand, upcard: Card, shoe: Shoe, rules: RuleSet, legal: FrozenSet[Action]) -> Action:
        advice = advise(hand, upcard, counter, rules)
        if advice.action in legal:
            return advice.action
        return basic_decide_fn(hand, upcard, shoe, rules, legal)

    return decide_fn
