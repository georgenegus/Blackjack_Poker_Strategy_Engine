"""Phase 10: the real preflop game (betting tree + 169-class card
abstraction + equity-realisation terminal values), the CLI solve driver's
shared library, and the runtime advice lookup. See
markdowns/poker/poker_build_plan_v1.md Phase 10.

Terminal values -- the plan's largest modelling compromise, stated plainly
here because it is the single most important thing to understand about
every number this module produces. Lines that end preflop (a fold, or an
all-in that reaches showdown) have EXACT values -- no cards are needed at
all for a fold, and a showdown-after-all-in uses the exact combo-weighted
169x169 equity matrix (Phase 3), not an approximation. Lines that instead
see a flop (betting closes with 2+ players still active and more than one
of them still has chips behind) do NOT have exact values here -- solving the
real postflop game is out of scope for this project (Appendix B item 4).
v1 approximates a flop-seeing line's value as the SAME 169x169 all-in
equity, shifted toward the in-position player by an amount that scales with
how close the matchup is (peaking at a coinflip, vanishing for a near-lock)
and with the stack-to-pot ratio (more room for postflop skill to matter at
higher SPR). This is a real, stated compromise -- more consequential than
the blackjack area's `2 x one_hand_EV` split approximation, which is worth
~0.01% and was validated against published charts built on the same
assumption. There is no published reference built on the SAME assumption
here. Consequences that follow from this, and must be respected everywhere
this module's numbers are used: the solved strategy is an equilibrium OF
THE APPROXIMATED GAME, not of real no-limit hold'em; its exploitability is
measured against that same approximated game; and neither number transfers
to a real table without that qualification attached. The realisation
parameters are recorded in every solved strategy file precisely because
changing them changes the answer -- they are part of the game's definition,
not a tuning knob applied after the fact.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import numpy as np

from src.poker import tree as _tree
from src.poker.pushfold import _load_matrix
from src.poker.ranges import CLASS_LABELS
from src.poker.spec import GameSpec

STRATEGY_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "poker" / "strategy"

POSITION_BONUS_MAX = 0.15
SPR_CAP = 10.0


def _position_skew(spr: float) -> float:
    """Max equity-realisation shift attributable to position, scaling with
    SPR (more room for postflop play to matter at a higher stack-to-pot
    ratio); capped so it never exceeds POSITION_BONUS_MAX."""
    return POSITION_BONUS_MAX * min(spr / SPR_CAP, 1.0)


def _apply_realization(raw_equity0: float, spr: float) -> float:
    """Player 0 (SB/BTN preflop, but IN POSITION on every postflop street in
    heads-up -- a real, well-known quirk of HU play, not a mistake) gets an
    equity-realisation bonus; player 1 (BB, out of position postflop) the
    exactly corresponding penalty -- zero-sum BY CONSTRUCTION (player 1's
    realised equity is always 1 - this value, never computed
    independently, which is what keeps the approximated game a valid
    zero-sum game CFR can solve). The bonus is scaled by closeness
    (4*p*(1-p), peaking at a coinflip, vanishing at the extremes) so it can
    never push a realised equity outside [0, 1] or invert a genuinely
    lopsided matchup into a different favourite."""
    skew = _position_skew(spr)
    closeness = 4.0 * raw_equity0 * (1.0 - raw_equity0)
    return min(max(raw_equity0 + skew * closeness, 0.0), 1.0)


class PreflopState(NamedTuple):
    hole: tuple[int, int]  # (player0's class index, player1's class index) into CLASS_LABELS
    betting: "_tree._State"


class PreflopGame:
    """The extensive-form game src.poker.cfr traverses: GameSpec's preflop
    betting tree (src.poker.tree's internal state machinery, reused
    directly rather than re-implemented) plus the lossless 169-class deal
    and the equity-realisation terminal-value approximation described in
    this module's docstring."""

    def __init__(self, spec: GameSpec):
        self.spec = spec
        m = _load_matrix()
        self._matrix = m["matrix"]
        self._label_index = m["index"]
        weights = np.array([m["class_weight"][label] for label in CLASS_LABELS], dtype=np.float64)
        probs = np.outer(weights, weights).ravel()
        self._deal_outcomes = [
            (PreflopState((i, j), _tree._initial_state(spec)), float(probs[i * 169 + j]) / probs.sum())
            for i in range(169)
            for j in range(169)
        ]

    def is_chance(self, history) -> bool:
        return history == ()

    def chance_outcomes(self, history):
        return self._deal_outcomes

    def is_terminal(self, history) -> bool:
        if history == ():
            return False
        state = history.betting
        return sum(state.active) == 1 or not state.to_act

    def current_player(self, history) -> int:
        return history.betting.to_act[0][0]

    def legal_actions(self, history) -> tuple[str, ...]:
        state = history.betting
        player, can_raise = state.to_act[0]
        current_max = max(state.committed_bb)
        to_call = current_max - state.committed_bb[player]
        stack = state.stacks_bb[player]
        pot = sum(state.committed_bb)

        actions = []
        if to_call <= 1e-9:
            actions.append("check")
            if stack > 1e-9:
                for size in _tree._legal_bet_sizes(self.spec, pot, stack):
                    actions.append(f"bet_{size:g}")
        else:
            actions.append("fold")
            actions.append("call")
            if can_raise and stack > to_call + 1e-9:
                for inc in _tree._legal_raise_increments(self.spec, pot, to_call, stack, state.last_raise_bb):
                    actions.append(f"raise_{inc:g}")
        return tuple(actions)

    def next_history(self, history, action: str) -> PreflopState:
        state = history.betting
        player = state.to_act[0][0]

        if action == "fold":
            new_state = _tree._apply_action(self.spec, state, player, "fold", 0.0)
        elif action == "check":
            new_state = _tree._apply_action(self.spec, state, player, "check", state.committed_bb[player])
        elif action == "call":
            current_max = max(state.committed_bb)
            call_amt = min(current_max - state.committed_bb[player], state.stacks_bb[player])
            new_state = _tree._apply_action(self.spec, state, player, "call", state.committed_bb[player] + call_amt)
        elif action.startswith("bet_"):
            size = float(action[len("bet_") :])
            new_state = _tree._apply_action(self.spec, state, player, "bet", state.committed_bb[player] + size)
        elif action.startswith("raise_"):
            inc = float(action[len("raise_") :])
            current_max = max(state.committed_bb)
            new_state = _tree._apply_action(self.spec, state, player, "raise", current_max + inc)
        else:
            raise ValueError(f"unrecognised action: {action!r}")

        return history._replace(betting=new_state)

    def infoset_key(self, history, player: int) -> tuple:
        return (history.hole[player], history.betting.history)

    def utility(self, history, player: int) -> float:
        """Rake (Implementation section 1 of the plan's Phase 10 entry:
        "rake from spec.pot_after_rake") is applied here, the one place per
        spec.pot_after_rake's own docstring rake is ever computed -- a fold
        terminal never sees a flop (saw_flop=False, so no_flop_no_drop's
        default exempts it), a showdown terminal always does
        (saw_flop=True). Both branches call the SAME spec.pot_after_rake
        rather than reimplementing its no_flop_no_drop/cap logic here, so
        this game's rake treatment can never drift from GameSpec's own
        definition of it."""
        state = history.betting
        raw_pot = sum(state.committed_bb)
        active = state.active

        if sum(active) == 1:
            winner = active.index(True)
            pot = self.spec.pot_after_rake(raw_pot, saw_flop=False)
            payoff0 = (pot if winner == 0 else 0.0) - state.committed_bb[0]
        else:
            pot = self.spec.pot_after_rake(raw_pot, saw_flop=True)
            i, j = history.hole
            raw_equity0 = float(self._matrix[i, j])
            spr = min(state.stacks_bb) / raw_pot if raw_pot > 1e-9 else float("inf")
            realized0 = _apply_realization(raw_equity0, spr)
            payoff0 = pot * realized0 - state.committed_bb[0]

        return payoff0 if player == 0 else -payoff0

    def tree_size(self) -> tuple[int, int, int]:
        """(n_nodes, n_infosets, n_terminals) of the card-agnostic betting
        tree alone -- the number of DISTINCT (infoset, hole-class)
        combinations this game can reach is n_infosets * 169, since every
        betting-tree infoset is reached under every one of the 169 possible
        own-hand classes."""
        return _tree.build_tree(self.spec).size()


