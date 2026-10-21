"""Phase 7: derived count indices vs the Illustrious 18 / Fab 4 / insurance,
within the build plan's documented +/-1 true-count tolerance -- published tables
themselves disagree by this much across different count-to-composition mappings,
so +/-1 is an honest gate, not a weakened one. Any cell off by >=2 is a real bug.
"""

import pytest

from src.counting.counter import Counter
from src.counting.systems import HI_LO
from src.engine.cards import Card
from src.engine.game import Action
from src.engine.hand import Hand
from src.engine.rules import RuleSet
from src.strategy import deviations
from src.strategy.index_builder import (
    FAB_4,
    ILLUSTRIOUS_18,
    insurance_index,
    solve_indices_cached,
)

RULES = RuleSet(num_decks=6, dealer_hits_soft_17=False, double_after_split=True, surrender="late")

ILLUSTRIOUS_18_PUBLISHED = {
    "16v10": 0, "15v10": 4, "TTv5": 5, "TTv6": 4, "10v10": 4, "12v3": 2,
    "12v2": 3, "11vA": 1, "9v2": 1, "10vA": 4, "9v7": 3, "16v9": 5,
    "13v2": -1, "12v4": 0, "12v5": -2, "12v6": -1, "13v3": -2,
}
FAB_4_PUBLISHED = {"14v10": 3, "15v10": 0, "15v9": 2, "15vA": 1}
TOLERANCE = 1


@pytest.fixture(scope="module")
def named_indices():
    return solve_indices_cached(HI_LO, num_decks=6, rules=RULES)


def _derived_value(idx):
    """Whichever direction actually found a flip. A published index of 0 can
    surface on either side of this module's TC=0 baseline (the baseline is, by
    construction, never itself reported as an index) -- see index_builder.py's
    module docstring."""
    return idx.positive_index if idx.positive_index is not None else idx.negative_index


@pytest.mark.parametrize("kind,upcard,cell_key", ILLUSTRIOUS_18)
def test_illustrious_18(named_indices, kind, upcard, cell_key):
    idx = named_indices[f"{cell_key}:primary"]
    derived = _derived_value(idx)
    published = ILLUSTRIOUS_18_PUBLISHED[cell_key]
    assert derived is not None, f"{cell_key}: no flip found in +/-10 TC"
    assert abs(derived - published) <= TOLERANCE, (
        f"{cell_key}: derived {derived} vs published {published} (baseline={idx.baseline_action}, "
        f"+{idx.positive_index}->{idx.positive_action}, {idx.negative_index}->{idx.negative_action})"
    )


@pytest.mark.parametrize("kind,upcard,cell_key", FAB_4)
def test_fab_4(named_indices, kind, upcard, cell_key):
    idx = named_indices[f"{cell_key}:surrender"]
    derived = _derived_value(idx)
    published = FAB_4_PUBLISHED[cell_key]
    # The neutral-shoe baseline (S/H/R argmax) is "R" only for 15v10 -- basic strategy
    # already surrenders that one at TC=0. For the other three, baseline is "H": basic
    # strategy does NOT surrender at a neutral shoe, and the count flips it INTO
    # surrender as it rises -- that asymmetry is exactly why these are worth
    # memorizing. Either way, the flip itself (found regardless of which direction
    # or which baseline) is what's being validated here.
    assert derived is not None, f"{cell_key}: no flip found in +/-10 TC"
    assert abs(derived - published) <= TOLERANCE, (
        f"{cell_key}: derived {derived} vs published {published} (baseline={idx.baseline_action}, "
        f"+{idx.positive_index}->{idx.positive_action}, {idx.negative_index}->{idx.negative_action})"
    )


def test_insurance_triggers_near_tc_plus_3():
    idx = insurance_index(HI_LO, num_decks=6)
    assert idx is not None
    assert abs(idx - 3) <= TOLERANCE


# --- deviations.advise() runtime wiring --------------------------------------------------
# named_indices fixture above already forces solve_indices_cached to have run, so these
# reuse its cached result rather than re-deriving.

