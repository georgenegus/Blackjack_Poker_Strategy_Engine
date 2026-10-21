"""Phase 7: count-indexed strategy deviations. Derives, never transcribes -- see
.agents/skills/ev_solver_conventions/SKILL.md's "Count-Index Derivation" and
.agents/coding-standards.md's "Count-to-Composition Mapping" for the method this
implements, and the build plan's Phase 7 for the Illustrious 18 / Fab 4 / insurance
values this is validated against.

Reuses grid_builder.py's own cell-solving functions (_solve_hard_cell etc.) against
a TC-perturbed composition instead of a neutral one -- the same, already-validated
decomposition-weighting logic Check 1/5 locked in, not a reimplementation of it.
"""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Optional, Tuple

import numpy as np

from src.counting.systems import CountingSystem
from src.engine.cards import RANK_INDEX
from src.engine.rules import RuleSet
from src.engine.shoe import DECK_COMPOSITION
from src.strategy import dealer_probs
from src.strategy import ev_solver as ev_solver_module
from src.strategy.grid_builder import (
    _comp_minus_values,
    _solve_hard_cell,
    _solve_pair_cell,
)
from src.utils.cache_manager import load_or_compute, source_hash

DEFAULT_INDEX_CACHE_DIR = Path("data/indices")
_SOLVER_SOURCE_FILES = (
    Path(__file__).with_name("ev_solver.py"),
    Path(__file__).with_name("dealer_probs.py"),
    Path(__file__).with_name("grid_builder.py"),
    Path(__file__).with_name("index_builder.py"),
)

TC_SWEEP_MAX = 10  # the build plan's Phase 7 Step 1: sweep true count from -10 to +10
_TEN_BUCKET = RANK_INDEX["T"]


def implied_composition(system: CountingSystem, decks_remaining: float, running_count: float) -> np.ndarray:
    """The 10-bucket shoe composition a given running count implies, treating
    `decks_remaining` as if it were itself a fresh, neutral shoe of that many
    (possibly fractional) decks, then perturbed by `running_count`.

    Standard treatment (documented here per coding-standards.md, since a
    different mapping shifts every derived index by ~1): distribute the
    count's implied surplus/deficit PROPORTIONALLY WITHIN each tag group,
    scaling every positive-tag rank down by the same fraction `f` and every
    negative-tag rank up by that same `f`, leaving untagged ranks alone.

    Derivation: let A = sum(tag_r * neutral_r) over positive-tag ranks, B = the
    same over negative-tag ranks. remaining_r = neutral_r*(1-f) for tag_r>0,
    neutral_r*(1+f) for tag_r<0. Requiring sum(tag_r * remaining_r) = -running_count
    (a system's running count is the tag-weighted sum of DEALT cards, i.e. the
    negative of the tag-weighted sum of cards remaining, for a balanced system
    where the full-shoe tag sum is 0) solves to f = [RC + (A+B)] / (A-B); for a
    balanced system A+B=0 and this reduces to f = RC / (2A).
    """
    neutral = DECK_COMPOSITION.astype(float) * decks_remaining
    tags = np.array(system.tags, dtype=float)

    pos = tags > 0
    neg = tags < 0
    a = float(np.sum(tags[pos] * neutral[pos]))
    b = float(np.sum(tags[neg] * neutral[neg]))
    denom = a - b
    if denom == 0:
        return neutral  # every rank untagged -- no perturbation is meaningful

    f = (running_count + (a + b)) / denom
    remaining = neutral.copy()
    remaining[pos] *= (1.0 - f)
    remaining[neg] *= (1.0 + f)
    # Physically impossible to remove more cards than exist -- only reachable at
    # extreme counts with few decks remaining; clamp rather than let ev_solver see
    # a negative count.
    return np.maximum(remaining, 0.0)


def insurance_correct(comp: np.ndarray) -> bool:
    """Insurance is a standalone bet on ten-density, not a grid cell (build plan
    Phase 7 Step 4): correct whenever tens exceed one third of the remaining shoe."""
    remaining = float(np.sum(comp))
    return remaining > 0 and float(comp[_TEN_BUCKET]) > remaining / 3.0


def insurance_index(system: CountingSystem, num_decks: int) -> Optional[int]:
    """Lowest TC (evaluated at decks_remaining=num_decks, the canonical reference
    point used throughout this module) at which insurance first becomes correct."""
    for tc in range(0, TC_SWEEP_MAX + 1):
        comp = implied_composition(system, num_decks, float(tc) * num_decks)
        if insurance_correct(comp):
            return tc
    return None


