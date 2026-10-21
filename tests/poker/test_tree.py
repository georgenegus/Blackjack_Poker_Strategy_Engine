"""Phase 6: the preflop betting tree. See
.agents/skills/poker_solver_conventions/SKILL.md and
markdowns/poker/poker_build_plan_v1.md Phase 6.

The min-raise/short-all-in-doesn't-reopen-action test below is the one that
matters most here: it's exactly the kind of subtle rule the build plan
called out explicitly ("a real rule, not an approximation"), and a tree that
gets it wrong silently hands CFR (Phase 7) illegal actions to learn from --
it would converge to "equilibrium" of the wrong game and never show an
obvious symptom.
"""

import pytest

from src.poker.spec import GameSpec
from src.poker.tree import Decision, Terminal, _apply_action, _build, _initial_state, _legal_raise_increments, build_tree


def _walk(node, path=()):
    if isinstance(node, Terminal):
        yield node, path
    else:
        for label, child in node.actions.items():
            yield from _walk(child, path + (label,))


# --- Structural sanity --------------------------------------------------


def test_tree_grows_with_more_bet_sizes():
    small = build_tree(GameSpec(stack_bb=10.0, bet_sizes=(1.0,)))
    big = build_tree(GameSpec(stack_bb=10.0, bet_sizes=(0.5, 1.0)))
    assert big.size() >= small.size()
    assert big.size() != small.size()


def test_tree_shrinks_with_lower_stack():
    deep = build_tree(GameSpec(stack_bb=10.0, bet_sizes=(1.0,)))
    short = build_tree(GameSpec(stack_bb=5.0, bet_sizes=(1.0,)))
    assert short.size() <= deep.size()


def test_deep_stack_tree_terminates_bounded():
    """Pot-sized raises grow geometrically, so even a 200bb stack tree stays
    small -- this would hang (or blow memory) if raise-size generation had
    an off-by-one letting stacks shrink without ever reaching all-in."""
    t = build_tree(GameSpec(stack_bb=200.0, bet_sizes=(1.0,)))
    n_nodes, n_infosets, n_terminals = t.size()
    assert n_nodes < 1000
    assert n_terminals > 0


def test_fold_terminals_are_zero_sum():
    """A fold terminal just redistributes already-committed chips -- no
    external money enters or leaves, so every fold terminal's payoffs must
    sum to exactly zero."""
    t = build_tree(GameSpec(stack_bb=10.0, bet_sizes=(1.0,)))
    fold_terms = [n for n, _ in _walk(t.root) if n.kind == "fold"]
    assert len(fold_terms) > 0
    for term in fold_terms:
        assert sum(term.payoffs_bb) == pytest.approx(0.0, abs=1e-9)


def test_showdown_terminals_have_unresolved_payoff():
    t = build_tree(GameSpec(stack_bb=10.0, bet_sizes=(1.0,)))
    showdown_terms = [n for n, _ in _walk(t.root) if n.kind == "showdown"]
    assert len(showdown_terms) > 0
    assert all(n.payoffs_bb is None for n in showdown_terms)
    assert all(sum(n.active) >= 2 for n in showdown_terms)


def test_cannot_fold_when_facing_no_bet():
    """You can't fold a hand you could see for free -- "fold" must never
    appear as a legal action at a to_call == 0 decision node."""
    t = build_tree(GameSpec(stack_bb=10.0, bet_sizes=(1.0,)))
    for node, _ in _walk_decisions(t.root):
        if node.to_call_bb <= 1e-9:
            assert "fold" not in node.actions


def _walk_decisions(node, path=()):
    if isinstance(node, Decision):
        yield node, path
        for label, child in node.actions.items():
            yield from _walk_decisions(child, path + (label,))


def test_heads_up_big_blind_gets_the_option():
    """Heads-up: if SB just calls, BB (having only posted a forced blind,
    not voluntarily acted) must still get a real decision -- check or raise
    -- not have the street close on them automatically."""
    t = build_tree(GameSpec(stack_bb=10.0, bet_sizes=(1.0,)))
    call_child = t.root.actions["call"]
    assert isinstance(call_child, Decision)
    assert call_child.player == 1
    assert call_child.to_call_bb == 0.0
    assert "check" in call_child.actions
    assert len(call_child.actions) > 1  # check plus at least one bet/all-in option


def test_three_handed_tree_builds_and_utg_acts_first():
    t = build_tree(GameSpec(num_players=3, stack_bb=20.0, bet_sizes=(1.0,)))
    assert t.root.player == 2  # UTG, not a blind


