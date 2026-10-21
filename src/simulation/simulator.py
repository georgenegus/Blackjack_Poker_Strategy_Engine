"""Lightweight Monte Carlo simulator -- a precursor to Phase 8's full battery
(TC-bucketed edge model, variance/N0/risk-of-ruin metrics), built now because
Phase 5's house-edge validation needs SOME simulation capability and Phase 8
doesn't exist yet.

Deliberately plays real rounds through game.py's play_round(), not the
solver's own abstract EVs -- this is what makes it an INDEPENDENT check on
Phase 3/4: a bug in game.py's payout mechanics (wrong blackjack odds, wrong
dealer draw logic) would corrupt this simulation's result even though
ev_solver.py never gets touched, whereas a purely analytical EV-weighted-
average over the solved grid would not catch such a bug at all.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

import numpy as np

from src.counting.counter import Counter
from src.counting.systems import CountingSystem
from src.engine.game import play_round
from src.engine.rules import RuleSet
from src.engine.shoe import Shoe
from src.strategy.basic_strategy import strategy_decide_fn
from src.strategy.deviations import make_decide_fn, should_take_insurance


def simulate_house_edge(
    rules: RuleSet,
    decide_fn,
    n_hands: int,
    bet: float = 1.0,
    insurance_fn=None,
    rng: Optional[np.random.Generator] = None,
    fresh_shoe_per_hand: bool = False,
):
    """Plays n_hands rounds, each staking `bet`. Returns (mean, stderr) of total
    per-round result / bet -- the standard "house edge" convention: expected
    result as a fraction of the ORIGINAL bet, not of the total amount put at
    risk after doubles/splits increase it. A negative mean is a player
    disadvantage (positive house edge).

    fresh_shoe_per_hand=False (default) reshuffles only at the cut card --
    realistic table play, what Phase 8's penetration/count-dependent edge
    work needs. fresh_shoe_per_hand=True reshuffles before EVERY hand, which
    is what published "house edge" figures conventionally assume (no
    depletion/counting effects at all -- that asymmetry is precisely what
    card counting exploits, and is out of scope for a basic-strategy check).
    Confirmed empirically: at realistic penetration, 2-deck and 4-deck both
    showed a real, multi-standard-error-significant bias toward the house
    (2D: simulated 0.259% vs published 0.190%, over 3 SE at n=30M; the bias
    shrank with more decks, exactly as expected for a penetration-driven
    effect diluting across a larger shoe) -- not a solver bug, but a mismatch
    between what was being measured and what the anchor represents.
    """
    rng = rng if rng is not None else np.random.default_rng()
    shoe = Shoe(rules.num_decks, rules.penetration, rng=rng)
    results = np.empty(n_hands, dtype=np.float64)

    for i in range(n_hands):
        if fresh_shoe_per_hand or shoe.cut_card_reached:
            shoe.reset()
        outcome = play_round(shoe, rules, bet, decide_fn, insurance_fn)
        total = sum(outcome.payouts)
        if outcome.insurance_payout:
            total += outcome.insurance_payout
        results[i] = total / bet

    mean = float(results.mean())
    stderr = float(results.std(ddof=1) / np.sqrt(n_hands))
    return mean, stderr


@dataclass
class BucketStats:
    """Online (streaming) mean/variance accumulator. A 20M-hand battery can't
    hold individual per-hand records in memory on a 7.7GB dev machine -- every
    statistic here comes from running sums, never a stored array."""

    n: int = 0
    sum_result: float = 0.0
    sum_result_sq: float = 0.0

    def add(self, result: float) -> None:
        self.n += 1
        self.sum_result += result
        self.sum_result_sq += result * result

    @property
    def mean(self) -> float:
        return self.sum_result / self.n if self.n else float("nan")

    @property
    def variance(self) -> float:
        if self.n < 2:
            return float("nan")
        return max(self.sum_result_sq / self.n - self.mean**2, 0.0)

    @property
    def stderr(self) -> float:
        if self.n < 2:
            return float("nan")
        return (self.variance / self.n) ** 0.5


@dataclass
class BatteryResult:
    ruleset_key: str
    system_name: str
    n_hands: int
    use_deviations: bool
    other_players: int
    overall: BucketStats
    by_true_count: Dict[int, BucketStats] = field(default_factory=dict)
    n_doubled: int = 0
    n_split_rounds: int = 0
    seconds: float = 0.0


_OTHER_PLAYER_CARDS_PER_HAND = 2.7  # documented rule-of-thumb average across 2-card/hit/double/split hands


def flat_bet_fn(_count_signal: float) -> float:
    return 1.0


def run_battery(
    rules: RuleSet,
    system: CountingSystem,
    n_hands: int,
    *,
    bet_fn: Callable[[float], float] = flat_bet_fn,
    use_deviations: bool = True,
    other_players: int = 0,
    rng: Optional[np.random.Generator] = None,
) -> BatteryResult:
    """Phase 8's full battery: plays n_hands rounds under REALISTIC penetration
    (never a fresh shoe per hand -- Phase 5's simulate_house_edge is for that;
    this phase's whole point is studying how edge and variance move as the shoe
    actually depletes), tracking true count at bet time, wager, net result, and
    double/split flags, bucketed for edge_model.py's fit.

    Count state is frozen for the WHOLE round at whatever it was immediately
    before this round's own cards are dealt -- used for both the bet-sizing
    count and (via deviations.advise()) the first-action deviation check. This
    is a deliberate simplification, not an oversight: index play (Phase 7) only
    ever applies to first-action 2-card hands anyway, so nothing later in the
    round would consult a more precisely mid-round-updated count even if this
    recomputed it card-by-card.

    The value passed to `bet_fn` and used for bucketing is the TRUE count
    (rounding="nearest") for balanced systems, but the RAW running count for
    unbalanced ones (KO, Red 7) -- Counter.true_count() raises for those by
    design (see counter.py), so there is no TC to give. A flat bet_fn ignores
    its argument either way; a count-aware one (Phase 9) must know which kind
    of system it's being handed.

    `other_players`: OTHER seats at the table, modelled as a simple card burn
    (mean 2.7 cards/hand) from the SAME shoe before each of our own rounds, fed
    to the counter same as our own cards -- a real counter watches every
    exposed card at the table, not just their own hand. This is NOT a full
    multi-seat game simulation: it only changes how fast the shoe depletes (and
    so how often/how far the count swings), never any EV number, since our own
    decisions only ever depend on the shoe composition at our own decision
    point, regardless of whose play consumed which cards.
    """
    rng = rng if rng is not None else np.random.default_rng()
    shoe = Shoe(rules.num_decks, rules.penetration, rng=rng)
    counter = Counter(system, rules.num_decks)
    decide_fn = make_decide_fn(counter) if use_deviations else strategy_decide_fn
    insurance_fn = (lambda *_: should_take_insurance(counter)) if use_deviations else None

    overall = BucketStats()
    by_count: Dict[int, BucketStats] = defaultdict(BucketStats)
    n_doubled = 0
    n_split_rounds = 0
    t0 = time.perf_counter()

    for _ in range(n_hands):
        if shoe.cut_card_reached:
            shoe.reset()
            counter.reset()

        if other_players > 0:
            n_burn = int(rng.poisson(other_players * _OTHER_PLAYER_CARDS_PER_HAND))
            for _ in range(min(n_burn, shoe.remaining - 1)):
                counter.see(shoe.deal())

        count_signal = counter.true_count(rounding="nearest") if system.balanced else counter.running_count
        bet = bet_fn(count_signal)

        outcome = play_round(shoe, rules, bet, decide_fn, insurance_fn)
        result = sum(outcome.payouts)
        if outcome.insurance_payout:
            result += outcome.insurance_payout

        overall.add(result / bet)
        by_count[int(round(count_signal))].add(result / bet)

        if len(outcome.player_hands) > 1:
            n_split_rounds += 1
        for ph in outcome.player_hands:
            if ph.doubled:
                n_doubled += 1
            for card in ph.hand.cards:
                counter.see(card)
        # Counts the dealer's hole card even on rounds where every player hand busts and
        # game.py never calls play_dealer -- some houses don't turn it over then, but with
        # other_players>0 (a genuinely multi-seat table) some OTHER seat has usually not
        # busted, so the dealer plays and reveals it anyway; treated as always-observable
        # here rather than modelling per-house hole-card policy.
        for card in outcome.dealer_hand.cards:
            counter.see(card)

    return BatteryResult(
        ruleset_key=rules.key(),
        system_name=system.name,
        n_hands=n_hands,
        use_deviations=use_deviations,
        other_players=other_players,
        overall=overall,
        by_true_count=dict(by_count),
        n_doubled=n_doubled,
        n_split_rounds=n_split_rounds,
        seconds=time.perf_counter() - t0,
    )