@dataclass
class DerivedIndex:
    cell_key: str                      # matches grid_builder's key format: "16v10", "TTv5"
    kind: str                          # "hard{N}" or "pair{rank}" -- see cell_result_fn
    upcard: int                        # point value, 2-11 (11=Ace)
    question: str                      # "primary" (S/H/D/P, no surrender) or "surrender" (S/H/R)
    baseline_action: str
    positive_index: Optional[int]      # lowest TC >= 1 where the action first differs from baseline
    positive_action: Optional[str]
    negative_index: Optional[int]      # highest TC <= -1 where the action first differs from baseline
    negative_action: Optional[str]
    ev_table: Dict[int, Dict[str, float]]  # ev_by_action at every swept TC (-10..+10) -- see derive_index


def _argmax(ev_by_action: Dict[str, float], allowed: FrozenSet[str]) -> str:
    candidates = {k: v for k, v in ev_by_action.items() if k in allowed}
    return max(candidates, key=candidates.get)


def _hard_result(total: int, upcard: int, rules: RuleSet, comp: np.ndarray):
    return _solve_hard_cell(total, upcard, rules, comp)


def _pair_result(rank: str, upcard: int, rules: RuleSet, comp: np.ndarray):
    rank_bucket = RANK_INDEX[rank]
    rank_value = 11 if rank == "A" else (10 if rank == "T" else int(rank))
    cell_comp = _comp_minus_values(comp, rank_value, rank_value, upcard)
    return _solve_pair_cell(rank_bucket, upcard, cell_comp, rules)


def derive_index(
    cell_key: str,
    kind: str,
    upcard: int,
    cell_result_fn,
    question: str,
    allowed_actions: FrozenSet[str],
    system: CountingSystem,
    num_decks: int,
    rules: RuleSet,
) -> DerivedIndex:
    """Sweeps TC from -10 to +10 (at decks_remaining=num_decks) and records the
    first TC, in each direction from the TC=0 baseline, whose argmax (restricted
    to `allowed_actions`) differs from it. `allowed_actions` is what separates the
    traditional Illustrious 18 questions (S/H/D/P, ignoring whether surrender
    would separately dominate) from the Fab 4's own surrender-specific ones
    (S/H/R) on the very same cell -- see the module docstring.

    Never early-exits once a flip is found: every swept TC's full ev_by_action is
    kept (DerivedIndex.ev_table), not just the two flip points, so deviations.py
    can look up a cached EV at runtime instead of re-solving live on every single
    decision -- a fresh recursive re-solve per hand was the actual bottleneck
    found running Phase 8's simulator battery (a live composition is essentially
    never repeated across hands, so it gets zero benefit from ev_solver.py's own
    memoization, unlike this derivation's one-time, disk-cached sweep)."""

    ev_table: Dict[int, Dict[str, float]] = {}

    def action_at(tc: int) -> str:
        comp = implied_composition(system, num_decks, float(tc) * num_decks)
        result = cell_result_fn(comp)
        ev_table[tc] = result.ev_by_action
        return _argmax(result.ev_by_action, allowed_actions)

    baseline = action_at(0)

    positive_index = None
    positive_action = None
    for tc in range(1, TC_SWEEP_MAX + 1):
        action = action_at(tc)
        if positive_index is None and action != baseline:
            positive_index, positive_action = tc, action

    negative_index = None
    negative_action = None
    for tc in range(-1, -TC_SWEEP_MAX - 1, -1):
        action = action_at(tc)
        if negative_index is None and action != baseline:
            negative_index, negative_action = tc, action

    return DerivedIndex(
        cell_key=cell_key,
        kind=kind,
        upcard=upcard,
        question=question,
        baseline_action=baseline,
        positive_index=positive_index,
        positive_action=positive_action,
        negative_index=negative_index,
        negative_action=negative_action,
        ev_table=ev_table,
    )


# --- The 18 Illustrious + Fab 4 named indices ------------------------------------------
# (total_or_rank, upcard, question) -- upcard uses point value (2-11, 11=Ace), matching
# grid_builder's own UPCARD_VALUES convention.

PRIMARY_ACTIONS = frozenset({"S", "H", "D", "P"})   # excludes surrender
SURRENDER_ACTIONS = frozenset({"S", "H", "R"})       # excludes double/split

ILLUSTRIOUS_18: Tuple[Tuple[str, int, str], ...] = (
    ("hard16", 10, "16v10"), ("hard15", 10, "15v10"), ("pairT", 5, "TTv5"),
    ("pairT", 6, "TTv6"), ("hard10", 10, "10v10"), ("hard12", 3, "12v3"),
    ("hard12", 2, "12v2"), ("hard11", 11, "11vA"), ("hard9", 2, "9v2"),
    ("hard10", 11, "10vA"), ("hard9", 7, "9v7"), ("hard16", 9, "16v9"),
    ("hard13", 2, "13v2"), ("hard12", 4, "12v4"), ("hard12", 5, "12v5"),
    ("hard12", 6, "12v6"), ("hard13", 3, "13v3"),
)

