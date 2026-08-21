"""Phase 2 minimum-coverage tests for src/engine/dealer.py and src/engine/game.py.

Uses a ScriptedShoe test double (a plain .deal() card queue) instead of the real
Shoe, since game.py and dealer.py only ever call shoe.deal() -- no composition
bookkeeping is needed to drive these round-mechanics tests deterministically.
"""

from fractions import Fraction

import pytest

from src.engine.cards import Card
from src.engine.dealer import play_dealer
from src.engine.game import Action, play_round
from src.engine.hand import Hand
from src.engine.rules import RuleSet


class ScriptedShoe:
    def __init__(self, ranks):
        self._cards = [Card(rank=r, suit=None) for r in ranks]

    def deal(self) -> Card:
        return self._cards.pop(0)


def _always(action: Action):
    return lambda hand, dealer_up, shoe, rules, legal: action


def _no_decide(hand, dealer_up, shoe, rules, legal):
    raise AssertionError("decide_fn should not be called when the round settles before player action")


# --- Player blackjack pays 3:2 -----------------------------------------------------

def test_player_blackjack_pays_3_to_2():
    shoe = ScriptedShoe(["A", "9", "K", "7"])  # player: A,K (BJ); dealer: 9,7 (16, no BJ)
    result = play_round(shoe, RuleSet(), bet=10, decide_fn=_no_decide)
    assert result.player_hands[0].hand.is_blackjack
    assert not result.dealer_blackjack
    assert result.payouts == [15.0]


# --- Player blackjack vs dealer blackjack pushes ------------------------------------

def test_player_blackjack_vs_dealer_blackjack_pushes():
    shoe = ScriptedShoe(["A", "A", "K", "K"])  # player: A,K (BJ); dealer: A,K (BJ)
    result = play_round(shoe, RuleSet(), bet=10, decide_fn=_no_decide)
    assert result.dealer_blackjack
    assert result.player_hands[0].hand.is_blackjack
    assert result.payouts == [0.0]


# --- Split aces receive one card each, and 21-after-split pays 1:1, not 3:2 --------

def test_split_aces_one_card_each_and_21_after_split_pays_even_money():
    # player: A,A (split); dealer: 9,9 (18, stands immediately under S17)
    # left split hand draws K -> A,K = 21 (from_split, NOT blackjack)
    # right split hand draws 5 -> A,5 = soft 16
    shoe = ScriptedShoe(["A", "9", "A", "9", "K", "5"])
    result = play_round(shoe, RuleSet(), bet=10, decide_fn=_always(Action.SPLIT))

    assert len(result.player_hands) == 2
    left, right = result.player_hands
    assert len(left.hand.cards) == 2 and len(right.hand.cards) == 2

    assert left.hand.total == 21 and not left.hand.is_blackjack
    assert right.hand.total == 16 and right.hand.is_soft

    assert result.dealer_hand.total == 18 and len(result.dealer_hand.cards) == 2
    # left (21) beats dealer's 18 at 1:1 -- not the 1.5x a real blackjack would pay
    # right (16) loses to dealer's 18
    assert result.payouts == [10.0, -10.0]


# --- Surrender returns exactly half -------------------------------------------------

def test_surrender_returns_exactly_half_the_bet():
    shoe = ScriptedShoe(["7", "T", "9", "6"])  # player: 7,9=16; dealer: T,6=16 (no BJ)
    result = play_round(shoe, RuleSet(), bet=10, decide_fn=_always(Action.SURRENDER))
    assert result.player_hands[0].surrendered
    assert result.payouts == [-5.0]
    # A surrendered hand is not live, so the dealer must not draw further.
    assert len(result.dealer_hand.cards) == 2


# --- Dealer does not draw when the only player hand has busted ---------------------

def test_dealer_does_not_draw_when_player_hand_busts():
    # player: T,9=19, hits, draws T -> 29 bust; dealer: 5,5=10 (would normally have to hit)
    shoe = ScriptedShoe(["T", "5", "9", "5", "T"])
    result = play_round(shoe, RuleSet(), bet=10, decide_fn=_always(Action.HIT))
    assert result.player_hands[0].hand.is_bust
    assert result.payouts == [-10.0]
    assert len(result.dealer_hand.cards) == 2  # dealer never played out


# --- Dealer stands on soft 17 under S17, hits it under H17 -------------------------

def test_dealer_stands_on_soft_17_under_s17():
    # player: T,9=19 stands immediately; dealer: A,6 = soft 17
    shoe = ScriptedShoe(["T", "A", "9", "6"])
    result = play_round(shoe, RuleSet(dealer_hits_soft_17=False), bet=10, decide_fn=_always(Action.STAND))
    assert result.dealer_hand.total == 17 and result.dealer_hand.is_soft
    assert len(result.dealer_hand.cards) == 2


def test_dealer_hits_soft_17_under_h17():
    # same deal, plus one extra scripted card (4) for the forced hit: A,6,4 -> soft 21
    shoe = ScriptedShoe(["T", "A", "9", "6", "4"])
    result = play_round(shoe, RuleSet(dealer_hits_soft_17=True), bet=10, decide_fn=_always(Action.STAND))
    assert len(result.dealer_hand.cards) == 3
    assert result.dealer_hand.total == 21 and result.dealer_hand.is_soft


# --- No-peek dealer blackjack: OBBO vs full loss ------------------------------------

def _no_peek_double_scripted_shoe():
    # player: T,9=19, doubles (draws a 2); dealer: T,A = blackjack, revealed only after
    return ScriptedShoe(["T", "T", "9", "A", "2"])


def test_no_peek_full_loss_costs_the_doubled_bet():
    shoe = _no_peek_double_scripted_shoe()
    rules = RuleSet(dealer_peeks=False, obbo=False)
    result = play_round(shoe, rules, bet=10, decide_fn=_always(Action.DOUBLE))
    assert result.dealer_blackjack
    assert result.player_hands[0].doubled
    assert result.payouts == [-20.0]


def test_no_peek_obbo_costs_only_the_original_bet():
    shoe = _no_peek_double_scripted_shoe()
    rules = RuleSet(dealer_peeks=False, obbo=True)
    result = play_round(shoe, rules, bet=10, decide_fn=_always(Action.DOUBLE))
    assert result.dealer_blackjack
    assert result.player_hands[0].doubled
    assert result.payouts == [-10.0]


# --- dealer.py in isolation ----------------------------------------------------------

def test_play_dealer_stands_on_hard_17():
    hand = Hand(["T", "7"])
    shoe = ScriptedShoe([])  # no draws expected
    play_dealer(hand, shoe, RuleSet())
    assert hand.total == 17 and len(hand.cards) == 2


def test_play_dealer_hits_below_17():
    hand = Hand(["T", "6"])  # 16
    shoe = ScriptedShoe(["5"])  # -> 21, stops
    play_dealer(hand, shoe, RuleSet())
    assert hand.total == 21 and len(hand.cards) == 3


# --- Illegal action from decide_fn is rejected, not silently downgraded ------------

def test_illegal_action_raises():
    shoe = ScriptedShoe(["7", "T", "9", "6"])  # player 7,9=16 (no pair, can't split)
    with pytest.raises(ValueError):
        play_round(shoe, RuleSet(), bet=10, decide_fn=_always(Action.SPLIT))
