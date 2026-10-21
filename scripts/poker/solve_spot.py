"""Phase 10: bounded single-spot postflop solve. See
markdowns/poker/poker_build_plan_v1.md Phase 10.

    py scripts/poker/solve_spot.py --board AsKd7h2c9s --hero-range QQ+,AKs \
        --villain-range 50% --pot 20 --stack 80 --iterations 200000 --max-seconds 60

Deliberately scoped to a COMPLETE board (the river) rather than a general
flop/turn spot. Phase 10's preflop solve already documents its equity-
realisation compromise at length (advisor.py's module docstring) for lines
that see a flop with more streets still to come -- a general postflop spot
solver would need that same kind of approximation (or full multi-street tree
chaining, explicitly out of scope per the plan's "Bounded postflop scope"
decision, Appendix B item 4) for any board shorter than the river.
Restricting to river spots sidesteps the compromise entirely: with all 5
board cards fixed, every showdown has an EXACT value via
evaluator.evaluate(hole + board) -- no approximation anywhere in this
module, unlike PreflopGame. This is a real, deliberate scope decision, not a
shortcut: it means solve_spot.py answers "given we've already reached the
river with these two ranges, this pot, and these stacks, how should this
betting round be played" -- not "solve the flop" or "solve the turn".

Sunk-pot convention: `pot_bb` (chips already committed on earlier streets,
which this module does not model) is split EVENLY between the two players
as each one's starting `committed_bb` for this street. This is a pure
bookkeeping convenience with NO effect on the solved strategy: CFR's regret
computation only ever depends on DIFFERENCES between an action's value and
the node's value at the same information set, and a constant per-player
offset (however the sunk pot was actually contributed) cancels out of every
such difference identically. It does mean the reported game_value/EV numbers
are relative to "each player already has pot_bb/2 in", not to each player's
real historical net -- stated once here rather than re-derived by a reader
of this module's output.

Bounded by construction (this file's Problem statement in the plan, and the
same constraint the blackjack area's /api/simulate route already lives
under): an unbounded solver behind a runtime entry point is a
denial-of-service risk. `solve_spot` accepts both an iteration cap and a
wall-clock cap (`max_seconds`) and never exceeds either -- it calibrates on
a small warm-up batch to estimate iterations/second (which varies enormously
with range width and bet-size count), then runs however many further
iterations fit in the remaining wall-clock budget, capped at `iterations`
regardless.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.poker import tree as _tree
from src.poker.cards import card_ids, id_to_str
from src.poker.cfr import solve_mccfr
from src.poker.evaluator import evaluate
from src.poker.exploit import sampled_exploitability
from src.poker.ranges import Range
from src.poker.spec import GameSpec

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
POSITION_NAMES = {0: "OOP", 1: "IP"}  # postflop: player 0 acts first (out of position)


class SpotState(NamedTuple):
    hole: tuple[tuple[int, int], tuple[int, int]]  # (player0's combo, player1's combo)
    betting: "_tree._State"


class SpotGame:
    """The extensive-form game src.poker.cfr traverses for one bounded,
    fully-specified river spot: a fixed 5-card board, two card-removal-
    conditioned ranges, a starting pot, and stacks behind. See this module's
    docstring for the river-only scope decision and the sunk-pot convention.
    Reuses src.poker.tree's low-level betting-state machinery directly
    (exactly as PreflopGame does), never src.poker.tree.build_tree, since
    that helper assumes preflop blind-posting this spot doesn't have."""

    def __init__(
        self,
        board: tuple[int, ...],
        hero_range: Range,
        villain_range: Range,
        pot_bb: float,
        stack_bb: float,
        bet_sizes: tuple[float, ...] = GameSpec().bet_sizes,
        rake_pct: float = 0.0,
        rake_cap_bb: float = 0.0,
    ):
        if len(board) != 5:
            raise ValueError(f"solve_spot is river-only (see this module's docstring); got a {len(board)}-card board")
        if pot_bb <= 0.0 or stack_bb <= 0.0:
            raise ValueError("pot_bb and stack_bb must both be positive")

        self.board = tuple(board)
        self.pot_bb = float(pot_bb)
        self.stack_bb = float(stack_bb)
        # bet_sizes/allow_allin/bb are the only GameSpec fields this game consults
        # (via _tree's helpers below); this game manages its own starting state
        # rather than _tree._initial_state, so stack_bb/sb/bb on the spec itself
        # are never consulted.
        self.spec = GameSpec(bet_sizes=bet_sizes, rake_pct=rake_pct, rake_cap_bb=rake_cap_bb)

        board_mask = 0
        for c in board:
            board_mask |= 1 << c
        hero = hero_range.conditioned(board_mask)
        villain = villain_range.conditioned(board_mask)

        half_pot = self.pot_bb / 2.0
        start_state = _tree._State(
            stacks_bb=(self.stack_bb, self.stack_bb),
            committed_bb=(half_pot, half_pot),
            active=(True, True),
            to_act=((0, True), (1, True)),
            last_raise_bb=self.spec.bb,
            history=(),
        )

        outcomes: list[tuple[SpotState, float]] = []
        total_weight = 0.0
        for h, wh in hero.combos().items():
            if wh == 0.0:
                continue
            for v, wv in villain.combos().items():
                if wv == 0.0:
                    continue
                if h[0] == v[0] or h[0] == v[1] or h[1] == v[0] or h[1] == v[1]:
                    continue
                w = wh * wv
                total_weight += w
                outcomes.append((SpotState((h, v), start_state), w))
        if total_weight == 0.0:
            raise ValueError("no valid (non-conflicting) hero/villain combo pairs for this board")

        self._deal_outcomes = [(s, w / total_weight) for s, w in outcomes]
        self._rank_cache: dict[tuple[tuple[int, int], tuple[int, int]], tuple[int, int]] = {}

    def _ranks(self, hole: tuple[tuple[int, int], tuple[int, int]]) -> tuple[int, int]:
        cached = self._rank_cache.get(hole)
        if cached is not None:
            return cached
        h, v = hole
        ranks = (evaluate(h + self.board), evaluate(v + self.board))
        self._rank_cache[hole] = ranks
        return ranks

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

    def next_history(self, history, action: str) -> SpotState:
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
        state = history.betting
        raw_pot = sum(state.committed_bb)
        active = state.active

        if sum(active) == 1:
            winner = active.index(True)
            pot = self.spec.pot_after_rake(raw_pot, saw_flop=True)
            payoff0 = (pot if winner == 0 else 0.0) - state.committed_bb[0]
        else:
            pot = self.spec.pot_after_rake(raw_pot, saw_flop=True)
            rank0, rank1 = self._ranks(history.hole)
            if rank0 < rank1:
                share0 = pot
            elif rank1 < rank0:
                share0 = 0.0
            else:
                share0 = pot / 2.0
            payoff0 = share0 - state.committed_bb[0]

        return payoff0 if player == 0 else -payoff0