FAB_4: Tuple[Tuple[str, int, str], ...] = (
    ("hard14", 10, "14v10"), ("hard15", 10, "15v10"), ("hard15", 9, "15v9"), ("hard15", 11, "15vA"),
)


def cell_result_fn(kind: str, upcard: int, rules: RuleSet):
    """Public: deviations.py reuses this at runtime for a live re-solve (accurate
    EV-gain numbers at the counter's ACTUAL current composition), not just at
    index-build time."""
    if kind.startswith("hard"):
        total = int(kind[len("hard"):])
        return lambda comp: _hard_result(total, upcard, rules, comp)
    if kind.startswith("pair"):
        rank = kind[len("pair"):]
        return lambda comp: _pair_result(rank, upcard, rules, comp)
    raise ValueError(f"Unknown cell kind {kind!r}")


def build_named_indices(system: CountingSystem, num_decks: int, rules: RuleSet) -> Dict[str, DerivedIndex]:
    """Derives the Illustrious 18 (primary question, S/H/D/P) and Fab 4 (surrender
    question, S/H/R) index set for one ruleset+system. Keyed `f"{cell_key}:{question}"`
    since "15v10" carries both questions independently (see derive_index's docstring)."""
    indices: Dict[str, DerivedIndex] = {}
    for kind, upcard, cell_key in ILLUSTRIOUS_18:
        fn = cell_result_fn(kind, upcard, rules)
        idx = derive_index(cell_key, kind, upcard, fn, "primary", PRIMARY_ACTIONS, system, num_decks, rules)
        indices[f"{cell_key}:primary"] = idx
    for kind, upcard, cell_key in FAB_4:
        fn = cell_result_fn(kind, upcard, rules)
        idx = derive_index(cell_key, kind, upcard, fn, "surrender", SURRENDER_ACTIONS, system, num_decks, rules)
        indices[f"{cell_key}:surrender"] = idx
    return indices


_in_memory_index_cache: Dict[Tuple[str, str, int, str], Dict[str, DerivedIndex]] = {}
_cached_index_solver_hash: Optional[str] = None


def solve_indices_cached(
    system: CountingSystem, num_decks: int, rules: RuleSet, cache_dir: Path = DEFAULT_INDEX_CACHE_DIR
) -> Dict[str, DerivedIndex]:
    """build_named_indices(), transparently cached to
    cache_dir/{rules.key()}__{system.slug}.json (build plan Phase 7 Step 6) and
    memoized in-process. Deriving a fresh set of indices takes minutes (each of
    the ~20 swept true counts per cell is a genuinely distinct composition, with
    far less cross-call memoization reuse than a single neutral-shoe grid solve
    gets) -- deviations.advise() is called once per decision point, so it must
    never do this live."""
    global _cached_index_solver_hash
    mem_key = (rules.key(), system.slug, num_decks, str(cache_dir))
    cached = _in_memory_index_cache.get(mem_key)
    if cached is not None:
        return cached

    if _cached_index_solver_hash is None:
        _cached_index_solver_hash = source_hash(*_SOLVER_SOURCE_FILES)

    cache_path = cache_dir / f"{rules.key()}__{system.slug}.json"
    cache_key = {"ruleset_key": rules.key(), "system": system.name, "num_decks": num_decks}

    def _compute():
        named = build_named_indices(system, num_decks, rules)
        json_data = {key: asdict(idx) for key, idx in named.items()}
        # Same rationale as grid_builder.solve_grid_cached: these memos are only
        # useful WITHIN one derivation and grow unbounded across many otherwise.
        dealer_probs._recurse_memo.clear()
        ev_solver_module._ev_hit_memo.clear()
        ev_solver_module._ev_split_memo.clear()
        return json_data

    data = load_or_compute(cache_path, _cached_index_solver_hash, cache_key, _compute)
    indices = {key: _index_from_json(fields) for key, fields in data.items()}
    _in_memory_index_cache[mem_key] = indices
    return indices


def _index_from_json(fields: Dict) -> DerivedIndex:
    # JSON has no int keys -- ev_table round-trips as {"0": {...}, "-3": {...}, ...},
    # restore int keys so runtime lookups (deviations.py) can index it by TC directly.
    fields = dict(fields)
    fields["ev_table"] = {int(tc): evs for tc, evs in fields["ev_table"].items()}
    return DerivedIndex(**fields)
