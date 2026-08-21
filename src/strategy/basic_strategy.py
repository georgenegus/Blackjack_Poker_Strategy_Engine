"""Runtime basic-strategy lookup: given an actual player Hand, the dealer's
upcard, and a RuleSet, resolves the solved grid's cell into a concrete Action.

Rather than string-parsing the D/Ds/Rh/Rs/Rp chart notation and applying
fallback rules, this reads the cell's own ev_by_action dict directly, filters
it down to whatever is ACTUALLY legal for this specific runtime hand -- double
and surrender are first-action-only, and a post-split hand can only double if
rules.double_after_split -- and takes the argmax over just those candidates.
The D/Ds/Rh/Rs/Rp code is still returned (Advice.code) for display, but is
never parsed to make the decision.
"""

from dataclasses import dataclass
from typing import Dict, FrozenSet

from src.engine.cards import Card, HARD_VALUE
from src.engine.game import Action
from src.engine.hand import Hand
from src.engine.rules import RuleSet
from src.engine.shoe import Shoe
from src.strategy.grid_builder import PAIR_RANKS, solve_grid_cached

_ACTION_FOR_KEY = {"S": Action.STAND, "H": Action.HIT, "D": Action.DOUBLE, "R": Action.SURRENDER, "P": Action.SPLIT}
_KEY_FOR_ACTION = {v: k for k, v in _ACTION_FOR_KEY.items()}


@dataclass
class Advice:
    action: Action
    code: str                    # raw chart notation, e.g. "Rh", "Ds", "P" -- for display only
    ev_by_action: Dict[str, float]
    margin: float
    is_first_action: bool


def _card_value(card: Card) -> int:
    return HARD_VALUE[card.bucket]


def advise(hand: Hand, upcard: Card, rules: RuleSet) -> Advice:
    grid = solve_grid_cached(rules)
    upcard_value = _card_value(upcard)
    first_action = len(hand.cards) == 2
    is_pair = hand.is_pair if rules.split_by_value else hand.is_pair_exact

    if first_action and is_pair:
        rank_char = PAIR_RANKS[hand.cards[0].bucket]
        cell = grid["pairs"][f"{rank_char}{rank_char}v{upcard_value}"]
    elif hand.is_soft:
        total = max(13, min(20, hand.total))
        cell = grid["soft"][f"{total}v{upcard_value}"]
    else:
        total = max(5, min(20, hand.total))
        cell = grid["hard"][f"{total}v{upcard_value}"]

    # Double and surrender are first-action-only; a post-split hand additionally
    # needs rules.double_after_split to double at all. Neither restriction is part
    # of a (total, upcard) cell's own identity, so it's applied here, not baked
    # into the cached grid.
    double_legal = first_action and not (hand.from_split and not rules.double_after_split)
    surrender_legal = first_action and not hand.from_split

    candidates = {"S": cell.ev_by_action["S"], "H": cell.ev_by_action["H"]}
    if "D" in cell.ev_by_action and double_legal:
        candidates["D"] = cell.ev_by_action["D"]
    if "R" in cell.ev_by_action and surrender_legal:
        candidates["R"] = cell.ev_by_action["R"]
    if "P" in cell.ev_by_action and first_action:
        candidates["P"] = cell.ev_by_action["P"]

    best_key = max(candidates, key=candidates.get)
    return Advice(
        action=_ACTION_FOR_KEY[best_key],
        code=cell.action,
        ev_by_action=cell.ev_by_action,
        margin=cell.margin,
        is_first_action=first_action,
    )


def strategy_decide_fn(hand: Hand, upcard: Card, shoe: Shoe, rules: RuleSet, legal: FrozenSet[Action]) -> Action:
    """A game.py-compatible decide_fn (see game.py's DecideFn) that plays basic
    strategy. advise() alone can recommend an action that's illegal in the
    ACTUAL round (e.g. SPLIT after resplit_to hands already exist -- Hand
    carries only its own first-action/from_split state, not the round-wide
    split count game.py tracks internally) -- when that happens, this falls
    back to the best-EV action among what `legal` (computed by game.py itself)
    actually allows, using the same cell.ev_by_action the primary advice came
    from rather than guessing again from scratch.
    """
    advice = advise(hand, upcard, rules)
    if advice.action in legal:
        return advice.action
    candidates = {
        a: advice.ev_by_action[_KEY_FOR_ACTION[a]] for a in legal if _KEY_FOR_ACTION[a] in advice.ev_by_action
    }
    return max(candidates, key=candidates.get)
