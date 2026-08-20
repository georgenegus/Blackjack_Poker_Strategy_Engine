"""Dealer draw logic: hit until 17, respecting S17/H17."""

from src.engine.hand import Hand
from src.engine.rules import RuleSet
from src.engine.shoe import Shoe


def play_dealer(hand: Hand, shoe: Shoe, rules: RuleSet) -> Hand:
    """Draw cards for the dealer until the hand stands, mutating and returning `hand`.
    Stops naturally on bust, since total > 21 fails both draw conditions below."""
    while hand.total < 17 or (hand.total == 17 and hand.is_soft and rules.dealer_hits_soft_17):
        hand.add(shoe.deal())
    return hand