# --- The min-raise / short-all-in-doesn't-reopen rule -----------------------


def test_short_allin_does_not_reopen_action_for_players_who_already_acted():
    """3-handed: UTG makes a full pot-sized raise, SB calls (using up their
    turn without raising), then BB is stacked short enough that their only
    raise is BELOW the minimum -- an all-in for less. Real poker rule: this
    does NOT give UTG or SB (who already acted on the prior full bet) a new
    raise option, only call/fold. A player who HASN'T acted yet must still
    keep full raise rights.
    """
    spec = GameSpec(num_players=3, stack_bb=20.0, sb=0.5, bb=1.0, bet_sizes=(1.0,))
    s0 = _initial_state(spec)

    to_call = max(s0.committed_bb) - s0.committed_bb[2]
    incs = _legal_raise_increments(spec, sum(s0.committed_bb), to_call, s0.stacks_bb[2], s0.last_raise_bb)
    raise_to = max(s0.committed_bb) + incs[0]  # UTG's smallest legal full raise
    s1 = _apply_action(spec, s0, 2, "raise", raise_to)
    assert s1.last_raise_bb == incs[0]  # confirms this WAS registered as a full raise

    s2 = _apply_action(spec, s1, 0, "call", raise_to)  # SB calls

    # Shrink BB's stack so their only move is an all-in strictly below the min-raise increment
    bb_to_call = max(s2.committed_bb) - s2.committed_bb[1]
    short_behind = s2.last_raise_bb * 0.5
    s2b = s2.__class__(
        stacks_bb=(s2.stacks_bb[0], bb_to_call + short_behind, s2.stacks_bb[2]),
        committed_bb=s2.committed_bb,
        active=s2.active,
        to_act=s2.to_act,
        last_raise_bb=s2.last_raise_bb,
        history=s2.history,
    )
    allin_to = s2b.committed_bb[1] + s2b.stacks_bb[1]
    increment = allin_to - max(s2b.committed_bb)
    assert increment < s2b.last_raise_bb  # confirms this genuinely is a SHORT all-in

    s3 = _apply_action(spec, s2b, 1, "raise", allin_to)
    can_raise = dict(s3.to_act)
    assert can_raise[2] is False, "UTG already raised this bet level -- must not regain raise rights"
    assert can_raise[0] is False, "SB already called this bet level -- must not regain raise rights"

    utg_node = _build(spec, s3)
    assert utg_node.player == 2
    assert sorted(utg_node.actions.keys()) == ["call", "fold"]


def test_a_player_who_has_not_yet_acted_keeps_raise_rights_after_a_short_allin():
    """3-handed: UTG makes a full raise (to_act becomes [SB, BB], both with
    raise rights). SB then goes short all-in as their FIRST action -- a
    short all-in from a player who hasn't acted yet is exactly the case
    where BB (still queued behind them) must keep full raise rights, while
    UTG (who already raised, now facing SB's extra bit) is added back
    call/fold-only."""
    spec = GameSpec(num_players=3, stack_bb=20.0, sb=0.5, bb=1.0, bet_sizes=(1.0,))
    s0 = _initial_state(spec)
    to_call = max(s0.committed_bb) - s0.committed_bb[2]
    incs = _legal_raise_increments(spec, sum(s0.committed_bb), to_call, s0.stacks_bb[2], s0.last_raise_bb)
    raise_to = max(s0.committed_bb) + incs[0]
    s1 = _apply_action(spec, s0, 2, "raise", raise_to)  # UTG raises
    assert s1.to_act == ((0, True), (1, True))

    sb_to_call = max(s1.committed_bb) - s1.committed_bb[0]
    short_behind = s1.last_raise_bb * 0.5
    s1b = s1.__class__(
        stacks_bb=(sb_to_call + short_behind, s1.stacks_bb[1], s1.stacks_bb[2]),
        committed_bb=s1.committed_bb,
        active=s1.active,
        to_act=s1.to_act,
        last_raise_bb=s1.last_raise_bb,
        history=s1.history,
    )
    allin_to = s1b.committed_bb[0] + s1b.stacks_bb[0]
    increment = allin_to - max(s1b.committed_bb)
    assert increment < s1b.last_raise_bb  # genuinely a short all-in

    s2 = _apply_action(spec, s1b, 0, "raise", allin_to)
    can_raise = dict(s2.to_act)
    assert can_raise[1] is True, "BB never acted -- must keep full raise rights"
    assert can_raise[2] is False, "UTG already raised this bet level -- must not regain raise rights"