def solve_spot(
    game: SpotGame,
    iterations: int,
    max_seconds: float,
    seed: int | None = None,
    warmup_iterations: int = 200,
) -> tuple:
    """MCCFR, bounded by BOTH `iterations` and `max_seconds` -- never just
    one, per this module's "bounded by construction" requirement. Runs a
    small `warmup_iterations` batch first to measure iterations/second on
    THIS spot's actual tree size, then runs however many further iterations
    fit in the remaining wall-clock budget, capped at `iterations`
    regardless. Returns (SolveResult, iterations_run, elapsed_seconds)."""
    rng_seed = seed if seed is not None else 0
    t0 = time.perf_counter()
    warmup_n = min(warmup_iterations, iterations)
    result = solve_mccfr(game, iterations=warmup_n, seed=rng_seed, exact_value=False, value_samples=1)
    elapsed = time.perf_counter() - t0

    if warmup_n >= iterations or elapsed >= max_seconds:
        return result, warmup_n, elapsed

    rate = warmup_n / elapsed if elapsed > 1e-9 else float("inf")
    remaining_seconds = max_seconds - elapsed
    remaining_iterations = min(iterations - warmup_n, int(rate * remaining_seconds))
    if remaining_iterations <= 0:
        return result, warmup_n, elapsed

    total_iterations = warmup_n + remaining_iterations
    result = solve_mccfr(game, iterations=total_iterations, seed=rng_seed, exact_value=False, value_samples=20_000)
    elapsed = time.perf_counter() - t0
    return result, total_iterations, elapsed


