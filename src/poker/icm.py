"""Phase 9: the Independent Chip Model (Malmuth-Harville) and bubble
factor. See markdowns/poker/poker_build_plan_v1.md Phase 9.

ICM converts chip stacks into tournament $EV: a player's probability of
finishing 1st is their share of total chips; conditional on someone else
finishing 1st, the REMAINING players' relative chip shares determine who
finishes 2nd, and so on recursively. Malmuth-Harville is known to overstate
short stacks' finishing probabilities (it treats each finishing position as
a fresh proportional draw rather than modelling real play), but every
published table and competing tool uses it -- comparability is worth more
than the small accuracy gain of an alternative (Malmuth-Weitzman, Roberts),
per the build plan's own Appendix B item 6.
"""
from __future__ import annotations


def icm_equity(stacks: list[float], payouts: list[float]) -> list[float]:
    """Malmuth-Harville tournament equity for each player. `payouts[k]` is
    the prize for finishing in place k (0-indexed: payouts[0] = 1st).
    len(payouts) may be less than len(stacks) (only some places pay);
    positions beyond len(payouts) are worth 0 and are never explored.
    Recursion cost is O(n * (n-1) * ... * (n-k+1)) for k paid places --
    trivial for realistic final-table sizes, but genuinely exponential if
    EVERY position is paid (len(payouts) == len(stacks)) on a large field.
    """
    n = len(stacks)
    equity = [0.0] * n

    def recurse(remaining: list[int], remaining_payouts: list[float], prob_reach: float) -> None:
        if not remaining_payouts or not remaining:
            return
        total = sum(stacks[i] for i in remaining)
        if total <= 0:
            # Everyone still remaining is at exactly 0 chips (e.g. busted by
            # losing an all-in for their entire stack in an earlier branch of
            # this same recursion). Harville's stack-proportional formula is
            # undefined here (0/0); split the remaining finishing order
            # equally among them rather than dividing by zero -- with only
            # one player left this correctly assigns them that placement
            # with certainty regardless of their stack being 0.
            p_each = prob_reach / len(remaining)
            for idx in remaining:
                equity[idx] += p_each * remaining_payouts[0]
                recurse([i for i in remaining if i != idx], remaining_payouts[1:], p_each)
            return
        for idx in remaining:
            p_finish_here = prob_reach * stacks[idx] / total
            equity[idx] += p_finish_here * remaining_payouts[0]
            recurse([i for i in remaining if i != idx], remaining_payouts[1:], p_finish_here)

    recurse(list(range(n)), list(payouts), 1.0)
    return equity


def bubble_factor(stacks: list[float], payouts: list[float], player: int, opponent: int, risk_amount: float) -> float:
    """The ICM-equity risk/reward ratio for `player` risking `risk_amount`
    chips against `opponent` in a coin-flip-style confrontation -- the
    tournament analogue of pot odds. BF == 1 means ICM doesn't change the
    decision relative to raw chip EV; BF > 1 means MORE equity is needed
    than a chip-EV coin-flip would require, because the $EV lost if the
    confrontation is lost exceeds the $EV gained if it's won (the defining
    symptom of bubble play). risk_amount is capped by whichever player has
    fewer chips, matching a real all-in (you can't risk more than either
    stack holds).
    """
    risk_amount = min(risk_amount, stacks[player], stacks[opponent])
    current_equity = icm_equity(stacks, payouts)[player]

    win_stacks = list(stacks)
    win_stacks[player] += risk_amount
    win_stacks[opponent] -= risk_amount
    equity_win = icm_equity(win_stacks, payouts)[player]

    lose_stacks = list(stacks)
    lose_stacks[player] -= risk_amount
    lose_stacks[opponent] += risk_amount
    equity_lose = icm_equity(lose_stacks, payouts)[player]

    risk = current_equity - equity_lose
    reward = equity_win - current_equity
    return risk / reward
