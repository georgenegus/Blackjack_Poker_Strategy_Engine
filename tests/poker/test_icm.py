"""Phase 9: the Independent Chip Model. See
markdowns/poker/poker_build_plan_v1.md Appendix A.6 and Phase 9.

A real bug was caught while testing bubble_factor() here: icm_equity()
divided by zero whenever every remaining player in the recursion had
exactly 0 chips (e.g. a player who just lost an all-in for their entire
stack) -- Harville's stack-proportional formula is undefined at 0/0. Fixed
by splitting the remaining finishing-order probability equally among any
zero-stack players still in the recursion; the zero-stack regression test
below hand-verifies the fix's specific numbers, not just that it no longer
crashes.
"""

import pytest

from src.poker.icm import bubble_factor, icm_equity


def test_appendix_a6_worked_example():
    equities = icm_equity([5000, 3000, 2000], [50, 30, 20])
    assert equities == pytest.approx([38.392857, 32.75, 28.857143], abs=1e-5)
    assert sum(equities) == pytest.approx(100.0)


def test_equities_sum_to_exactly_the_prize_pool():
    for stacks, payouts in [
        ([100, 200, 300, 400], [50, 30, 20]),
        ([1, 1, 1, 1, 1], [60, 25, 15]),
        ([1000], [100]),
    ]:
        assert sum(icm_equity(stacks, payouts)) == pytest.approx(sum(payouts))


def test_equal_stacks_give_equal_equity_for_any_payout_structure():
    for payouts in [[50, 30, 20], [70, 20, 10], [100]]:
        equities = icm_equity([1000, 1000, 1000], payouts)
        assert equities[0] == pytest.approx(equities[1]) == pytest.approx(equities[2])
        assert equities[0] == pytest.approx(sum(payouts) / 3.0)


def test_marginal_chip_value_falls_as_stack_grows():
    """The entire content of ICM: a chip leader's equity per chip is below
    a short stack's -- a model that fails this is not ICM."""
    stacks = [5000, 3000, 2000]
    equities = icm_equity(stacks, [50, 30, 20])
    per_chip = [e / s for e, s in zip(equities, stacks)]
    assert per_chip[0] < per_chip[1] < per_chip[2]  # leader worth least per chip, short stack most


def test_winner_take_all_reduces_to_chip_proportional_equity():
    stacks = [5000, 3000, 2000]
    equities = icm_equity(stacks, [100])
    total = sum(stacks)
    expected = [100.0 * s / total for s in stacks]
    assert equities == pytest.approx(expected)


def test_zero_stack_player_is_certain_to_finish_last():
    """Regression test for the division-by-zero bug this module's docstring
    describes -- hand-verified numbers (not just "doesn't crash"): a player
    with exactly 0 chips is guaranteed dead last, receiving exactly the
    lowest payout, and the two non-zero stacks split the higher payouts NOT
    simply proportionally to their own chip ratio, because whichever one
    does not finish 1st is then guaranteed 2nd (the zero-stack player can
    never take 2nd either)."""
    equities = icm_equity([7000, 3000, 0], [50, 30, 20])
    assert equities[2] == pytest.approx(20.0)  # certain last-place payout
    assert equities[0] == pytest.approx(0.7 * 50 + 0.3 * 30)  # 44.0, hand-derived
    assert equities[1] == pytest.approx(0.3 * 50 + 0.7 * 30)  # 36.0, hand-derived
    assert sum(equities) == pytest.approx(100.0)


def test_multiple_zero_stack_players_split_remaining_placements_equally():
    equities = icm_equity([10000, 0, 0], [50, 30, 20])
    assert equities[0] == pytest.approx(50.0)  # certain 1st with all the chips
    assert equities[1] == pytest.approx(equities[2])  # the two zero-stacks split 2nd/3rd equally
    assert equities[1] == pytest.approx((30.0 + 20.0) / 2.0)
    assert sum(equities) == pytest.approx(100.0)


# --- Bubble factor -----------------------------------------------------------


def test_bubble_factor_deep_in_the_money_stays_near_one():
    """With every remaining player guaranteed to cash (payouts covering the
    whole field), ICM pressure is mild -- bubble factor should be close to,
    though not necessarily exactly, 1.0."""
    bf = bubble_factor([1000, 1000, 1000], [40, 35, 25], player=0, opponent=1, risk_amount=500)
    assert 0.8 < bf < 1.3


def test_bubble_factor_is_elevated_near_a_real_elimination_bubble():
    """4 players, only the top 3 pay -- a genuine elimination bubble for
    whoever busts. The chip leader calling a short stack's shove should show
    a bubble factor meaningfully above 1: their downside (losing chips they
    could otherwise coast to a min-cash with) outweighs their upside."""
    bf = bubble_factor([3000, 800, 1500, 1500], [50, 30, 20], player=0, opponent=1, risk_amount=800)
    assert bf > 1.05


def test_bubble_factor_risk_amount_is_capped_by_the_smaller_stack():
    """Asking to risk more than either player actually has must not
    silently produce a nonsensical stack (e.g. negative chips) -- the risked
    amount is capped at the smaller of the two stacks."""
    bf_exact = bubble_factor([5000, 2000], [70, 30], player=0, opponent=1, risk_amount=2000)
    bf_over = bubble_factor([5000, 2000], [70, 30], player=0, opponent=1, risk_amount=999999)
    assert bf_exact == pytest.approx(bf_over)