def _counter_at(running_count: float, num_decks: int = 6) -> Counter:
    counter = Counter(HI_LO, num_decks)
    counter.running_count = running_count
    counter.dealt = 0  # decks_remaining stays exactly num_decks -- the canonical reference
    return counter


def test_advise_no_deviation_far_from_any_named_cell(named_indices):
    hand = Hand(["4", "3"])  # hard 7 -- nowhere near any Illustrious 18 / Fab 4 cell
    upcard = Card(rank="5", suit=None)
    advice = deviations.advise(hand, upcard, _counter_at(30), RULES)  # TC +5
    assert not advice.is_deviation
    assert advice.ev_gain == 0.0
    assert advice.action == advice.basic_action


def test_advise_12v3_no_deviation_at_negative_count(named_indices):
    # 12 vs 3 (not 16 vs 10) deliberately: 16v10 stays surrender-dominant across a
    # much wider range than "primary"'s own S-vs-H flip alone would suggest (see
    # advise()'s docstring comment on this), so it's a poor choice for pinning
    # down a specific expected action/basic_action pair. 12 is never surrendered
    # regardless of count, avoiding that confound entirely.
    hand = Hand(["9", "3"])  # hard 12
    upcard = Card(rank="3", suit=None)
    advice = deviations.advise(hand, upcard, _counter_at(-30), RULES)  # TC -5
    assert advice.basic_action == Action.HIT
    assert not advice.is_deviation
    assert advice.action == Action.HIT


def test_advise_12v3_deviates_to_stand_at_positive_count(named_indices):
    hand = Hand(["9", "3"])  # hard 12
    upcard = Card(rank="3", suit=None)
    advice = deviations.advise(hand, upcard, _counter_at(30), RULES)  # TC +5, past published +2
    assert advice.basic_action == Action.HIT
    assert advice.is_deviation
    assert advice.action == Action.STAND
    assert advice.ev_gain > 0
    assert advice.deviation_reason is not None


def test_advise_16v10_never_worse_than_basic_strategy(named_indices):
    """16 vs 10 with late surrender: basic strategy is ALREADY Surrender (not Hit),
    so this only checks the general safety property -- whatever advise() ends up
    recommending, it must never be worse than just taking basic strategy's own
    action, at both a very negative and a very positive count."""
    hand = Hand(["9", "7"])  # hard 16
    upcard = Card(rank="T", suit=None)
    for rc in (-30, 30):
        advice = deviations.advise(hand, upcard, _counter_at(rc), RULES)
        assert advice.basic_action == Action.SURRENDER
        assert advice.ev_gain >= 0


def test_advise_14v10_surrender_only_entry_still_fires(named_indices):
    """Regression test: 14v10 has ONLY a ':surrender' table entry (basic strategy
    hits it at a neutral shoe, so there's no interesting stand-vs-hit question),
    which the runtime selection logic must still find -- it can't be keyed off
    whatever basic strategy's neutral-shoe action happens to be."""
    hand = Hand(["9", "5"])  # hard 14
    upcard = Card(rank="T", suit=None)

    low = deviations.advise(hand, upcard, _counter_at(0), RULES)  # TC 0
    assert low.basic_action == Action.HIT
    assert not low.is_deviation

    high = deviations.advise(hand, upcard, _counter_at(30), RULES)  # TC +5, past published +3
    assert high.is_deviation
    assert high.action == Action.SURRENDER
    assert high.ev_gain > 0


def test_advise_post_split_hand_never_deviates(named_indices):
    hand = Hand(["9", "7"], from_split=True)  # would be hard 16 vs 10, but post-split
    upcard = Card(rank="T", suit=None)
    advice = deviations.advise(hand, upcard, _counter_at(30), RULES)
    assert not advice.is_deviation


# --- should_take_insurance() -- standalone, no grid cell or cached index involved --------

def test_should_take_insurance_false_at_neutral_shoe():
    assert deviations.should_take_insurance(_counter_at(0)) is False


def test_should_take_insurance_true_well_past_the_index():
    assert deviations.should_take_insurance(_counter_at(36)) is True  # TC +6, published index +3
