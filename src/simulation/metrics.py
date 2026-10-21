"""Phase 8: standard advantage-play metrics. Every function here takes simple,
already-computed statistics (never raw per-hand arrays -- see simulator.py's
BucketStats, which is what actually accumulates them) and returns one number.
Every CALLER reporting one of these must still attach its own standard error
where the inputs came from a simulation -- see .agents/instructions.md's "No
Bare Point Estimates from Monte Carlo"; these formulas themselves are exact
given their inputs, but the inputs (edge, variance) are usually themselves
noisy estimates.

Sign convention: `edge` here is the PLAYER's expected return per unit wagered
(negative = house edge, positive = player advantage) -- matching the build
plan's own Phase 8 example ("intercept ~ -0.005 ... slope ~ +0.005 ... giving
break-even near TC +1"), NOT test_house_edge.py's "house edge is a positive
number" convention. Do not mix the two without converting.
"""

import math


def win_rate_per_100(edge: float, bet: float = 1.0) -> float:
    """Expected units won per 100 hands at a flat `bet` size."""
    return edge * bet * 100.0


def n_zero(edge: float, variance: float) -> float:
    """N0: hands needed for the expected win to equal one standard deviation --
    the "how long until skill beats luck" number. Infinite at edge<=0 (skill
    never overcomes luck on an unfavorable or break-even game)."""
    if edge <= 0:
        return float("inf")
    return variance / (edge**2)


def risk_of_ruin(bankroll_units: float, edge: float, variance: float) -> float:
    """Brownian-motion approximation: exp(-2*B*mu/sigma^2). A non-positive edge
    is certain ruin (1.0) played indefinitely -- the formula's own exponential
    would otherwise give a nonsensical >1 "probability" for edge<0."""
    if edge <= 0:
        return 1.0
    return math.exp(-2.0 * bankroll_units * edge / variance)


def desirability_index(edge: float, variance: float) -> float:
    """DI = 1000 * EV / SD."""
    if variance <= 0:
        return float("inf") if edge > 0 else (0.0 if edge == 0 else float("-inf"))
    return 1000.0 * edge / math.sqrt(variance)


def score(edge: float, variance: float) -> float:
    """SCORE = DI^2 = 1,000,000 * EV^2 / Var -- the standard comparative
    game-quality metric (verified against published usage, not guessed at: SCORE
    is literally the Desirability Index squared, so a negative-edge game and its
    positive-edge mirror image score identically -- SCORE alone can't tell you
    which side of break-even a game is on, only how "sharp" its edge-to-noise
    ratio is; pair it with the sign of `edge` itself)."""
    return desirability_index(edge, variance) ** 2
