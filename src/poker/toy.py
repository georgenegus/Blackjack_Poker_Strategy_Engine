"""Phase 8 (Kuhn poker was built early, in Phase 7): tiny extensive-form
games with a known equilibrium, used to validate the CFR implementation in
src/poker/cfr.py against ground truth that needs no card evaluator, no
betting tree, and no abstraction. See
markdowns/poker/poker_build_plan_v1.md Phase 7/8 and Appendix A.5.

Every game here implements the small extensive-form interface src.poker.cfr
traverses generically (is_chance/is_terminal/current_player/legal_actions/
chance_outcomes/next_history/infoset_key/utility) -- the same interface the
real preflop tree (src.poker.tree) will eventually be adapted to, so CFR's
core algorithm is never toy-game-specific. src.poker.cfr.solve() always
starts traversal from the literal empty tuple `()` for ANY game, so every
game here must treat `()` as its single chance (deal) node; what a game's
`history` looks like AFTER that first transition is entirely up to it --
KuhnPoker stays a flat tuple throughout, LeducPoker switches to a richer
NamedTuple once the deal has happened.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import permutations
from typing import NamedTuple

import numpy as np
from scipy.optimize import linprog


class KuhnPoker:
    """Three cards (J=0, Q=1, K=2, higher wins), one-chip ante, one-chip bet,
    two players. Actions are always "p" (pass -- check if no bet is out,
    fold if facing one) or "b" (bet -- open if no bet is out, call if facing
    one), matching the standard Kuhn-poker notation. A `history` is
    `(card0, card1, *actions)`; the empty tuple is the single chance node
    (the deal).
    """

    CARDS = (0, 1, 2)
    N_PLAYERS = 2

    _TERMINAL_ACTION_SEQS = frozenset({("p", "p"), ("b", "p"), ("b", "b"), ("p", "b", "p"), ("p", "b", "b")})

    def is_chance(self, history: tuple) -> bool:
        return history == ()

    def chance_outcomes(self, history: tuple) -> list[tuple[tuple, float]]:
        deals = [(c0, c1) for c0, c1 in permutations(self.CARDS, 2)]
        p = 1.0 / len(deals)
        return [(deal, p) for deal in deals]

    def is_terminal(self, history: tuple) -> bool:
        return len(history) >= 2 and history[2:] in self._TERMINAL_ACTION_SEQS

    def current_player(self, history: tuple) -> int:
        return len(history[2:]) % 2

    def legal_actions(self, history: tuple) -> tuple[str, ...]:
        return ("p", "b")

    def next_history(self, history: tuple, action: str) -> tuple:
        return history + (action,)

    def infoset_key(self, history: tuple, player: int) -> tuple:
        return (history[player], history[2:])

    def utility(self, history: tuple, player: int) -> float:
        """Player `player`'s net payoff (chips won/lost relative to their
        ante), zero-sum -- utility(h, 0) == -utility(h, 1) always."""
        c0, c1 = history[0], history[1]
        actions = history[2:]
        p0_wins_showdown = c0 > c1

        if actions == ("p", "p"):
            payoff0 = 1.0 if p0_wins_showdown else -1.0
        elif actions == ("b", "p"):
            payoff0 = 1.0  # player 1 folded
        elif actions == ("b", "b"):
            payoff0 = 2.0 if p0_wins_showdown else -2.0
        elif actions == ("p", "b", "p"):
            payoff0 = -1.0  # player 0 folded
        elif actions == ("p", "b", "b"):
            payoff0 = 2.0 if p0_wins_showdown else -2.0
        else:
            raise ValueError(f"not a terminal action sequence: {actions!r}")

        return payoff0 if player == 0 else -payoff0


class LeducHistory(NamedTuple):
    card0: int
    card1: int
    round1: tuple[str, ...]
    public: int | None
    round2: tuple[str, ...]


def _round_status(actions: tuple[str, ...]) -> str:
    """"open" (more action needed this round), "closed" (round over, no
    fold), or "fold" (round AND hand over). Actions are "p" (check if no bet
    is out, else fold), "c" (call, always closes the round), "b" (bet if no
    bet is out, else raise -- up to LeducPoker.RAISE_CAP total per round)."""
    facing_bet = False
    just_checked = False
    for a in actions:
        if a == "b":
            facing_bet = True
            just_checked = False
        elif a == "c":
            return "closed"
        elif a == "p":
            if facing_bet:
                return "fold"
            if just_checked:
                return "closed"
            just_checked = True
    return "open"


def _round_contributions(actions: tuple[str, ...], bet_size: float) -> list[float]:
    """Chips each player has put into the pot THIS round, given the action
    sequence and the round's fixed bet size (fixed-limit: each "b" -- bet or
    raise alike -- adds exactly bet_size on top of whatever's already
    facing)."""
    contrib = [0.0, 0.0]
    current_bet = 0.0
    player = 0
    for a in actions:
        if a == "b":
            current_bet += bet_size
            contrib[player] = current_bet
        elif a == "c":
            contrib[player] = current_bet
        player = 1 - player
    return contrib


def _legal_actions_for_round(actions: tuple[str, ...], cap: int) -> tuple[str, ...]:
    facing_bet = bool(actions) and actions[-1] == "b"
    if not facing_bet:
        return ("p", "b")
    n_bets = sum(1 for a in actions if a == "b")
    return ("p", "c", "b") if n_bets < cap else ("p", "c")


class LeducPoker:
    """Six cards -- two suits x {J=0, Q=1, K=2} -- one-chip ante, two
    betting rounds (bet size 2 before the public card, 4 after), fixed-limit
    with a cap of RAISE_CAP=2 total bets per round (an opening bet plus one
    raise). Player 0 acts first in both rounds. A pair (private card rank ==
    public card rank) beats any non-pair; among non-pairs, higher private
    rank wins; equal non-pair ranks split the pot exactly (possible since
    each rank has two copies in the deck).
    """

    N_CARDS = 6
    ANTE = 1.0
    BET_SIZES = (2.0, 4.0)
    RAISE_CAP = 2

    def is_chance(self, history) -> bool:
        if history == ():
            return True
        return history.public is None and _round_status(history.round1) == "closed"

    def chance_outcomes(self, history):
        if history == ():
            deals = [(c0, c1) for c0 in range(self.N_CARDS) for c1 in range(self.N_CARDS) if c0 != c1]
            p = 1.0 / len(deals)
            return [(LeducHistory(c0, c1, (), None, ()), p) for c0, c1 in deals]
        used = {history.card0, history.card1}
        remaining = [c for c in range(self.N_CARDS) if c not in used]
        p = 1.0 / len(remaining)
        return [(history._replace(public=c), p) for c in remaining]

    def is_terminal(self, history) -> bool:
        if history == ():
            return False
        r1 = _round_status(history.round1)
        if r1 == "fold":
            return True
        if r1 != "closed" or history.public is None:
            return False
        return _round_status(history.round2) in ("fold", "closed")

    def current_player(self, history) -> int:
        if history.public is None:
            return len(history.round1) % 2
        return len(history.round2) % 2

    def legal_actions(self, history) -> tuple[str, ...]:
        actions = history.round1 if history.public is None else history.round2
        return _legal_actions_for_round(actions, self.RAISE_CAP)

    def next_history(self, history, action: str):
        if history.public is None:
            return history._replace(round1=history.round1 + (action,))
        return history._replace(round2=history.round2 + (action,))

    def infoset_key(self, history, player: int) -> tuple:
        card = history.card0 if player == 0 else history.card1
        return (card, history.round1, history.public, history.round2)

    def _compare_hands(self, card0: int, card1: int, public: int) -> int:
        """1 if player 0 wins, -1 if player 1 wins, 0 for a tie."""
        r0, r1, rp = card0 // 2, card1 // 2, public // 2
        p0_pair, p1_pair = r0 == rp, r1 == rp
        if p0_pair != p1_pair:
            return 1 if p0_pair else -1
        if r0 != r1:
            return 1 if r0 > r1 else -1
        return 0

    def utility(self, history, player: int) -> float:
        r1c = _round_contributions(history.round1, self.BET_SIZES[0])
        r2c = _round_contributions(history.round2, self.BET_SIZES[1]) if history.public is not None else [0.0, 0.0]
        total = [self.ANTE + r1c[i] + r2c[i] for i in range(2)]
        pot = sum(total)

        r1_status = _round_status(history.round1)
        if r1_status == "fold":
            folder = (len(history.round1) - 1) % 2
            result = -1 if folder == 0 else 1
        else:
            r2_status = _round_status(history.round2)
            if r2_status == "fold":
                folder = (len(history.round2) - 1) % 2
                result = -1 if folder == 0 else 1
            else:
                result = self._compare_hands(history.card0, history.card1, history.public)

        if result > 0:
            payoff0 = pot - total[0]
        elif result < 0:
            payoff0 = -total[0]
        else:
            payoff0 = pot / 2.0 - total[0]
        return payoff0 if player == 0 else -payoff0


# ---------------------------------------------------------------------------
# Sequence-form LP -- an EXACT Nash equilibrium value, independent of CFR
# ---------------------------------------------------------------------------

EMPTY_SEQ: tuple = ()


@dataclass
class SequenceFormGame:
    """The sequence-form compilation of a two-player zero-sum extensive-form
    game: for each player, a "realization plan" flow structure over
    SEQUENCES (not raw actions) -- a sequence is that player's OWN history
    of (infoset, action) pairs, which is why two histories that reach the
    "same" raw action label but differ in hidden information (e.g. a
    different private card) are different sequences even though an opponent
    watching only public actions couldn't tell them apart. This is what lets
    the LP below stay linear in tree size rather than exponential (a reduced
    normal-form pure-strategy count is roughly `actions ** infosets` -- for
    Leduc's 468 infosets per player, astronomically larger than the ~1,000
    sequences the same player actually has).
    """

    seq_index: list[dict]  # [player0 sequence -> index, player1 sequence -> index]
    infoset_parent_seq: list[dict]  # [player0 infoset -> parent sequence, player1's]
    infoset_actions: list[dict]  # [player0 infoset -> legal actions tuple, player1's]
    payoff: np.ndarray  # (n_seq0, n_seq1): sum of chance_prob * utility0 per (seq0, seq1) pair


def _build_sequence_form(game) -> SequenceFormGame:
    seq_index = [{EMPTY_SEQ: 0}, {EMPTY_SEQ: 0}]
    infoset_parent_seq: list[dict] = [{}, {}]
    infoset_actions: list[dict] = [{}, {}]
    terminal_contribs: dict = defaultdict(float)  # (seq0, seq1) -> accumulated chance_prob * utility0

    def walk(history, seq: list[tuple], chance_prob: float):
        if game.is_terminal(history):
            terminal_contribs[(seq[0], seq[1])] += chance_prob * game.utility(history, 0)
            return
        if game.is_chance(history):
            for next_history, p in game.chance_outcomes(history):
                walk(next_history, seq, chance_prob * p)
            return

        player = game.current_player(history)
        infoset = game.infoset_key(history, player)
        actions = game.legal_actions(history)

        if infoset not in infoset_parent_seq[player]:
            infoset_parent_seq[player][infoset] = seq[player]
            infoset_actions[player][infoset] = tuple(actions)
        else:
            assert infoset_parent_seq[player][infoset] == seq[player], (
                f"perfect-recall violation: infoset {infoset} reached via two different sequences"
            )

        for a in actions:
            new_seq_p = seq[player] + ((infoset, a),)
            table = seq_index[player]
            if new_seq_p not in table:
                table[new_seq_p] = len(table)
            new_seq = list(seq)
            new_seq[player] = new_seq_p
            walk(game.next_history(history, a), new_seq, chance_prob)

    walk((), [EMPTY_SEQ, EMPTY_SEQ], 1.0)

    n0, n1 = len(seq_index[0]), len(seq_index[1])
    payoff = np.zeros((n0, n1))
    for (s0, s1), value in terminal_contribs.items():
        payoff[seq_index[0][s0], seq_index[1][s1]] = value

    return SequenceFormGame(seq_index, infoset_parent_seq, infoset_actions, payoff)


def _flow_constraints(seq_index: dict, infoset_parent_seq: dict, infoset_actions: dict):
    """Player-i equality constraints: x[empty]=1, and for each infoset h with
    parent sequence p: sum_{a in A(h)} x[p+((h,a))] - x[p] = 0. Returns
    (A_eq, b_eq) in scipy.optimize.linprog's convention."""
    n = len(seq_index)
    rows = []
    b = []

    empty_row = np.zeros(n)
    empty_row[seq_index[EMPTY_SEQ]] = 1.0
    rows.append(empty_row)
    b.append(1.0)

    for infoset, parent in infoset_parent_seq.items():
        row = np.zeros(n)
        for a in infoset_actions[infoset]:
            row[seq_index[parent + ((infoset, a),)]] += 1.0
        row[seq_index[parent]] -= 1.0
        rows.append(row)
        b.append(0.0)

    return np.array(rows), np.array(b)