def format_strategy(avg_strategy: dict, game: SpotGame) -> dict:
    """{"{OOP|IP}:{situation}": {combo: {action: frequency}}}, situation =
    "-".join(betting history) or "start". Unlike solve_preflop.py's
    format_strategy, this walks the actual game tree from the deal outcomes
    (there is no reusable card-agnostic tree to walk independently here --
    SpotGame's combos are concrete two-card tuples specific to one
    board/range pair, not the 169-class registry) to recover each visited
    infoset's legal action names, which avg_strategy's own arrays don't
    carry on their own."""
    seen_actions: dict = {}

    def walk(history):
        if game.is_terminal(history):
            return
        player = game.current_player(history)
        infoset = game.infoset_key(history, player)
        actions = game.legal_actions(history)
        seen_actions.setdefault(infoset, actions)
        for a in actions:
            walk(game.next_history(history, a))

    for hole, _ in game._deal_outcomes:
        if len(seen_actions) >= len(avg_strategy):
            break
        walk(hole)

    out: dict = {}
    for (combo, betting_history), probs in avg_strategy.items():
        actions = seen_actions.get((combo, betting_history))
        if actions is None or len(actions) != len(probs):
            continue
        situation = "-".join(betting_history) if betting_history else "start"
        player = 0 if not betting_history or len(betting_history) % 2 == 0 else 1
        label = f"{POSITION_NAMES[player]}:{situation}"
        combo_label = id_to_str(combo[0]) + id_to_str(combo[1])
        out.setdefault(label, {})[combo_label] = {
            action: round(float(p), 4) for action, p in zip(actions, probs) if p > 1e-3
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", type=str, required=True, help="5 cards, e.g. 'AsKd7h2c9s'")
    ap.add_argument("--hero-range", type=str, required=True)
    ap.add_argument("--villain-range", type=str, required=True)
    ap.add_argument("--pot", type=float, required=True)
    ap.add_argument("--stack", type=float, required=True)
    ap.add_argument("--iterations", type=int, default=200_000)
    ap.add_argument("--max-seconds", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--exploit-deals", type=int, default=150)
    ap.add_argument("--exploit-trials", type=int, default=5)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    board = tuple(card_ids(args.board))
    game = SpotGame(
        board=board,
        hero_range=Range(args.hero_range),
        villain_range=Range(args.villain_range),
        pot_bb=args.pot,
        stack_bb=args.stack,
    )
    print(f"Board {args.board}  |  {len(game._deal_outcomes)} valid hero/villain deal pairs")

    result, n_iters, elapsed = solve_spot(game, iterations=args.iterations, max_seconds=args.max_seconds, seed=args.seed)
    print(
        f"Ran {n_iters:,} MCCFR iterations in {elapsed:.1f}s | "
        f"game_value = {result.game_value:.4f} +/- {result.game_value_se:.4f} bb"
    )

    exp_mean, exp_se = sampled_exploitability(
        game, result.average_strategy, n_deals=args.exploit_deals, n_trials=args.exploit_trials, seed=args.seed
    )
    print(f"Abstraction exploitability: {exp_mean * 1000:.2f} +/- {exp_se * 1000:.2f} mbb/g")

    out = {
        "board": args.board,
        "hero_range": args.hero_range,
        "villain_range": args.villain_range,
        "pot_bb": args.pot,
        "stack_bb": args.stack,
        "iterations": n_iters,
        "elapsed_seconds": elapsed,
        "game_value_bb": result.game_value,
        "game_value_se_bb": result.game_value_se,
        "abstraction_exploitability_mbb": exp_mean * 1000.0,
        "abstraction_exploitability_se_mbb": exp_se * 1000.0,
        "strategy": format_strategy(result.average_strategy, game),
    }
    out_path = Path(args.out) if args.out else REPO_ROOT / "data" / "poker" / "solves" / f"spot_{args.board}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
