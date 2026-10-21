"""Phase 6: the preflop betting tree, built entirely from GameSpec -- no
hardcoded action list, no hardcoded stack depth. See
markdowns/poker/poker_build_plan_v1.md Phase 6 and
.agents/skills/poker_solver_conventions/SKILL.md.

Scoped to preflop action only, matching Phase 10's own design: a line that
sees a flop is a single approximated terminal there (its own documented
"equity realisation" compromise), not a fully-modelled flop/turn/river tree
-- so this module never needs to chain betting rounds across streets. The
same single-street machinery here is what Phase 10's solve_spot.py reuses
for a bounded postflop spot, which is exactly one street given a fixed
board.

Legal actions at every decision are derived from spec.bet_sizes,
spec.stack_bb, and the current pot/stacks -- never a literal list. Minimum-
raise legality (a raise must be at least the size of the previous raise,
with the standard exception that an all-in for less does not reopen the
action for players who already acted on the current bet) is modelled
explicitly via a per-player "can this player still raise" flag carried
alongside the acting queue, not approximated.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.poker.spec import GameSpec


@dataclass(frozen=True)
class Terminal:
    """A resolved end of the betting round.

    kind == "fold": exactly one active player remains; payoffs_bb is exact
        (no cards needed at all).
    kind == "showdown": two or more players are still active with the
        street's action closed; payoffs_bb is None -- resolving this needs
        hole cards, and possibly further streets this module deliberately
        doesn't model (see this file's module docstring).
    """

    kind: str
    pot_bb: float
    active: tuple[bool, ...]
    payoffs_bb: tuple[float, ...] | None
    history: tuple[str, ...]


@dataclass(frozen=True)
class Decision:
    player: int
    pot_bb: float
    to_call_bb: float
    stacks_bb: tuple[float, ...]
    actions: dict[str, "Node"]
    history: tuple[str, ...]


Node = Decision | Terminal


@dataclass(frozen=True)
class Tree:
    root: Node
    spec: GameSpec

    def size(self) -> tuple[int, int, int]:
        """(n_nodes, n_infosets, n_terminals). n_infosets counts DECISION
        nodes -- one per (player, history) point in this card-agnostic tree;
        combining with abstraction.py's card buckets (Phase 7+) multiplies
        this further by however many buckets each player's hole cards could
        fall into. Print this before every solve, per the build plan's own
        warning -- an abstraction or bet-size grid that silently grew the
        tree by 40x is the most common cause of a solve that "hangs"."""
        return _size(self.root)


def _size(node: Node) -> tuple[int, int, int]:
    if isinstance(node, Terminal):
        return (1, 0, 1)
    n_nodes, n_infosets, n_terminals = 1, 1, 0
    for child in node.actions.values():
        cn, ci, ct = _size(child)
        n_nodes += cn
        n_infosets += ci
        n_terminals += ct
    return (n_nodes, n_infosets, n_terminals)


# ---------------------------------------------------------------------------
# Internal betting-round state
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _State:
    stacks_bb: tuple[float, ...]  # remaining behind, per player
    committed_bb: tuple[float, ...]  # chips already put in this street, per player
    active: tuple[bool, ...]  # still in the hand (hasn't folded)
    to_act: tuple[tuple[int, bool], ...]  # ordered queue: (player, can_still_raise)
    last_raise_bb: float  # size of the last FULL raise increment (min-raise reference)
    history: tuple[str, ...]


def _rotation_from(start: int, n: int) -> list[int]:
    return [(start + i) % n for i in range(n)]


def _legal_bet_sizes(spec: GameSpec, pot_bb: float, stack_bb: float) -> list[float]:
    """Opening-bet sizes (to_call == 0): pot_bb * each spec.bet_sizes
    fraction, each snapped to all-in if it would leave less than half a big
    blind behind, deduplicated, sorted ascending."""
    sizes = set()
    for frac in spec.bet_sizes:
        raw = pot_bb * frac
        amt = min(stack_bb if stack_bb - raw < 0.5 * spec.bb else raw, stack_bb)
        if amt > 1e-9:
            sizes.add(round(amt, 6))
    if spec.allow_allin and stack_bb > 1e-9:
        sizes.add(round(stack_bb, 6))
    return sorted(sizes)


def _legal_raise_increments(
    spec: GameSpec, pot_bb: float, to_call_bb: float, stack_bb: float, last_raise_bb: float
) -> list[float]:
    """Raise-increment sizes (to_call > 0, ON TOP of calling): (pot after
    calling) * each spec.bet_sizes fraction, legal only if the increment is
    >= last_raise_bb (the standard min-raise rule) OR it's an all-in for
    less (always legal, but does not reopen the action -- see _apply_action).
    """
    pot_after_call = pot_bb + to_call_bb
    remaining_after_call = stack_bb - to_call_bb
    if remaining_after_call <= 1e-9:
        return []
    sizes = set()
    for frac in spec.bet_sizes:
        raw = pot_after_call * frac
        amt = min(remaining_after_call if remaining_after_call - raw < 0.5 * spec.bb else raw, remaining_after_call)
        if amt > 1e-9 and (amt >= last_raise_bb - 1e-9 or amt >= remaining_after_call - 1e-9):
            sizes.add(round(amt, 6))
    if spec.allow_allin and remaining_after_call > 1e-9:
        sizes.add(round(remaining_after_call, 6))
    return sorted(sizes)


def _initial_state(spec: GameSpec) -> _State:
    n = spec.num_players
    stacks = [spec.stack_bb] * n
    committed = [0.0] * n

    if spec.ante_bb > 0:
        if spec.bb_ante:
            posted = min(spec.ante_bb, stacks[1])
            stacks[1] -= posted
            committed[1] += posted
        else:
            for i in range(n):
                posted = min(spec.ante_bb, stacks[i])
                stacks[i] -= posted
                committed[i] += posted

    sb_amt = min(spec.sb, stacks[0])
    stacks[0] -= sb_amt
    committed[0] += sb_amt
    bb_amt = min(spec.bb, stacks[1])
    stacks[1] -= bb_amt
    committed[1] += bb_amt

    order = [p for p in range(2, n)] + [0, 1]
    to_act = tuple((p, True) for p in order)

    return _State(
        stacks_bb=tuple(stacks),
        committed_bb=tuple(committed),
        active=tuple(True for _ in range(n)),
        to_act=to_act,
        last_raise_bb=spec.bb,
        history=(),
    )


def _apply_action(spec: GameSpec, state: _State, player: int, action: str, new_committed_for_player: float) -> _State:
    n = len(state.active)
    rest = state.to_act[1:]

    if action == "fold":
        new_active = tuple(a if i != player else False for i, a in enumerate(state.active))
        return _State(state.stacks_bb, state.committed_bb, new_active, rest, state.last_raise_bb, state.history + ("f",))

    delta = new_committed_for_player - state.committed_bb[player]
    new_stacks = tuple(s - delta if i == player else s for i, s in enumerate(state.stacks_bb))
    new_committed = tuple(new_committed_for_player if i == player else c for i, c in enumerate(state.committed_bb))

    if action in ("check", "call"):
        label = "x" if action == "check" else "c"
        return _State(new_stacks, new_committed, state.active, rest, state.last_raise_bb, state.history + (label,))

    # bet / raise
    current_max = max(state.committed_bb)
    increment = new_committed_for_player - current_max
    is_all_in = new_stacks[player] <= 1e-9
    is_full_raise = increment >= state.last_raise_bb - 1e-9
    label = f"{'allin' if is_all_in else ('bet' if current_max <= 1e-9 else 'raise')}_{new_committed_for_player:g}"

    if is_full_raise:
        new_to_act = tuple((p, True) for p in _rotation_from(player + 1, n) if p != player and state.active[p])
        new_last_raise = increment
    else:
        # Short all-in: does NOT reopen the action. Players still queued (in `rest`)
        # keep whatever raise rights they already had -- untouched. Players who had
        # ALREADY acted on the current bet level (active, not the raiser, not still
        # queued) must respond to the new higher amount, but call/fold only.
        still_queued = {p for p, _ in rest}
        already_acted = [
            (p, False)
            for p in _rotation_from(player + 1, n)
            if p != player and state.active[p] and p not in still_queued
        ]
        new_to_act = tuple(rest) + tuple(already_acted)
        new_last_raise = state.last_raise_bb

    return _State(new_stacks, new_committed, state.active, new_to_act, new_last_raise, state.history + (label,))


def _build(spec: GameSpec, state: _State) -> Node:
    n_active = sum(state.active)
    pot = sum(state.committed_bb)

    if n_active == 1:
        winner = state.active.index(True)
        payoffs = tuple((pot if i == winner else 0.0) - c for i, c in enumerate(state.committed_bb))
        return Terminal("fold", pot, state.active, payoffs, state.history)

    if not state.to_act:
        return Terminal("showdown", pot, state.active, None, state.history)

    player, can_raise = state.to_act[0]
    current_max = max(state.committed_bb)
    to_call = current_max - state.committed_bb[player]
    stack = state.stacks_bb[player]

    actions: dict[str, Node] = {}

    if to_call <= 1e-9:
        actions["check"] = _build(spec, _apply_action(spec, state, player, "check", state.committed_bb[player]))
        if stack > 1e-9:
            for size in _legal_bet_sizes(spec, pot, stack):
                new_committed = state.committed_bb[player] + size
                actions[f"bet_{size:g}"] = _build(spec, _apply_action(spec, state, player, "bet", new_committed))
    else:
        actions["fold"] = _build(spec, _apply_action(spec, state, player, "fold", 0.0))
        call_amt = min(to_call, stack)
        actions["call"] = _build(
            spec, _apply_action(spec, state, player, "call", state.committed_bb[player] + call_amt)
        )
        if can_raise and stack > to_call + 1e-9:
            for inc in _legal_raise_increments(spec, pot, to_call, stack, state.last_raise_bb):
                actions[f"raise_{inc:g}"] = _build(
                    spec, _apply_action(spec, state, player, "raise", current_max + inc)
                )

    return Decision(player, pot, to_call, state.stacks_bb, actions, state.history)


def build_tree(spec: GameSpec) -> Tree:
    """Build the full preflop betting tree for `spec`. Every legal action at
    every decision comes from spec.bet_sizes / spec.stack_bb / the current
    state -- see this module's docstring for what "preflop-only" means and
    why that's the correctly-scoped tree for what Phase 10 actually solves."""
    return Tree(_build(spec, _initial_state(spec)), spec)
