"""Phase 7/8: KuhnPoker's and LeducPoker's own mechanics, independent of
CFR -- a bug in the game definition itself (a wrong payoff, a chance
distribution that doesn't sum to 1) would be indistinguishable from a CFR
bug if only convergence were checked, so these are tested on their own."""

from itertools import combinations, permutations

import pytest

from src.poker.toy import KuhnPoker, LeducHistory, LeducPoker


def test_chance_outcomes_sum_to_one_and_cover_all_deals():
    game = KuhnPoker()
    outcomes = game.chance_outcomes(())
    assert sum(p for _, p in outcomes) == pytest.approx(1.0)
    assert {deal for deal, _ in outcomes} == set(permutations(game.CARDS, 2))
    assert all(p == pytest.approx(1.0 / 6.0) for _, p in outcomes)


def test_is_chance_only_at_the_empty_history():
    game = KuhnPoker()
    assert game.is_chance(())
    assert not game.is_chance((0, 1, "p"))


def test_terminal_detection_matches_all_five_kuhn_lines():
    game = KuhnPoker()
    terminal_seqs = [("p", "p"), ("b", "p"), ("b", "b"), ("p", "b", "p"), ("p", "b", "b")]
    for seq in terminal_seqs:
        assert game.is_terminal((0, 1) + seq)
    assert not game.is_terminal((0, 1))
    assert not game.is_terminal((0, 1, "p"))
    assert not game.is_terminal((0, 1, "b"))


def test_current_player_alternates_starting_with_player_zero():
    game = KuhnPoker()
    assert game.current_player((0, 1)) == 0
    assert game.current_player((0, 1, "p")) == 1
    assert game.current_player((0, 1, "p", "b")) == 0


@pytest.mark.parametrize(
    "actions,c0,c1,expected0",
    [
        (("p", "p"), 2, 0, 1.0),  # showdown, p0's king beats p1's jack
        (("p", "p"), 0, 2, -1.0),  # showdown, p0 loses
        (("b", "p"), 0, 2, 1.0),  # p1 folds to p0's bet regardless of cards
        (("b", "b"), 2, 0, 2.0),  # bet-call showdown, p0 wins the bigger pot
        (("b", "b"), 0, 2, -2.0),
        (("p", "b", "p"), 2, 0, -1.0),  # p0 folds to p1's bet regardless of cards
        (("p", "b", "b"), 2, 0, 2.0),
        (("p", "b", "b"), 0, 2, -2.0),
    ],
)
def test_utility_matches_hand_derived_payoffs(actions, c0, c1, expected0):
    game = KuhnPoker()
    history = (c0, c1) + actions
    assert game.utility(history, 0) == expected0
    assert game.utility(history, 1) == -expected0  # zero-sum


def test_infoset_key_only_reveals_the_acting_players_own_card():
    """The single most important structural property: a player's infoset
    must never encode the OPPONENT's card -- if it did, CFR would be
    solving a game of complete information, not Kuhn poker."""
    game = KuhnPoker()
    key0 = game.infoset_key((2, 0, "p"), 0)
    key0_other_opponent_card = game.infoset_key((2, 1, "p"), 0)
    assert key0 == key0_other_opponent_card  # p0's infoset is identical regardless of p1's card
    assert key0[0] == 2  # but does reveal p0's own card


# ---------------------------------------------------------------------------
# LeducPoker
# ---------------------------------------------------------------------------


def test_leduc_chance_outcomes_sum_to_one():
    game = LeducPoker()
    deals = game.chance_outcomes(())
    assert sum(p for _, p in deals) == pytest.approx(1.0)
    assert len(deals) == 30  # 6 * 5 ordered deals
    assert all(p == pytest.approx(1.0 / 30.0) for _, p in deals)

    h = LeducHistory(0, 1, ("p", "p"), None, ())
    publics = game.chance_outcomes(h)
    assert sum(p for _, p in publics) == pytest.approx(1.0)
    assert len(publics) == 4  # 6 cards minus the 2 already dealt
    assert all(p == pytest.approx(0.25) for _, p in publics)


def test_leduc_round_closes_and_deals_public_card_after_check_check():
    game = LeducPoker()
    h = LeducHistory(0, 1, (), None, ())
    assert not game.is_chance(h) and not game.is_terminal(h)
    h = game.next_history(h, "p")
    assert not game.is_chance(h) and not game.is_terminal(h)
    h = game.next_history(h, "p")
    assert game.is_chance(h)
    assert not game.is_terminal(h)


def test_leduc_fold_ends_the_hand_immediately_without_a_public_card():
    game = LeducPoker()
    h = LeducHistory(0, 1, ("b", "p"), None, ())
    assert game.is_terminal(h)
    assert h.public is None  # folded before the public card was ever dealt


