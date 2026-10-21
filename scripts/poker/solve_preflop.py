"""Phase 10: solve and cache a preflop strategy for a given GameSpec. See
markdowns/poker/poker_build_plan_v1.md Phase 10.

    py scripts/poker/solve_preflop.py --spec hu-100bb-r5c3-s5 --iterations 1000000

Writes data/poker/strategy/{spec.key()}/preflop.json: the spec, a source
hash, iteration count, abstraction exploitability (mbb/g, WITH its standard
error -- sampled, see src/poker/exploit.py's sampled_exploitability), the
equity-realisation parameters used for "sees a flop" terminal values (part
of the game's definition, not a tuning knob -- see src/poker/advisor.py's
module docstring), and the solved strategy itself, keyed by
"{position}:{situation}" -> {hand_class: {action: frequency}}.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.poker import tree as _tree
from src.poker.advisor import POSITION_BONUS_MAX, SPR_CAP, PreflopGame
from src.poker.cfr import solve_mccfr
from src.poker.exploit import sampled_exploitability
from src.poker.ranges import CLASS_LABELS
from src.poker.spec import GameSpec

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
POSITION_NAMES = {0: "BTN", 1: "BB"}  # heads-up: player 0 is SB/BTN combined, player 1 is BB


def parse_spec_key(key: str) -> GameSpec:
    """Best-effort inverse of GameSpec.key() for the CLI's --spec argument.
    The key is a lossy encoding (e.g. "s5" records only the COUNT of bet
    sizes, not their values), so bet_sizes reconstructs to GameSpec's own
    default tuple when the count matches it; other fields not present in
    the key (ante, variant, ...) are left at GameSpec's defaults. Raises if
    the reconstructed spec's own .key() doesn't round-trip exactly, so a key
    this can't faithfully reconstruct fails loudly rather than silently
    solving the wrong game.
    """
    kwargs = {}
    for part in key.split("-"):
        if part == "hu":
            kwargs["num_players"] = 2
        elif part.endswith("max") and part[:-3].isdigit():
            kwargs["num_players"] = int(part[:-3])
        elif part.endswith("bb") and part[:-2].replace(".", "", 1).isdigit():
            kwargs["stack_bb"] = float(part[:-2])
        elif part.startswith("r") and "c" in part[1:]:
            r_str, c_str = part[1:].split("c", 1)
            kwargs["rake_pct"] = float(r_str) / 100.0
            kwargs["rake_cap_bb"] = float(c_str)
        elif part.startswith("s") and part[1:].isdigit():
            n_sizes = int(part[1:])
            default_sizes = GameSpec().bet_sizes
            if n_sizes != len(default_sizes):
                raise ValueError(f"cannot reconstruct exact bet_sizes for count {n_sizes} from key {key!r} alone")
            kwargs["bet_sizes"] = default_sizes
    spec = GameSpec(**kwargs)
    if spec.key() != key:
        raise ValueError(f"spec key did not round-trip: requested {key!r}, reconstructed {spec.key()!r}")
    return spec


def _solver_hash() -> str:
    h = hashlib.sha256()
    for name in ("advisor.py", "tree.py", "cfr.py"):
        h.update((REPO_ROOT / "src" / "poker" / name).read_bytes())
    return h.hexdigest()


def format_strategy(avg_strategy: dict, spec: GameSpec) -> dict:
    """{"{position}:{situation}": {hand_class: {action: frequency}}}. Walks
    the card-agnostic betting tree (src.poker.tree.build_tree) once to
    recover, for each decision point, which player acts and what their
    legal actions are -- information avg_strategy's own keys
    (class_index, betting_history) don't carry on their own."""
    t = _tree.build_tree(spec)
    out: dict = {}

    def walk(node):
        if isinstance(node, _tree.Terminal):
            return
        situation = "-".join(node.history) if node.history else "open"
        label = f"{POSITION_NAMES[node.player]}:{situation}"
        hands = {}
        for class_idx, class_label in enumerate(CLASS_LABELS):
            probs = avg_strategy.get((class_idx, node.history))
            if probs is None:
                continue
            hands[class_label] = {
                action: round(float(p), 4) for action, p in zip(node.actions.keys(), probs) if p > 1e-3
            }
        if hands:
            out[label] = hands
        for child in node.actions.values():
            walk(child)

    walk(t.root)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", type=str, required=True)
    ap.add_argument("--iterations", type=int, default=1_000_000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--exploit-deals", type=int, default=300)
    ap.add_argument("--exploit-trials", type=int, default=6)
    ap.add_argument("--value-samples", type=int, default=20_000)
    args = ap.parse_args()

    spec = parse_spec_key(args.spec)
    game = PreflopGame(spec)
    print(f"Spec: {spec.key()}  |  betting tree (card-agnostic): {game.tree_size()}")

    t0 = time.perf_counter()
    result = solve_mccfr(game, iterations=args.iterations, seed=args.seed, exact_value=False, value_samples=args.value_samples)
    t1 = time.perf_counter()
    print(
        f"Solved {args.iterations:,} MCCFR iterations in {t1 - t0:.1f}s "
        f"| game_value = {result.game_value:.4f} +/- {result.game_value_se:.4f} bb"
    )

    exp_mean, exp_se = sampled_exploitability(
        game, result.average_strategy, n_deals=args.exploit_deals, n_trials=args.exploit_trials, seed=args.seed
    )
    exp_mbb, exp_se_mbb = exp_mean * 1000.0, exp_se * 1000.0
    print(f"Abstraction exploitability: {exp_mbb:.2f} +/- {exp_se_mbb:.2f} mbb/g")

    out = {
        "spec": spec.key(),
        "solver_hash": _solver_hash(),
        "iterations": args.iterations,
        "game_value_bb": result.game_value,
        "game_value_se_bb": result.game_value_se,
        "abstraction_exploitability_mbb": exp_mbb,
        "abstraction_exploitability_se_mbb": exp_se_mbb,
        "realisation_factors": {"position_bonus_max": POSITION_BONUS_MAX, "spr_cap": SPR_CAP},
        "strategy": format_strategy(result.average_strategy, spec),
    }

    out_dir = REPO_ROOT / "data" / "poker" / "strategy" / spec.key()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "preflop.json").write_text(json.dumps(out, indent=2))
    print(f"Saved to {out_dir / 'preflop.json'}")


if __name__ == "__main__":
    main()
