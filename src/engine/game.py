"""Round state machine. Game mechanics only -- no strategy knowledge. Every decision
is delegated to an injected `decide_fn`, which is the seam that lets the same round
engine be driven by basic strategy, count-aware deviations, a random baseline, or a
human via the UI. See .agents/skills/blackjack_rules_conventions/SKILL.md.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, FrozenSet, List, Optional

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


DecideFn = Callable[[Hand, Card, Shoe, RuleSet, FrozenSet[Action]], Action]
"""(player_hand, dealer_up, shoe, rules, legal_actions) -> Action. `legal_actions`
is the exact set game.py itself computed for this decision point -- e.g. it
already accounts for resplit_to and DAS, which a strategy function like
basic_strategy.advise() cannot know from the Hand alone (it only knows this
one hand's own first-action/from_split state, not the round-wide split
count). A decide_fn is expected to return something IN this set; returning
anything else raises, rather than being silently downgraded."""
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


def _play_one_hand_gen(
    hand: Hand,
    bet: float,
    dealer_up: Card,
    shoe: Shoe,
    rules: RuleSet,
    results: List[PlayerHand],
    hand_count: List[int],
    is_split_aces: bool,
):
    """Generator form: yields (hand, legal_actions) at each decision point and
    receives the chosen Action via .send(). This is the ONE implementation of
    split/double/hit/surrender legality and transitions -- play_round (below)
    drives it with a decide_fn in a tight loop for simulation/AI callers,
    exactly reproducing the old direct-recursion behavior; play_hands_interactive
    exposes the raw generator so an HTTP API (Phase 10) can pause between
    requests instead, without a second, separately-maintained copy of this
    logic to drift out of sync with the first. See the module docstring.
    """
    ph = PlayerHand(hand=hand, bet=bet)

    if is_split_aces and not rules.hit_split_aces:
        # The one card split aces receive was already dealt by the SPLIT branch below.
        # Normally no further action -- UNLESS this card is itself another ace and
        # resplit_aces is allowed, in which case RESPLITTING (only, not hitting) is
        # still offered. "Resplit aces" and "hit split aces" are independent casino
        # rule toggles in standard terminology, not one gating the other.
        can_resplit_aces = hand.is_pair and rules.resplit_aces and hand_count[0] < rules.resplit_to
        if not can_resplit_aces:
            results.append(ph)
            return

        legal = frozenset({Action.STAND, Action.SPLIT})
        action = yield (hand, legal)
        if action not in legal:
            raise ValueError(f"Illegal action {action!r} for {hand!r} (legal: {legal})")
        if action is Action.SPLIT:
            hand_count[0] += 1
            c1, c2 = hand.cards
            left, right = Hand([c1], from_split=True), Hand([c2], from_split=True)
            left.add(shoe.deal())
            right.add(shoe.deal())
            yield from _play_one_hand_gen(left, bet, dealer_up, shoe, rules, results, hand_count, is_split_aces=True)
            yield from _play_one_hand_gen(right, bet, dealer_up, shoe, rules, results, hand_count, is_split_aces=True)
            return
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
        legal = frozenset(legal)

        action = yield (hand, legal)
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
            yield from _play_one_hand_gen(left, bet, dealer_up, shoe, rules, results, hand_count, new_is_aces)
            yield from _play_one_hand_gen(right, bet, dealer_up, shoe, rules, results, hand_count, new_is_aces)
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


def play_hands_interactive(initial_hand: Hand, bet: float, dealer_up: Card, shoe: Shoe, rules: RuleSet):
    """Public generator entry point for step-by-step (HTTP-driven) play: yields
    (hand, legal_actions) at each decision point, takes the chosen Action via
    .send(action), and its StopIteration.value is the final List[PlayerHand] --
    exactly what the old _play_player_hands returned, just paced by the caller
    (e.g. one HTTP request per decision) instead of an immediately-callable
    decide_fn. A session holds to this generator BETWEEN requests -- see
    app.py's GameSession -- since it's a plain Python object, never a shoe/hand
    round-tripped through the browser.
    """
    results: List[PlayerHand] = []
    hand_count = [1]
    yield from _play_one_hand_gen(initial_hand, bet, dealer_up, shoe, rules, results, hand_count, is_split_aces=False)
    return results


def _play_player_hands(
    initial_hand: Hand, bet: float, dealer_up: Card, shoe: Shoe, rules: RuleSet, decide_fn: DecideFn
) -> List[PlayerHand]:
    """Drives play_hands_interactive with decide_fn in a tight loop -- this is
    what keeps play_round's signature/behavior unchanged for every existing
    (simulation/AI) caller. There is only ONE implementation of the actual
    split/double/hit/surrender logic (play_hands_interactive /
    _play_one_hand_gen), not two that could quietly drift apart."""
    gen = play_hands_interactive(initial_hand, bet, dealer_up, shoe, rules)
    try:
        hand, legal = next(gen)
        while True:
            action = decide_fn(hand, dealer_up, shoe, rules, legal)
            hand, legal = gen.send(action)
    except StopIteration as stop:
        return stop.value


@dataclass
class InitialDeal:
    """The opening deal, when the round did NOT already settle (no blackjack/
    peek short-circuit) and still needs player decisions -- via
    play_hands_interactive or _play_player_hands -- then settle_round().
    Returned by deal_initial() instead of a RoundResult in that case."""

    dealer_hand: Hand
    player_hand: Hand
    dealer_up: Card
    bet: float
    insurance_payout: Optional[float]


def deal_initial(
    shoe: Shoe, rules: RuleSet, bet: float, insurance_fn: Optional[InsuranceFn] = None
):
    """Deals the opening 4 cards, offers insurance, and checks the peek/
    instant-blackjack short-circuits -- steps 1-4 of play_round's own
    docstring. Returns a finished RoundResult if the round already settled
    (dealer blackjack under peek, or player blackjack), otherwise an
    InitialDeal to continue via play_hands_interactive (Phase 10's HTTP API
    drives this directly, one request per decision) or _play_player_hands
    (play_round, below, drives this with a decide_fn), then settle_round().
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

    return InitialDeal(dealer_hand, player_hand, dealer_up, bet, insurance_payout)


