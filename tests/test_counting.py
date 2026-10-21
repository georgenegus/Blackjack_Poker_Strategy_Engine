"""Phase 6: count arithmetic, IRC, true-count rounding.

See .agents/skills/counting_systems_conventions/SKILL.md for the invariants this
locks in: a balanced system must return exactly to its IRC after a full shoe is
dealt (the definition of "balanced"), and the floor/nearest/truncate rounding
split must be explicit and testable independently.
"""

import pytest

from src.counting.counter import Counter
from src.counting.systems import (
    ALL_SYSTEMS,
    HI_LO,
    HI_OPT_I,
    HI_OPT_II,
    KO,
    OMEGA_II,
    RED_7,
    ZEN,
)
from src.engine.cards import Card
from src.engine.shoe import Shoe

BALANCED_SYSTEMS = (HI_LO, HI_OPT_I, HI_OPT_II, OMEGA_II, ZEN)


def _deal_full_shoe(system, num_decks):
    shoe = Shoe(num_decks)
    counter = Counter(system, num_decks)
    while shoe.remaining > 0:
        counter.see(shoe.deal())
    return counter


# --- Balance invariant: a full shoe returns each system to a fixed, predictable value ----

@pytest.mark.parametrize("system", BALANCED_SYSTEMS, ids=lambda s: s.name)
@pytest.mark.parametrize("num_decks", [1, 2, 6])
def test_balanced_systems_return_to_zero_after_full_shoe(system, num_decks):
    counter = _deal_full_shoe(system, num_decks)
    assert counter.running_count == pytest.approx(0.0)
    assert system.irc(num_decks) == 0.0


@pytest.mark.parametrize("num_decks", [1, 2, 6, 8])
def test_ko_irc_and_full_shoe_value(num_decks):
    counter = Counter(KO, num_decks)
    assert counter.running_count == -4 * (num_decks - 1)
    counter = _deal_full_shoe(KO, num_decks)
    # KO's per-deck tag sum is +4 (see systems.py), so a fully-dealt shoe always ends
    # at the pivot (+4) regardless of deck count -- this IS the point of KO's design.
    assert counter.running_count == pytest.approx(4.0)


def test_ko_six_deck_matches_build_plan_worked_example():
    counter = Counter(KO, num_decks=6)
    assert counter.running_count == -20
    counter = _deal_full_shoe(KO, num_decks=6)
    assert counter.running_count == pytest.approx(4.0)


# --- Red 7: suit-dependent tag, so full-shoe balance must be checked on an explicitly ----
# --- constructed deck (Shoe.deal() assigns suit via an independent coin flip per card, ---
# --- not tracked composition -- see shoe.py -- so it is NOT guaranteed to deal exactly ---
# --- 2 red + 2 black 7s per deck) ---------------------------------------------------------

def _build_exact_deck():
    cards = []
    for rank in ["2", "3", "4", "5", "6", "8", "9", "T", "J", "Q", "K", "A"]:
        cards += [Card(rank=rank, suit=suit) for suit in ("S", "H", "D", "C")]
    cards += [Card(rank="7", suit="H"), Card(rank="7", suit="D"), Card(rank="7", suit="S"), Card(rank="7", suit="C")]
    assert len(cards) == 52
    return cards


def test_red_seven_tag_for_depends_on_suit_not_rank_alone():
    assert RED_7.tag_for(Card(rank="7", suit="H")) == 1.0   # red
    assert RED_7.tag_for(Card(rank="7", suit="D")) == 1.0   # red
    assert RED_7.tag_for(Card(rank="7", suit="S")) == 0.0   # black
    assert RED_7.tag_for(Card(rank="7", suit="C")) == 0.0   # black
    assert RED_7.tag_for(Card(rank="6", suit="S")) == 1.0   # unaffected by is_red_seven


@pytest.mark.parametrize("num_decks", [1, 2, 6])
def test_red_seven_irc_and_exact_deck_balance(num_decks):
    counter = Counter(RED_7, num_decks)
    assert counter.running_count == -2.0 * num_decks
    for _ in range(num_decks):
        for card in _build_exact_deck():
            counter.see(card)
    # Red 7's per-deck tag sum is +2 (2 red 7s at +1, 2 black 7s at 0, plus Hi-Lo's own
    # balance elsewhere), so an exactly-composed shoe returns it to 0 -- same endpoint
    # as a balanced system, just reached via a deliberately unbalanced IRC.
    assert counter.running_count == pytest.approx(0.0)


# --- Unbalanced systems must not expose true_count ---------------------------------------

