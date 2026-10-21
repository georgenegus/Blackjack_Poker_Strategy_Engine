"""Phase 2: exact 5/6/7-card hand evaluator.

Strategy A (Cactus-Kev style, per markdowns/poker/poker_build_plan_v1.md and
.agents/skills/poker_evaluator_conventions/SKILL.md): every 5-card hand is
classified once, offline, into one of exactly 7,462 distinct rank classes
(lower integer = stronger hand -- fixed, never flipped). Classification uses
one of three O(1) lookups depending on hand shape:
  - all-same-suit (flush, incl. straight flush)         -> flush_class[bitmask]
  - 5 distinct ranks, not a flush (straight/high card)   -> unique5_class[bitmask]
  - a repeated rank (quads/full house/trips/2pair/pair)  -> prime_class[prime_product]
A 7-card hand's value is the best (minimum) of its C(7,5) = 21 five-card subsets.

Strategy B (a denser 7-card DAG lookup) is not built here -- this ships
Strategy A as the reference, per the build plan; the escalation that did
prove necessary was numba (see evaluate_batch below), not Strategy B.

Run `py scripts/poker/build_evaluator_tables.py` once before importing this
module for real use -- it builds and persists the tables this module loads.
"""
from __future__ import annotations

from collections import Counter
from enum import IntEnum
from itertools import combinations
from pathlib import Path

import numpy as np

try:
    from numba import njit, prange

    _HAS_NUMBA = True
except ImportError:  # pragma: no cover - numba is an optional dependency
    _HAS_NUMBA = False

PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41)  # indexed by rank 0..12

TABLE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "poker" / "evaluator" / "tables.npz"


class HandCategory(IntEnum):
    STRAIGHT_FLUSH = 0
    FOUR_OF_A_KIND = 1
    FULL_HOUSE = 2
    FLUSH = 3
    STRAIGHT = 4
    THREE_OF_A_KIND = 5
    TWO_PAIR = 6
    ONE_PAIR = 7
    HIGH_CARD = 8


def _straight_high(rank_set: frozenset) -> int | None:
    """rank_set: exactly 5 distinct rank indices (0..12). Returns the rank
    index of the straight's high card, or None if the ranks don't form a
    straight. The wheel (2,3,4,5,A = ranks {0,1,2,3,12}) is the lowest
    straight, with the 5 (index 3) -- not the ace -- as its high card."""
    if rank_set == frozenset({0, 1, 2, 3, 12}):
        return 3
    mn, mx = min(rank_set), max(rank_set)
    if mx - mn == 4:
        return mx
    return None


def _classify5(ranks: list[int], suits: list[int]) -> tuple:
    """Pure classification of one 5-card hand -> a strength key. Ascending key
    order == descending hand strength (a straight flush's key sorts first).
    The single source of truth for both build_tables() below and, indirectly,
    for verifying it -- see distinct_five_card_values()."""
    rank_set = frozenset(ranks)
    if len(rank_set) == 5:
        is_flush = suits[0] == suits[1] == suits[2] == suits[3] == suits[4]
        high = _straight_high(rank_set)
        if high is not None:
            category = HandCategory.STRAIGHT_FLUSH if is_flush else HandCategory.STRAIGHT
            tiebreak = (high,)
        else:
            category = HandCategory.FLUSH if is_flush else HandCategory.HIGH_CARD
            tiebreak = tuple(sorted(ranks, reverse=True))
    else:
        counts = Counter(ranks)
        by_count: dict[int, list[int]] = {}
        for r, n in counts.items():
            by_count.setdefault(n, []).append(r)
        for n in by_count:
            by_count[n].sort(reverse=True)
        if by_count.get(4):
            category = HandCategory.FOUR_OF_A_KIND
            tiebreak = (by_count[4][0], by_count[1][0])
        elif by_count.get(3) and by_count.get(2):
            category = HandCategory.FULL_HOUSE
            tiebreak = (by_count[3][0], by_count[2][0])
        elif by_count.get(3):
            category = HandCategory.THREE_OF_A_KIND
            tiebreak = (by_count[3][0],) + tuple(by_count[1])
        elif len(by_count.get(2, [])) == 2:
            category = HandCategory.TWO_PAIR
            tiebreak = tuple(by_count[2]) + tuple(by_count[1])
        else:
            category = HandCategory.ONE_PAIR
            tiebreak = (by_count[2][0],) + tuple(by_count[1])
    return (int(category),) + tuple(12 - r for r in tiebreak)


def _bitmask(ranks) -> int:
    bm = 0
    for r in ranks:
        bm |= 1 << r
    return bm


def _prime_product(ranks) -> int:
    p = 1
    for r in ranks:
        p *= PRIMES[r]
    return p