POSITION_NAMES = {0: "BTN", 1: "BB"}  # heads-up: player 0 is SB/BTN combined


@dataclass
class Advice:
    action_frequencies: dict[str, float]
    is_close: bool  # top two actions within a small EV-adjacent frequency margin


def advise(hand: str, position: str, action_history: list[str], spec: GameSpec) -> Advice:
    """Look up the solved preflop strategy for `hand` (169-class notation,
    e.g. "AJs") at `position` ("BTN" or "BB") having observed
    `action_history` so far, from the cached
    data/poker/strategy/{spec.key()}/preflop.json (built by
    scripts/poker/solve_preflop.py). Returns action frequencies that sum to
    exactly 1.0 (renormalised over whatever the solve actually recorded,
    which already excludes near-zero-probability actions) and an `is_close`
    flag when the top two actions are within 0.1 of each other in
    frequency -- a rough proxy for "this cell is a genuine mix, not a
    lopsided decision", since solved frequency alone (unlike a real EV gap)
    is what's stored in the cached file.
    """
    path = STRATEGY_DIR / spec.key() / "preflop.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No solved preflop strategy for {spec.key()}. Run "
            f"`py scripts/poker/solve_preflop.py --spec {spec.key()}` first."
        )
    data = json.loads(path.read_text())

    situation = "-".join(action_history) if action_history else "open"
    label = f"{position}:{situation}"
    situations = data["strategy"]
    if label not in situations:
        raise KeyError(f"no solved situation {label!r} for spec {spec.key()}")
    hand_freqs = situations[label].get(hand)
    if hand_freqs is None:
        raise KeyError(f"no solved frequencies for hand {hand!r} at {label!r}")

    total = sum(hand_freqs.values())
    normalized = {a: f / total for a, f in hand_freqs.items()}
    sorted_freqs = sorted(normalized.values(), reverse=True)
    is_close = len(sorted_freqs) >= 2 and (sorted_freqs[0] - sorted_freqs[1]) < 0.1

    return Advice(normalized, is_close)
