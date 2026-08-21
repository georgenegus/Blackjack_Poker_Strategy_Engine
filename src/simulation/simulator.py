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

from typing import Optional

import numpy as np

from src.engine.game import play_round
from src.engine.rules import RuleSet
from src.engine.shoe import Shoe


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