def build_tables() -> dict:
    """Enumerate all C(52,5) = 2,598,960 real five-card hands directly (real
    suits, real ranks -- not an abstract multiset argument about which rank
    patterns are physically possible, which is exactly the kind of reasoning
    a hand-derived table is at risk of getting subtly wrong), classify each
    via _classify5, and derive the three O(1) lookup tables from the
    resulting distinct keys.
    """
    flush_keys: dict[int, tuple] = {}
    unique5_keys: dict[int, tuple] = {}
    prime_keys: dict[int, tuple] = {}

    for combo in combinations(range(52), 5):
        ranks = [c >> 2 for c in combo]
        suits = [c & 3 for c in combo]
        key = _classify5(ranks, suits)
        if len(set(ranks)) == 5:
            bm = _bitmask(ranks)
            if suits[0] == suits[1] == suits[2] == suits[3] == suits[4]:
                flush_keys[bm] = key
            else:
                unique5_keys[bm] = key
        else:
            prime_keys[_prime_product(ranks)] = key

    all_keys = sorted(set(flush_keys.values()) | set(unique5_keys.values()) | set(prime_keys.values()))
    assert len(all_keys) == 7462, f"expected 7462 distinct hand values, got {len(all_keys)}"
    key_to_class = {key: i for i, key in enumerate(all_keys)}

    flush_class = np.full(8192, -1, dtype=np.int32)
    for bm, key in flush_keys.items():
        flush_class[bm] = key_to_class[key]
    unique5_class = np.full(8192, -1, dtype=np.int32)
    for bm, key in unique5_keys.items():
        unique5_class[bm] = key_to_class[key]

    prime_arr = np.array(sorted(prime_keys), dtype=np.int64)
    prime_class_arr = np.array([key_to_class[prime_keys[p]] for p in prime_arr], dtype=np.int32)

    class_to_category = np.array([key[0] for key in all_keys], dtype=np.int32)

    return {
        "flush_class": flush_class,
        "unique5_class": unique5_class,
        "prime_keys": prime_arr,
        "prime_class": prime_class_arr,
        "class_to_category": class_to_category,
    }


_tables_cache: dict | None = None


def _load_tables() -> dict:
    global _tables_cache
    if _tables_cache is not None:
        return _tables_cache
    if not TABLE_PATH.exists():
        raise FileNotFoundError(
            f"Evaluator tables not found at {TABLE_PATH}. Run "
            "`py scripts/poker/build_evaluator_tables.py` first."
        )
    data = np.load(TABLE_PATH)
    _tables_cache = {k: data[k] for k in data.files}
    return _tables_cache


def evaluate5(cards) -> int:
    """Exact rank class in [0, 7462) for one 5-card hand. Lower = stronger."""
    t = _load_tables()
    ranks = [c >> 2 for c in cards]
    suits = [c & 3 for c in cards]
    if len(set(ranks)) == 5:
        bm = _bitmask(ranks)
        if suits[0] == suits[1] == suits[2] == suits[3] == suits[4]:
            return int(t["flush_class"][bm])
        return int(t["unique5_class"][bm])
    prod = _prime_product(ranks)
    idx = int(np.searchsorted(t["prime_keys"], prod))
    assert idx < len(t["prime_keys"]) and t["prime_keys"][idx] == prod, (
        "invalid or duplicate cards passed to evaluate5"
    )
    return int(t["prime_class"][idx])


def evaluate(cards) -> int:
    """Exact rank class for a 5, 6, or 7-card hand -- the best (minimum) of
    its C(len(cards), 5) five-card subsets. Lower = stronger."""
    cards = list(cards)
    if len(cards) == 5:
        return evaluate5(cards)
    return min(evaluate5(c) for c in combinations(cards, 5))


_SUBSETS5_OF_7 = [list(c) for c in combinations(range(7), 5)]  # 21 fixed index-tuples


def _evaluate5_vectorized(ranks5: np.ndarray, suits5: np.ndarray, t: dict) -> np.ndarray:
    """ranks5, suits5: (N, 5) int arrays -> (N,) int32 rank class. The
    vectorised twin of evaluate5(): the same three-way flush/unique5/prime
    dispatch, but as array-wide numpy passes instead of one Python call per
    hand. Both branches are computed unconditionally for every row and then
    selected with np.where -- the discarded branch's value is never a valid
    lookup for that row's actual cards, but array indexing never raises for
    it (bitmasks stay within the fixed 8192-entry tables; searchsorted
    results are clipped before indexing), so there is nothing to guard."""
    is_flush = (
        (suits5[:, 0] == suits5[:, 1])
        & (suits5[:, 0] == suits5[:, 2])
        & (suits5[:, 0] == suits5[:, 3])
        & (suits5[:, 0] == suits5[:, 4])
    )
    sorted_ranks = np.sort(ranks5, axis=1)
    no_dup = ~(sorted_ranks[:, :-1] == sorted_ranks[:, 1:]).any(axis=1)

    bm = np.zeros(ranks5.shape[0], dtype=np.int32)
    for col in range(5):
        bm |= np.int32(1) << ranks5[:, col].astype(np.int32)
    distinct_result = np.where(is_flush, t["flush_class"][bm], t["unique5_class"][bm])

    primes_arr = np.asarray(PRIMES, dtype=np.int64)
    prod = primes_arr[ranks5].prod(axis=1)
    idx = np.clip(np.searchsorted(t["prime_keys"], prod), 0, len(t["prime_class"]) - 1)
    prime_result = t["prime_class"][idx]

    return np.where(no_dup, distinct_result, prime_result).astype(np.int32)