def solve_sequence_form_lp(game) -> float:
    """The EXACT Nash equilibrium value to player 0, via the sequence-form
    LP -- see SequenceFormGame's docstring for why sequence-form (not
    reduced normal form) is the only tractable exact representation here.
    Solves:
        max v_root
        s.t. x[empty] = 1
             player-0 flow constraints (x >= 0)
             for every player-1 sequence tau:
                 parent_v(tau) - sum_{child infosets h' of tau} v[h'] <= payoff[:, tau] . x
    where parent_v(tau) is v_root if tau is empty, else the value variable
    for whichever player-1 infoset OWNS tau's final action. This is the
    dual, w.r.t. player 1's OWN flow-constrained LP, of "minimize x^T A y
    over y" -- see this function's derivation in the Phase 8 tracking-table
    entry for the full reasoning; verified independently to reproduce
    Kuhn's exact analytic value -1/18 before ever being trusted on Leduc.
    """
    sf = _build_sequence_form(game)
    n0, n1 = len(sf.seq_index[0]), len(sf.seq_index[1])

    p1_infosets = list(sf.infoset_parent_seq[1].keys())
    v_index = {"root": 0}
    for h in p1_infosets:
        v_index[h] = len(v_index)
    n_v = len(v_index)

    n_vars = n0 + n_v
    A_eq0, b_eq0 = _flow_constraints(sf.seq_index[0], sf.infoset_parent_seq[0], sf.infoset_actions[0])
    A_eq = np.zeros((A_eq0.shape[0], n_vars))
    A_eq[:, :n0] = A_eq0
    b_eq = b_eq0

    children_of_seq: dict = defaultdict(list)
    for h, parent in sf.infoset_parent_seq[1].items():
        children_of_seq[parent].append(h)
    owner_of_seq: dict = {EMPTY_SEQ: "root"}
    for h, actions in sf.infoset_actions[1].items():
        parent = sf.infoset_parent_seq[1][h]
        for a in actions:
            owner_of_seq[parent + ((h, a),)] = h

    A_ub = np.zeros((n1, n_vars))
    b_ub = np.zeros(n1)
    for tau, tau_idx in sf.seq_index[1].items():
        owner = owner_of_seq[tau]
        A_ub[tau_idx, n0 + v_index[owner]] += 1.0
        for child in children_of_seq.get(tau, []):
            A_ub[tau_idx, n0 + v_index[child]] -= 1.0
        A_ub[tau_idx, :n0] -= sf.payoff[:, tau_idx]
        b_ub[tau_idx] = 0.0

    c = np.zeros(n_vars)
    c[n0 + v_index["root"]] = -1.0  # linprog minimizes; maximize v_root == minimize -v_root

    bounds = [(0, None)] * n0 + [(None, None)] * n_v

    result = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not result.success:
        raise RuntimeError(f"sequence-form LP failed to solve: {result.message}")
    return -result.fun