@pytest.mark.parametrize("system", [KO, RED_7], ids=lambda s: s.name)
def test_unbalanced_systems_raise_on_true_count(system):
    counter = Counter(system, num_decks=6)
    with pytest.raises(ValueError):
        counter.true_count()


# --- True-count rounding: floor (betting) vs nearest (playing) vs truncate ---------------

def _counter_with_state(system, num_decks, running_count, dealt):
    counter = Counter(system, num_decks)
    counter.running_count = running_count
    counter.dealt = dealt
    return counter


def test_decks_remaining_floors_to_half_deck_resolution():
    # 6 decks = 312 cards; dealt=110 -> exact remaining = 202/52 = 3.8846...
    counter = _counter_with_state(HI_LO, num_decks=6, running_count=0, dealt=110)
    assert counter.decks_remaining_exact == pytest.approx(202 / 52)
    assert counter.decks_remaining == pytest.approx(3.5)


def test_true_count_rounding_negative_true_count():
    # decks_remaining=3.5 (see above); running_count=-8.05 -> raw true count = -2.3
    counter = _counter_with_state(HI_LO, num_decks=6, running_count=-8.05, dealt=110)
    assert counter.true_count(rounding="floor") == -3       # conservative: rounds AWAY from zero when negative
    assert counter.true_count(rounding="truncate") == -2
    assert counter.true_count(rounding="nearest") == -2


def test_true_count_rounding_positive_true_count():
    # decks_remaining=3.5; running_count=+9.45 -> raw true count = +2.7
    counter = _counter_with_state(HI_LO, num_decks=6, running_count=9.45, dealt=110)
    assert counter.true_count(rounding="floor") == 2         # conservative: never overbets on a rounding artefact
    assert counter.true_count(rounding="truncate") == 2
    assert counter.true_count(rounding="nearest") == 3


def test_default_rounding_is_floor():
    counter = _counter_with_state(HI_LO, num_decks=6, running_count=9.45, dealt=110)
    assert counter.tc_rounding == "floor"
    assert counter.true_count() == 2


# --- Ace side-count flag: Hi-Opt I/II and Omega II count aces as 0 ------------------------

def test_needs_ace_side_count_flags():
    assert HI_OPT_I.needs_ace_side_count
    assert HI_OPT_II.needs_ace_side_count
    assert OMEGA_II.needs_ace_side_count
    assert not HI_LO.needs_ace_side_count
    assert not KO.needs_ace_side_count
    assert not ZEN.needs_ace_side_count
    assert not RED_7.needs_ace_side_count


def test_aces_seen_tracks_regardless_of_system():
    counter = Counter(HI_OPT_I, num_decks=6)
    counter.see(Card(rank="A", suit="S"))
    counter.see(Card(rank="5", suit="H"))
    counter.see(Card(rank="A", suit="D"))
    assert counter.aces_seen == 2
    assert counter.dealt == 3


# --- Dual-system mode: a paired Counter must be indistinguishable from two separate ones --

def test_paired_counter_matches_two_independent_counters():
    shoe = Shoe(num_decks=6)
    betting, playing = Counter.paired(HI_LO, OMEGA_II, num_decks=6)
    solo_betting = Counter(HI_LO, num_decks=6)
    solo_playing = Counter(OMEGA_II, num_decks=6)

    dealt = 0
    diverged_mid_shoe = False
    while shoe.remaining > 0:
        card = shoe.deal()
        betting.see(card)
        playing.see(card)
        solo_betting.see(card)
        solo_playing.see(card)
        dealt += 1
        if dealt % 37 == 0:  # spot-check mid-shoe too, not just at the end
            assert betting.running_count == solo_betting.running_count
            assert playing.running_count == solo_playing.running_count
            if betting.running_count != playing.running_count:
                diverged_mid_shoe = True

    assert betting.running_count == solo_betting.running_count
    assert playing.running_count == solo_playing.running_count
    # Both are balanced systems, so both correctly return to the same IRC (0) once the
    # FULL shoe is dealt (see test_balanced_systems_return_to_zero_after_full_shoe) --
    # that's convergence by design, not evidence of shared state. Check independence
    # where it actually shows: Hi-Lo and Omega II have different tag vectors, so mid-shoe
    # they must diverge at least once if the two counters truly aren't linked.
    assert diverged_mid_shoe


def test_all_seven_systems_registered():
    assert len(ALL_SYSTEMS) == 7
    assert {s.name for s in ALL_SYSTEMS} == {
        "Hi-Lo", "KO", "Hi-Opt I", "Hi-Opt II", "Omega II", "Zen", "Red 7",
    }