def test_leduc_raise_cap_forbids_a_third_bet():
    game = LeducPoker()
    h = LeducHistory(0, 1, ("b", "b"), None, ())
    assert game.legal_actions(h) == ("p", "c")  # cap reached: fold or call only, no re-raise


def test_leduc_legal_actions_before_any_bet():
    game = LeducPoker()
    assert game.legal_actions(LeducHistory(0, 1, (), None, ())) == ("p", "b")


def test_leduc_legal_actions_facing_first_bet_include_raise():
    game = LeducPoker()
    assert game.legal_actions(LeducHistory(0, 1, ("b",), None, ())) == ("p", "c", "b")


def test_leduc_utility_fold_wins_only_the_pot_so_far():
    game = LeducPoker()
    # player0 bets 2 (round1 bet size), player1 folds -> player0 wins player1's ante only
    h = LeducHistory(0, 1, ("b", "p"), None, ())
    assert game.utility(h, 0) == 1.0  # wins the 1-chip ante
    assert game.utility(h, 1) == -1.0


def test_leduc_utility_raise_cap_fold_matches_hand_derived_pot():
    game = LeducPoker()
    # p0 bets 2 (total 2), p1 raises to 4 (total 4), p0 folds (cap reached, no further raise)
    h = LeducHistory(0, 1, ("b", "b", "p"), None, ())
    # pot = ante(1+1) + p0's 2 + p1's 4 = 8; p0 folded so p1 wins; p1's own total = 1+4=5
    assert game.utility(h, 1) == pytest.approx(8.0 - 5.0)
    assert game.utility(h, 0) == pytest.approx(-3.0)  # -(ante 1 + round1 contrib 2)


def test_leduc_showdown_pair_beats_nonpair():
    game = LeducPoker()
    # card0=0 (J), card1=2 (Q), public=1 (J) -> player0 pairs Jacks, wins despite lower raw rank
    h = LeducHistory(0, 2, ("p", "p"), 1, ("p", "p"))
    assert game.utility(h, 0) > 0
    assert game.utility(h, 1) < 0


def test_leduc_showdown_equal_nonpair_ranks_split_the_pot():
    game = LeducPoker()
    # card0=0 (J), card1=1 (J, other suit), public=2 (Q) -> both J, no pair, exact tie
    h = LeducHistory(0, 1, ("p", "p"), 2, ("p", "p"))
    assert game.utility(h, 0) == 0.0
    assert game.utility(h, 1) == 0.0


def test_leduc_showdown_higher_nonpair_rank_wins():
    game = LeducPoker()
    # card0=4 (K), card1=1 (J), public=2 (Q) -> neither pairs, K beats J
    h = LeducHistory(4, 1, ("p", "p"), 2, ("p", "p"))
    assert game.utility(h, 0) > 0
    assert game.utility(h, 1) < 0


def test_leduc_zero_sum_across_all_covered_terminal_shapes():
    game = LeducPoker()
    cases = [
        LeducHistory(0, 1, ("p", "p"), 2, ("p", "p")),  # round1+round2 both check through, showdown
        LeducHistory(0, 1, ("b", "p"), None, ()),  # fold in round1, before any public card
        LeducHistory(0, 1, ("b", "b", "c"), 2, ("p", "p")),  # round1 closed via a raise-call, then showdown
        LeducHistory(4, 1, ("p", "b", "c"), 2, ("b", "c")),  # round1 closed via call, round2 closed via call
    ]
    for h in cases:
        assert game.is_terminal(h), f"test case is not actually terminal: {h}"
        assert game.utility(h, 0) == pytest.approx(-game.utility(h, 1))


def test_leduc_infoset_key_never_reveals_the_opponents_card():
    game = LeducPoker()
    key = game.infoset_key(LeducHistory(0, 1, ("p",), None, ()), 0)
    key_other_opp_card = game.infoset_key(LeducHistory(0, 4, ("p",), None, ()), 0)
    assert key == key_other_opp_card
    assert key[0] == 0


def test_leduc_full_enumeration_terminal_count_is_stable():
    """A hardcoded regression anchor on the game's own size -- if this
    number ever changes, either the rules changed deliberately (update the
    anchor) or something broke silently (a legality/termination bug)."""
    game = LeducPoker()
    counts = {"terminal": 0, "chance": 0}

    def walk(h):
        if game.is_terminal(h):
            counts["terminal"] += 1
            return
        if game.is_chance(h):
            counts["chance"] += 1
            for nh, _ in game.chance_outcomes(h):
                walk(nh)
            return
        for a in game.legal_actions(h):
            walk(game.next_history(h, a))

    walk(())
    assert counts["terminal"] == 5520
    assert counts["chance"] == 151
