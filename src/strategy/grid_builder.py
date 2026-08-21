"""Solves the full basic-strategy grid (hard totals, soft totals, pairs) for a
given RuleSet by exact EV enumeration -- see ev_solver.py. The grid is the
solver's ARGMAX, not a transcribed chart; the published charts in the build
plan's Appendix A are a known-answer test for THIS code (Phase 5), never the
other way around.

Notation (H/S/D/Ds/P/Rh/Rs/Rp): D/Ds and Rh/Rs/Rp encode a FUNCTIONAL fallback,
not a ruleset-ambiguity one. Double and surrender are first-action-only, so the
same "hard 11" cell is consulted both for a fresh 2-card 11 (where double may
apply) and for a 3+ card 11 reached by hitting (where it never does) -- the
fallback letter (H vs S) tells basic_strategy.advise() what to do in the latter
case. A pair cell never carries this ambiguity: since ev_split (Phase 3) already
bakes in rules.double_after_split for this exact ruleset, "split" is either
correct or it isn't -- there is no runtime fallback to encode. This means a cell
this solver renders as plain "P" is functionally identical to a published
chart's "Ph" whenever that chart's ruleset also has DAS=True (Ph only differs
from P as a *pedagogical* note for readers whose own table might lack DAS) --
see the Phase 5 chart-comparison test for how that equivalence is normalised.

Hard totals are frequency-weighted over EVERY valid non-pair 2-card decomposition
(e.g. hard 12 = 2+10, 3+9, 4+8, or 5+7), not a single representative combo -- soft
totals and pairs have no such ambiguity (A+x and rank+rank are exact). A single
arbitrary decomposition is not a harmless simplification: hard 12 vs dealer 4 is
close enough (S=-0.2111 vs H=-0.2104 with the 2+10 combo alone) that picking a
Ten-heavy combo flips the argmax against the published chart, while every other
combo agrees with it. See the Phase 4 tracking-table entry for the numbers.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from src.engine.cards import RANK_INDEX, advance_total
from src.engine.rules import RuleSet, double_allowed
from src.engine.shoe import Shoe
from src.strategy import dealer_probs
from src.strategy import ev_solver as ev_solver_module
from src.strategy.ev_solver import ev_double, ev_hit, ev_split, ev_stand, ev_surrender
from src.utils.cache_manager import load_or_compute, source_hash

DEFAULT_CACHE_DIR = Path("data/strategy")
_SOLVER_SOURCE_FILES = (
    Path(__file__).with_name("ev_solver.py"),
    Path(__file__).with_name("dealer_probs.py"),
    Path(__file__).with_name("grid_builder.py"),
)

UPCARD_VALUES = list(range(2, 12))          # 2..11, 11=Ace
HARD_TOTALS = list(range(5, 21))            # 5..20 (21 is trivially always-stand)
SOFT_TOTALS = list(range(13, 21))           # A,2 (13) .. A,9 (20)
PAIR_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "A"]


@dataclass
class CellResult:
    action: str
    ev_by_action: Dict[str, float]
    margin: float  # gap between the best and second-best EV among ev_by_action


def _value_to_bucket(value: int) -> int:
    if value == 11:
        return RANK_INDEX["A"]
    if value == 10:
        return RANK_INDEX["T"]
    return value - 2


def _comp_minus_values(rules: RuleSet, *values: int) -> Tuple[int, ...]:
    comp = Shoe(rules.num_decks).composition.copy()
    for v in values:
        comp[_value_to_bucket(v)] -= 1
    return tuple(int(x) for x in comp)


def _hard_decompositions(total: int) -> Tuple[Tuple[int, int], ...]:
    """Every valid non-pair two-card decomposition of a hard total (c1 < c2, both
    in 2..10) -- e.g. 12 = 2+10, 3+9, 4+8, 5+7. Degenerate totals with no non-pair
    decomposition at all (20 = only 10+10) fall back to the pair-like combo, which
    is harmless since standing dominates so overwhelmingly at that total that the
    exact comp cannot plausibly change the argmax."""
    combos = tuple((c1, total - c1) for c1 in range(2, 10) if c1 < total - c1 <= 10)
    if combos:
        return combos
    return ((total // 2, total - total // 2),)


def _margin(ev_by_action: Dict[str, float]) -> float:
    values = sorted(ev_by_action.values(), reverse=True)
    return values[0] - values[1] if len(values) > 1 else 0.0


def _rank_action(
    stand_ev: float, hit_ev: float, double_ev: Optional[float], surrender_ev: Optional[float]
) -> Tuple[str, Dict[str, float]]:
    ev_by_action = {"S": stand_ev, "H": hit_ev}
    if double_ev is not None:
        ev_by_action["D"] = double_ev
    if surrender_ev is not None:
        ev_by_action["R"] = surrender_ev

    fallback = "S" if stand_ev >= hit_ev else "H"
    best_key = max(ev_by_action, key=ev_by_action.get)

    if best_key == "D":
        code = "D" if fallback == "H" else "Ds"
    elif best_key == "R":
        code = "Rh" if fallback == "H" else "Rs"
    else:
        code = best_key
    return code, ev_by_action


def _pair_action(
    stand_ev: float,
    hit_ev: float,
    double_ev: Optional[float],
    surrender_ev: Optional[float],
    split_ev: float,
) -> Tuple[str, Dict[str, float]]:
    ev_by_action = {"S": stand_ev, "H": hit_ev, "P": split_ev}
    if double_ev is not None:
        ev_by_action["D"] = double_ev
    if surrender_ev is not None:
        ev_by_action["R"] = surrender_ev

    # Fallback if surrender (first-action-only) isn't available: best of the actions a
    # fresh pair can always consider. Double is ALSO first-action-only, so if it would
    # be the fallback winner, resolve it down to stand/hit same as _rank_action does.
    no_surrender = {k: v for k, v in ev_by_action.items() if k != "R"}
    fallback_key = max(no_surrender, key=no_surrender.get)
    if fallback_key == "D":
        fallback_key = "S" if stand_ev >= hit_ev else "H"

    best_key = max(ev_by_action, key=ev_by_action.get)
    if best_key == "R":
        code = {"H": "Rh", "S": "Rs", "P": "Rp"}[fallback_key]
    elif best_key == "D":
        d_fallback = "S" if stand_ev >= hit_ev else "H"
        code = "D" if d_fallback == "H" else "Ds"
    else:
        code = best_key
    return code, ev_by_action


def _solve_non_pair_cell(total: int, is_soft: bool, upcard: int, comp: Tuple[int, ...], rules: RuleSet) -> CellResult:
    """Exact single-comp solve, for cells with no decomposition ambiguity (soft totals)."""
    stand_ev = ev_stand(total, upcard, comp, rules)
    hit_ev = ev_hit(total, is_soft, upcard, comp, rules)
    double_ev = ev_double(total, is_soft, upcard, comp, rules) if double_allowed(rules, total, is_soft) else None
    surrender_ev = ev_surrender() if rules.surrender != "none" else None
    code, ev_by_action = _rank_action(stand_ev, hit_ev, double_ev, surrender_ev)
    return CellResult(action=code, ev_by_action=ev_by_action, margin=_margin(ev_by_action))


def _solve_hard_cell(total: int, upcard: int, rules: RuleSet, full) -> CellResult:
    """Frequency-weighted solve across every valid non-pair decomposition of `total`
    -- see the module docstring for why a single arbitrary decomposition is not safe."""
    weighted_comps = []
    for c1, c2 in _hard_decompositions(total):
        w = float(full[_value_to_bucket(c1)]) * float(full[_value_to_bucket(c2)])
        comp = _comp_minus_values(rules, c1, c2, upcard)
        weighted_comps.append((w, comp))
    total_w = sum(w for w, _ in weighted_comps)

    stand_ev = sum(w * ev_stand(total, upcard, comp, rules) for w, comp in weighted_comps) / total_w
    hit_ev = sum(w * ev_hit(total, False, upcard, comp, rules) for w, comp in weighted_comps) / total_w
    if double_allowed(rules, total, False):
        double_ev = sum(w * ev_double(total, False, upcard, comp, rules) for w, comp in weighted_comps) / total_w
    else:
        double_ev = None
    surrender_ev = ev_surrender() if rules.surrender != "none" else None

    code, ev_by_action = _rank_action(stand_ev, hit_ev, double_ev, surrender_ev)
    return CellResult(action=code, ev_by_action=ev_by_action, margin=_margin(ev_by_action))


def _solve_pair_cell(rank_bucket: int, upcard: int, comp: Tuple[int, ...], rules: RuleSet) -> CellResult:
    is_aces = rank_bucket == RANK_INDEX["A"]
    t1, s1 = advance_total(0, False, rank_bucket)
    total, is_soft = advance_total(t1, s1, rank_bucket)

    stand_ev = ev_stand(total, upcard, comp, rules)
    hit_ev = ev_hit(total, is_soft, upcard, comp, rules)
    double_ev = ev_double(total, is_soft, upcard, comp, rules) if double_allowed(rules, total, is_soft) else None
    surrender_ev = ev_surrender() if rules.surrender != "none" else None
    split_ev = ev_split(rank_bucket, upcard, comp, rules, is_aces=is_aces)

    code, ev_by_action = _pair_action(stand_ev, hit_ev, double_ev, surrender_ev, split_ev)
    return CellResult(action=code, ev_by_action=ev_by_action, margin=_margin(ev_by_action))


def solve_grid(rules: RuleSet) -> Dict[str, Dict[str, CellResult]]:
    """Solves every cell of the basic-strategy grid for `rules`: hard totals 5-20,
    soft totals 13-20 (A,2..A,9), and pairs 2,2..A,A, each against every dealer
    upcard 2-11. Returns {"hard": {...}, "soft": {...}, "pairs": {...}}, each
    mapping a cell key ("{total}v{upcard}" or "{rank}{rank}v{upcard}") -> CellResult.
    """
    grid: Dict[str, Dict[str, CellResult]] = {"hard": {}, "soft": {}, "pairs": {}}
    full = Shoe(rules.num_decks).composition

    for total in HARD_TOTALS:
        for upcard in UPCARD_VALUES:
            grid["hard"][f"{total}v{upcard}"] = _solve_hard_cell(total, upcard, rules, full)

    for total in SOFT_TOTALS:
        x = total - 11
        for upcard in UPCARD_VALUES:
            comp = _comp_minus_values(rules, 11, x, upcard)
            grid["soft"][f"{total}v{upcard}"] = _solve_non_pair_cell(total, True, upcard, comp, rules)

    for rank in PAIR_RANKS:
        rank_bucket = RANK_INDEX[rank]
        rank_value = 11 if rank == "A" else (10 if rank == "T" else int(rank))
        for upcard in UPCARD_VALUES:
            comp = _comp_minus_values(rules, rank_value, rank_value, upcard)
            grid["pairs"][f"{rank}{rank}v{upcard}"] = _solve_pair_cell(rank_bucket, upcard, comp, rules)

    return grid


def _grid_to_json(grid: Dict[str, Dict[str, CellResult]]) -> Dict[str, Dict[str, dict]]:
    return {section: {key: asdict(cell) for key, cell in cells.items()} for section, cells in grid.items()}


def _grid_from_json(data: Dict[str, Dict[str, dict]]) -> Dict[str, Dict[str, CellResult]]:
    return {section: {key: CellResult(**cell) for key, cell in cells.items()} for section, cells in data.items()}


_in_memory_grid_cache: Dict[Tuple[RuleSet, str], Dict[str, Dict[str, CellResult]]] = {}
_cached_solver_hash: Optional[str] = None


def solve_grid_cached(rules: RuleSet, cache_dir: Path = DEFAULT_CACHE_DIR) -> Dict[str, Dict[str, CellResult]]:
    """solve_grid(rules), transparently cached to cache_dir/{rules.key()}.json via
    src/utils/cache_manager.py, AND memoized in-process. Callers like
    basic_strategy.advise() may be invoked millions of times in a single
    simulation run (Phase 5's house-edge check, Phase 8's Monte Carlo battery)
    -- re-reading and re-parsing the ~90KB JSON file on every call would
    dominate runtime. The disk cache still protects across process runs; this
    only avoids redundant work within one."""
    global _cached_solver_hash
    mem_key = (rules, str(cache_dir))
    cached = _in_memory_grid_cache.get(mem_key)
    if cached is not None:
        return cached

    if _cached_solver_hash is None:
        _cached_solver_hash = source_hash(*_SOLVER_SOURCE_FILES)

    cache_path = cache_dir / f"{rules.key()}.json"
    cache_key = {"ruleset_key": rules.key()}

    def _compute():
        json_data = _grid_to_json(solve_grid(rules))
        # The raw per-cell recursion memos in dealer_probs.py/ev_solver.py are only
        # useful WITHIN one ruleset's solve -- they barely share entries across
        # different RuleSets (ev_hit/ev_split key on the whole RuleSet; dealer_probs
        # keys on dealer_hits_soft_17 but comps differ by deck count) -- and grow
        # unbounded if left across many solves in one process. Pre-solving all 32
        # shipped rulesets in one run of scripts/build_all_grids.py hit a
        # MemoryError on the 7.7GB dev machine partway through without this.
        dealer_probs._recurse_memo.clear()
        ev_solver_module._ev_hit_memo.clear()
        ev_solver_module._ev_split_memo.clear()
        return json_data

    data = load_or_compute(cache_path, _cached_solver_hash, cache_key, _compute)
    grid = _grid_from_json(data)
    _in_memory_grid_cache[mem_key] = grid
    return grid
