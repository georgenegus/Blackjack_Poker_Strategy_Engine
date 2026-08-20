"""Round state machine. Game mechanics only -- no strategy knowledge. Every decision
is delegated to an injected `decide_fn`, which is the seam that lets the same round
engine be driven by basic strategy, count-aware deviations, a random baseline, or a
human via the UI. See .agents/skills/blackjack_rules_conventions/SKILL.md.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, List, Optional

from src.engine.cards import Card
from src.engine.dealer import play_dealer
from src.engine.hand import Hand
from src.engine.rules import RuleSet, double_allowed
from src.engine.shoe import Shoe


class Action(Enum):
    STAND = auto()
    HIT = auto()
    DOUBLE = auto()
    SPLIT = auto()
    SURRENDER = auto()


DecideFn = Callable[[Hand, Card, Shoe, RuleSet], Action]
InsuranceFn = Callable[[Hand, Card, Shoe, RuleSet], bool]


@dataclass
class PlayerHand:
    hand: Hand
    bet: float
    surrendered: bool = False
    doubled: bool = False


@dataclass
class RoundResult:
    dealer_hand: Hand
    player_hands: List[PlayerHand]
    payouts: List[float]
    insurance_payout: Optional[float] = None
    dealer_blackjack: bool = False




def _settle(ph: PlayerHand, dealer_hand: Hand) -> float:
    if ph.surrendered:
        return -ph.bet / 2
    if ph.hand.is_bust:
        return -ph.bet
    if dealer_hand.is_bust:
        return ph.bet
    if ph.hand.total > dealer_hand.total:
        return ph.bet
    if ph.hand.total < dealer_hand.total:
        return -ph.bet
    return 0.0


def _settle_vs_dealer_blackjack(ph: PlayerHand, original_bet: float, obbo: bool) -> float:
    if ph.surrendered:
        return -ph.bet / 2
    if obbo:
        return -original_bet
    return -ph.bet


def _play_one_hand(
    hand: Hand,
    bet: float,
    dealer_up: Card,
    shoe: Shoe,
    rules: RuleSet,
    decide_fn: DecideFn,
    results: List[PlayerHand],
    hand_count: List[int],
    is_split_aces: bool,
) -> None:
    ph = PlayerHand(hand=hand, bet=bet)

    if is_split_aces and not rules.hit_split_aces:
        # The one card split aces receive was already dealt by the SPLIT branch below;
        # no further action is offered.
        results.append(ph)
        return

    first_action = True
    while True:
        # hand_count[0] is the total hands in the round so far -- true globally, not just
        # along this hand's split lineage, because every split adds exactly one hand overall.
        can_double = (
            first_action
            and (hand_count[0] == 1 or rules.double_after_split)
            and double_allowed(rules, hand.total, hand.is_soft)
        )
        can_split = (
            first_action
            and hand.is_pair
            and hand_count[0] < rules.resplit_to
            and not (is_split_aces and not rules.resplit_aces)
        )
        # Surrender is a first-action option on the original hand only -- never on a split hand.
        can_surrender = first_action and hand_count[0] == 1 and rules.surrender != "none"

        legal = {Action.STAND, Action.HIT}
        if can_double:
            legal.add(Action.DOUBLE)
        if can_split:
            legal.add(Action.SPLIT)
        if can_surrender:
            legal.add(Action.SURRENDER)

        action = decide_fn(hand, dealer_up, shoe, rules)
        if action not in legal:
            raise ValueError(f"Illegal action {action!r} for {hand!r} (legal: {legal})")

        if action is Action.SURRENDER:
            ph.surrendered = True
            results.append(ph)
            return

        if action is Action.SPLIT:
            hand_count[0] += 1
            c1, c2 = hand.cards
            new_is_aces = c1.rank == "A"
            left, right = Hand([c1], from_split=True), Hand([c2], from_split=True)
            left.add(shoe.deal())
            right.add(shoe.deal())
            _play_one_hand(left, bet, dealer_up, shoe, rules, decide_fn, results, hand_count, new_is_aces)
            _play_one_hand(right, bet, dealer_up, shoe, rules, decide_fn, results, hand_count, new_is_aces)
            return

        if action is Action.DOUBLE:
            ph.bet *= 2
            ph.doubled = True
            hand.add(shoe.deal())
            results.append(ph)
            return

        if action is Action.HIT:
            hand.add(shoe.deal())
            first_action = False
            if hand.is_bust:
                results.append(ph)
                return
            continue

        # STAND
        results.append(ph)
        return


def _play_player_hands(
    initial_hand: Hand, bet: float, dealer_up: Card, shoe: Shoe, rules: RuleSet, decide_fn: DecideFn
) -> List[PlayerHand]:
    results: List[PlayerHand] = []
    hand_count = [1]
    _play_one_hand(initial_hand, bet, dealer_up, shoe, rules, decide_fn, results, hand_count, is_split_aces=False)
    return results


def play_round(
    shoe: Shoe,
    rules: RuleSet,
    bet: float,
    decide_fn: DecideFn,
    insurance_fn: Optional[InsuranceFn] = None,
) -> RoundResult:
    """Play one round for a single player. Resolution order (see the module docstring
    and blackjack_rules_conventions/SKILL.md for why this exact order matters):

    1. Deal: player, dealer up, player, dealer hole
    2. Offer insurance if dealer shows an Ace
    3. Peek: if dealer_peeks and dealer has blackjack, settle immediately
    4. Player blackjack (no dealer blackjack) pays blackjack_payout
    5. Player decisions per hand: surrender / split / double / hit / stand
    6. No-peek dealer blackjack, revealed only now, settles (obbo or full loss)
    7. Dealer plays out, only if at least one player hand is still live
    8. Settle each live hand vs the dealer's final total
    """
    if insurance_fn is None:
        insurance_fn = lambda *_: False

    dealer_hand = Hand()
    player_hand = Hand()
    player_hand.add(shoe.deal())
    dealer_up = shoe.deal()
    dealer_hand.add(dealer_up)
    player_hand.add(shoe.deal())
    # The hole card is dealt now regardless of dealer_peeks -- only *when it is checked*
    # differs between peek and no-peek rulesets, not when it is physically drawn from the shoe.
    dealer_hand.add(shoe.deal())

    insurance_payout: Optional[float] = None
    if dealer_up.rank == "A" and insurance_fn(player_hand, dealer_up, shoe, rules):
        insurance_bet = bet / 2
        insurance_payout = insurance_bet * 2 if dealer_hand.is_blackjack else -insurance_bet

    if rules.dealer_peeks and dealer_hand.is_blackjack:
        payout = 0.0 if player_hand.is_blackjack else -bet
        return RoundResult(dealer_hand, [PlayerHand(player_hand, bet)], [payout], insurance_payout, dealer_blackjack=True)

    if player_hand.is_blackjack:
        if not dealer_hand.is_blackjack:
            payout = float(bet) * float(rules.blackjack_payout)
            return RoundResult(dealer_hand, [PlayerHand(player_hand, bet)], [payout], insurance_payout, dealer_blackjack=False)
        # No-peek and both have blackjack: push.
        return RoundResult(dealer_hand, [PlayerHand(player_hand, bet)], [0.0], insurance_payout, dealer_blackjack=True)

    player_hands = _play_player_hands(player_hand, bet, dealer_up, shoe, rules, decide_fn)

    if not rules.dealer_peeks and dealer_hand.is_blackjack:
        payouts = [_settle_vs_dealer_blackjack(ph, bet, rules.obbo) for ph in player_hands]
        return RoundResult(dealer_hand, player_hands, payouts, insurance_payout, dealer_blackjack=True)

    if any(not ph.hand.is_bust and not ph.surrendered for ph in player_hands):
        play_dealer(dealer_hand, shoe, rules)

    payouts = [_settle(ph, dealer_hand) for ph in player_hands]
    return RoundResult(dealer_hand, player_hands, payouts, insurance_payout, dealer_blackjack=False)