def settle_round(
    dealer_hand: Hand,
    player_hands: List[PlayerHand],
    shoe: Shoe,
    rules: RuleSet,
    original_bet: float,
    insurance_payout: Optional[float] = None,
) -> RoundResult:
    """Once every player hand is done (via play_hands_interactive or
    _play_player_hands): reveals no-peek dealer blackjack if applicable, plays
    the dealer out if any hand is still live, and settles -- steps 6-8 of
    play_round's own docstring. `original_bet` is the ante BEFORE any
    doubling/splitting -- OBBO settlement caps the loss at this, not at a
    (possibly doubled) individual hand's own ph.bet; see _settle_vs_dealer_blackjack.
    """
    if not rules.dealer_peeks and dealer_hand.is_blackjack:
        payouts = [_settle_vs_dealer_blackjack(ph, original_bet, rules.obbo) for ph in player_hands]
        return RoundResult(dealer_hand, player_hands, payouts, insurance_payout, dealer_blackjack=True)

    if any(not ph.hand.is_bust and not ph.surrendered for ph in player_hands):
        play_dealer(dealer_hand, shoe, rules)

    payouts = [_settle(ph, dealer_hand) for ph in player_hands]
    return RoundResult(dealer_hand, player_hands, payouts, insurance_payout, dealer_blackjack=False)


def play_round(
    shoe: Shoe,
    rules: RuleSet,
    bet: float,
    decide_fn: DecideFn,
    insurance_fn: Optional[InsuranceFn] = None,
) -> RoundResult:
    """Play one round for a single player, driven end-to-end by decide_fn (see
    DecideFn) -- for simulation/AI callers. Just deal_initial() -> (if not
    already settled) _play_player_hands() -> settle_round(), in one call; see
    those three for what each step actually does and the build plan's Phase 10
    for how an HTTP API instead drives deal_initial/play_hands_interactive/
    settle_round across separate requests, one per player decision.
    """
    dealt = deal_initial(shoe, rules, bet, insurance_fn)
    if isinstance(dealt, RoundResult):
        return dealt

    player_hands = _play_player_hands(dealt.player_hand, bet, dealt.dealer_up, shoe, rules, decide_fn)
    return settle_round(dealt.dealer_hand, player_hands, shoe, rules, bet, dealt.insurance_payout)