def _evaluate_batch_numpy(hands: np.ndarray, t: dict) -> np.ndarray:
    """Fully vectorised fallback: evaluates all 21 five-card subsets across
    all N hands as 21 numpy passes (not N*21 Python-level evaluate5() calls),
    then takes the row-wise best. ~235k hands/sec measured -- used when numba
    is unavailable."""
    ranks = (hands >> 2).astype(np.int32)
    suits = (hands & 3).astype(np.int32)
    best = np.full(hands.shape[0], np.iinfo(np.int32).max, dtype=np.int32)
    for cols in _SUBSETS5_OF_7:
        best = np.minimum(best, _evaluate5_vectorized(ranks[:, cols], suits[:, cols], t))
    return best


if _HAS_NUMBA:

    @njit(parallel=True, cache=True)
    def _evaluate_batch_numba(hands, flush_class, unique5_class, prime_keys, prime_class, primes, subsets):
        n = hands.shape[0]
        n_subsets = subsets.shape[0]
        n_primes = len(prime_keys)
        out = np.empty(n, dtype=np.int32)
        for i in prange(n):
            best = 2147483647
            ranks = np.empty(7, dtype=np.int64)
            suits = np.empty(7, dtype=np.int64)
            for k in range(7):
                c = hands[i, k]
                ranks[k] = c >> 2
                suits[k] = c & 3
            for s in range(n_subsets):
                i0, i1, i2, i3, i4 = subsets[s, 0], subsets[s, 1], subsets[s, 2], subsets[s, 3], subsets[s, 4]
                r0, r1, r2, r3, r4 = ranks[i0], ranks[i1], ranks[i2], ranks[i3], ranks[i4]
                is_flush = (suits[i0] == suits[i1]) and (suits[i0] == suits[i2])
                is_flush = is_flush and (suits[i0] == suits[i3]) and (suits[i0] == suits[i4])
                bm = (1 << r0) | (1 << r1) | (1 << r2) | (1 << r3) | (1 << r4)
                cnt = 0
                tmp = bm
                while tmp:
                    tmp &= tmp - 1
                    cnt += 1
                if cnt == 5:
                    val = flush_class[bm] if is_flush else unique5_class[bm]
                else:
                    prod = primes[r0] * primes[r1] * primes[r2] * primes[r3] * primes[r4]
                    lo, hi = 0, n_primes
                    while lo < hi:
                        mid = (lo + hi) // 2
                        if prime_keys[mid] < prod:
                            lo = mid + 1
                        else:
                            hi = mid
                    val = prime_class[lo]
                if val < best:
                    best = val
            out[i] = best
        return out

    _PRIMES_ARR = np.asarray(PRIMES, dtype=np.int64)
    _SUBSETS_ARR = np.asarray(_SUBSETS5_OF_7, dtype=np.int64)


def evaluate_batch(hands: np.ndarray) -> np.ndarray:
    """hands: (N, 7) array of card ids -> (N,) int32 rank class, lower =
    stronger. This is the fast path Phase 3's equity engine depends on for
    exact enumeration to stay tractable at 1M+ runouts (the naive
    N * 21-Python-calls loop measured ~130s for one 1.7M-runout preflop
    matchup -- far too slow to build the 169x169 preflop equity matrix, which
    needs on the order of 10,000+ such matchups). Dispatches to a
    parallel numba kernel when available (~6.9M hands/sec measured, a ~29x
    speedup over the pure-numpy fallback below it) -- numba was added as a
    real dependency specifically because this proved necessary, per the build
    plan's "numba... add only if numpy proves too slow" escalation path."""
    t = _load_tables()
    hands = np.asarray(hands, dtype=np.int64)
    if _HAS_NUMBA:
        return _evaluate_batch_numba(
            hands, t["flush_class"], t["unique5_class"], t["prime_keys"], t["prime_class"], _PRIMES_ARR, _SUBSETS_ARR
        )
    return _evaluate_batch_numpy(hands, t)


def category(rank_class: int) -> HandCategory:
    t = _load_tables()
    return HandCategory(int(t["class_to_category"][rank_class]))


def category_batch(rank_classes: np.ndarray) -> np.ndarray:
    """Vectorised twin of category(): (N,) rank classes -> (N,) int32
    HandCategory values. Added for Phase 5's full C(52,7) enumeration, which
    needs to classify 133,784,560 results without a Python-level call per
    hand."""
    t = _load_tables()
    return t["class_to_category"][np.asarray(rank_classes)]


def distinct_five_card_values() -> int:
    """Fresh self-check: enumerate all C(52,5) = 2,598,960 five-card hands,
    evaluate each via the built tables, and count the distinct classes
    returned. Independent of build_tables()'s own internal assertion -- this
    exercises evaluate5() itself, catching any mismatch between how the
    tables were built and how they're read back."""
    seen = set()
    for combo in combinations(range(52), 5):
        seen.add(evaluate5(combo))
    return len(seen)
