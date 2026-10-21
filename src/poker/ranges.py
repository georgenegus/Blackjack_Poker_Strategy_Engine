"""Phase 4: 169-grid range notation, weighted combo expansion, and card
removal with renormalisation. See markdowns/poker/poker_build_plan_v1.md
Phase 4 and .agents/skills/poker_range_conventions/SKILL.md.

A range is not a set -- it is a weighted distribution over the 1,326
specific two-card combinations, and it must be re-conditioned on every card
that becomes visible (Range.conditioned()). This module owns the canonical
169-class registry (CLASS_LABELS, class_combos(), hand_classes()) that
scripts/poker/build_preflop_equity.py (Phase 3) also uses, so there is
exactly one definition of "the 169 classes" in the codebase.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from itertools import combinations, permutations
from pathlib import Path

from src.poker.cards import RANKS, SUITS, canonical, card_id, id_to_str
from src.poker.equity import equity_exact

Combo = tuple[int, int]

_SUIT_PERMS = list(permutations(range(4)))


# ---------------------------------------------------------------------------
# The 169 canonical starting-hand classes
# ---------------------------------------------------------------------------


def _build_class_registry():
    """Group all C(52,2) = 1,326 concrete combos into the 169 canonical
    classes via cards.canonical(), labelled "AA"/"AKs"/"AKo". Ordered
    high-rank-first, pair before suited before offsuit at each rank pair."""
    groups: dict = defaultdict(list)
    for combo in combinations(range(52), 2):
        groups[canonical(combo)].append(combo)

    entries = []
    for key, combos in groups.items():
        a, b = combos[0]
        ra, rb = a >> 2, b >> 2
        hi, lo = (ra, rb) if ra >= rb else (rb, ra)
        if ra == rb:
            label = RANKS[hi] + RANKS[lo]
            order = 0
        elif (a & 3) == (b & 3):
            label = RANKS[hi] + RANKS[lo] + "s"
            order = 1
        else:
            label = RANKS[hi] + RANKS[lo] + "o"
            order = 2
        entries.append((-hi, -lo, order, label, combos))
    entries.sort()
    labels = [e[3] for e in entries]
    combos_by_label = {e[3]: e[4] for e in entries}
    return labels, combos_by_label


CLASS_LABELS, _CLASS_COMBOS = _build_class_registry()
assert len(CLASS_LABELS) == 169, f"expected 169 canonical starting-hand classes, got {len(CLASS_LABELS)}"


def class_combos(label: str) -> list[Combo]:
    """The concrete two-card combos belonging to one of the 169 canonical
    starting-hand classes ("AA", "AKs", "AKo")."""
    return list(_CLASS_COMBOS[label])


def hand_classes() -> tuple[list[str], list[list[Combo]]]:
    """(labels, combo_groups) in parallel-list form, for callers that want to
    iterate all 169 classes together -- e.g.
    scripts/poker/build_preflop_equity.py's matrix build."""
    return list(CLASS_LABELS), [list(_CLASS_COMBOS[label]) for label in CLASS_LABELS]


# ---------------------------------------------------------------------------
# Notation parsing
# ---------------------------------------------------------------------------


def _normalize_token(token: str) -> str:
    """Uppercase rank characters, lowercase everything else ('s'/'o'
    suffixes, '+', '-', '%') -- case-insensitive input, unambiguous output."""
    out = []
    for ch in token.strip():
        out.append(ch.upper() if ch.upper() in RANKS else ch.lower())
    return "".join(out)


_R = "[2-9TJQKA]"
_PAIR = re.compile(rf"^(?P<r>{_R})(?P=r)$")
_PAIR_PLUS = re.compile(rf"^(?P<r>{_R})(?P=r)\+$")
_PAIR_RANGE = re.compile(rf"^(?P<r1>{_R})(?P=r1)-(?P<r2>{_R})(?P=r2)$")
_NONPAIR = re.compile(rf"^(?P<hi>{_R})(?P<lo>{_R})(?P<suit>[so]?)$")
_NONPAIR_PLUS = re.compile(rf"^(?P<hi>{_R})(?P<lo>{_R})(?P<suit>[so]?)\+$")
_NONPAIR_RANGE = re.compile(rf"^(?P<hi>{_R})(?P<lo1>{_R})(?P<suit>[so]?)-(?P=hi)(?P<lo2>{_R})(?P=suit)$")


def _class_labels_for_token(token: str) -> list[str]:
    """Expand one range-notation token (no weight suffix) into the list of
    169-class labels it covers. Supports: "100%"/"random"/"any2" (everything),
    "0%" (nothing); pairs "TT", "TT+", "88-55"; suited/offsuit/either "AKs",
    "AKo", "AK" (both combined); "+" and "-" ranges on suited/offsuit/either,
    keeping the top card fixed ("A5s+" = A5s..AKs, "A5s-A2s" = A5s..A2s)."""
    if token.strip().upper() in ("100%", "RANDOM", "ANY2"):
        return list(CLASS_LABELS)
    if token.strip() == "0%":
        return []
    t = _normalize_token(token)

    m = _PAIR_RANGE.match(t)
    if m:
        r1, r2 = RANKS.index(m["r1"]), RANKS.index(m["r2"])
        lo, hi = min(r1, r2), max(r1, r2)
        return [RANKS[r] + RANKS[r] for r in range(lo, hi + 1)]

    m = _PAIR_PLUS.match(t)
    if m:
        r = RANKS.index(m["r"])
        return [RANKS[k] + RANKS[k] for k in range(r, len(RANKS))]

    m = _PAIR.match(t)
    if m:
        return [t]

    m = _NONPAIR_RANGE.match(t)
    if m:
        hi = RANKS.index(m["hi"])
        lo1, lo2 = RANKS.index(m["lo1"]), RANKS.index(m["lo2"])
        lo, hi_kick = min(lo1, lo2), max(lo1, lo2)
        if hi_kick >= hi:
            raise ValueError(f"invalid range token (kicker reaches the top card): {token!r}")
        suit = m["suit"]
        suits = [suit] if suit else ["s", "o"]
        return [RANKS[hi] + RANKS[k] + s for k in range(lo, hi_kick + 1) for s in suits]

    m = _NONPAIR_PLUS.match(t)
    if m:
        hi, lo = RANKS.index(m["hi"]), RANKS.index(m["lo"])
        if lo >= hi:
            raise ValueError(f"invalid range token (kicker at or above the top card): {token!r}")
        suit = m["suit"]
        suits = [suit] if suit else ["s", "o"]
        return [RANKS[hi] + RANKS[k] + s for k in range(lo, hi) for s in suits]

    m = _NONPAIR.match(t)
    if m:
        hi, lo = RANKS.index(m["hi"]), RANKS.index(m["lo"])
        if hi == lo:
            raise ValueError(f"invalid token: {token!r}")
        if hi < lo:
            hi, lo = lo, hi
        suit = m["suit"]
        suits = [suit] if suit else ["s", "o"]
        return [RANKS[hi] + RANKS[lo] + s for s in suits]

    raise ValueError(f"unrecognised range token: {token!r}")


def _is_combo_token(token: str) -> bool:
    return (
        len(token) == 4
        and token[0].upper() in RANKS
        and token[1].lower() in SUITS
        and token[2].upper() in RANKS
        and token[3].lower() in SUITS
    )


def _combo_from_token(token: str) -> Combo:
    a = card_id(token[0:2])
    b = card_id(token[2:4])
    if a == b:
        raise ValueError(f"invalid combo (same card twice): {token!r}")
    return (min(a, b), max(a, b))


def _parse_notation(notation: str) -> dict[Combo, float]:
    combos: dict[Combo, float] = {}
    for raw_token in notation.split(","):
        raw_token = raw_token.strip()
        if not raw_token:
            continue
        if ":" in raw_token:
            base, weight_str = raw_token.rsplit(":", 1)
            weight = float(weight_str)
        else:
            base, weight = raw_token, 1.0
        base = base.strip()
        if not (0.0 <= weight <= 1.0):
            raise ValueError(f"combo weight must be in [0, 1]: {raw_token!r}")

        if _is_combo_token(base):
            combos[_combo_from_token(base)] = weight
        else:
            for label in _class_labels_for_token(base):
                for combo in _CLASS_COMBOS[label]:
                    combos[combo] = weight
    return combos


# ---------------------------------------------------------------------------
# Range
# ---------------------------------------------------------------------------


class Range:
    """A weighted distribution over two-card combos. Construct from notation
    ("AA", "TT+", "A5s-A2s", "AJs:0.5", "AsKd", "100%", comma-separated), or
    via Range.from_combos() for the result of an arithmetic operation."""

    __slots__ = ("_combos",)

    def __init__(self, notation: str | None = None):
        self._combos: dict[Combo, float] = _parse_notation(notation) if notation else {}

    @classmethod
    def from_combos(cls, combos: dict[Combo, float]) -> "Range":
        r = cls.__new__(cls)
        r._combos = dict(combos)
        return r

    def combos(self) -> dict[Combo, float]:
        """A copy of the {combo: weight} mapping."""
        return dict(self._combos)

    def n_combos(self) -> float:
        """Total combo-weight -- a range with every combo at weight 1.0 has
        n_combos() equal to its literal combo count."""
        return sum(self._combos.values())

    def percent_of_hands(self) -> float:
        return self.n_combos() / 1326.0 * 100.0

    def conditioned(self, blockers: int) -> "Range":
        """Drop every combo conflicting with `blockers` (a card bitmask, see
        cards.mask()). Deliberately does NOT rescale the survivors' weights:
        each surviving combo's weight already means "how often we hold this
        specific, still-possible combo", which blocking doesn't change about
        it -- what conditioning has to get right is that n_combos() (and
        everything built on it, like range-vs-range weighting) reflects only
        the survivors afterward, not a stale pre-conditioning total. See
        .agents/skills/poker_range_conventions/SKILL.md."""
        surviving = {
            c: w for c, w in self._combos.items() if not ((1 << c[0]) & blockers) and not ((1 << c[1]) & blockers)
        }
        return Range.from_combos(surviving)

    def reweight(self, factor: float) -> "Range":
        """Scale every combo's weight by `factor` -- e.g. "mix this range in
        30% of the time" is reweight(0.3). Not clamped to [0, 1]; that
        validation applies to notation parsing, not to arithmetic results."""
        return Range.from_combos({c: w * factor for c, w in self._combos.items()})

    def union(self, other: "Range") -> "Range":
        """Combo-wise max weight -- "in this range if it's in either", at
        whichever is the higher applicable frequency."""
        out = dict(self._combos)
        for c, w in other._combos.items():
            out[c] = max(out.get(c, 0.0), w)
        return Range.from_combos(out)

    def intersect(self, other: "Range") -> "Range":
        """Combo-wise min weight -- only combos in both ranges, at the more
        conservative of the two weights."""
        out = {}
        for c, w in self._combos.items():
            if c in other._combos:
                out[c] = min(w, other._combos[c])
        return Range.from_combos(out)

    def difference(self, other: "Range") -> "Range":
        """Combos in self that are not in other at all (set difference, not
        weight subtraction -- subtracting weights could go negative, which
        isn't a meaningful frequency)."""
        return Range.from_combos({c: w for c, w in self._combos.items() if c not in other._combos})

    __or__ = union
    __and__ = intersect
    __sub__ = difference

    def __repr__(self) -> str:
        return f"Range({self.n_combos():g} combos, {self.percent_of_hands():.2f}% of hands)"


def save_range(rng: Range, path: str | Path) -> None:
    data = {id_to_str(c[0]) + id_to_str(c[1]): w for c, w in rng.combos().items()}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True))


def load_range(path: str | Path) -> Range:
    data = json.loads(Path(path).read_text())
    return Range.from_combos({_combo_from_token(combo_str): float(weight) for combo_str, weight in data.items()})


# ---------------------------------------------------------------------------
# Range-vs-range equity
# ---------------------------------------------------------------------------


def _ordered_shape(hero: Combo, villain: Combo, board: tuple[int, ...]) -> tuple:
    """Suit-isomorphism shape of a (hero, villain, board) matchup --
    invariant under a global suit relabelling, but NOT under swapping hero
    and villain (their equities are complementary, f(villain, hero) =
    1 - f(hero, villain), not equal -- see
    scripts/poker/build_preflop_equity.py's Phase 3 tracking-table entry for
    the bug this exact distinction fixed there). Board cards form a third,
    order-insensitive group under the same permutation."""
    best = None
    for perm in _SUIT_PERMS:
        h = tuple(sorted((c // 4, perm[c % 4]) for c in hero))
        v = tuple(sorted((c // 4, perm[c % 4]) for c in villain))
        b = tuple(sorted((c // 4, perm[c % 4]) for c in board))
        candidate = (h, v, b)
        if best is None or candidate < best:
            best = candidate
    return best


def range_vs_range_equity(range_a: Range, range_b: Range, board=(), spec=None) -> tuple[float, float]:
    """Hero (range_a) vs villain (range_b) equity, computed as a JOINT
    weighted sum over non-conflicting (combo_a, combo_b) pairs -- never the
    naive per-combo average against the opponent's unconditioned range,
    which silently double-counts the mass of hands hero's own cards block
    (see .agents/skills/poker_range_conventions/SKILL.md). Board cards are
    additional blockers. Raw pairs are grouped by suit-isomorphism shape
    (_ordered_shape) before calling equity_exact, so only one exact
    enumeration is needed per distinct shape, not per raw combo pair -- the
    same technique scripts/poker/build_preflop_equity.py uses for the
    169x169 class matrix, generalised here to arbitrary weighted ranges and
    a possibly-nonempty board. Returns (equity_a, equity_b) summing to
    exactly 1.0.
    """
    board = tuple(board)
    board_mask = 0
    for c in board:
        board_mask |= 1 << c

    shape_weight: dict = {}
    shape_rep: dict = {}
    for a, wa in range_a._combos.items():
        if wa == 0.0 or (1 << a[0]) & board_mask or (1 << a[1]) & board_mask:
            continue
        for b, wb in range_b._combos.items():
            if wb == 0.0:
                continue
            if a[0] == b[0] or a[0] == b[1] or a[1] == b[0] or a[1] == b[1]:
                continue
            if (1 << b[0]) & board_mask or (1 << b[1]) & board_mask:
                continue
            key = _ordered_shape(a, b, board)
            shape_weight[key] = shape_weight.get(key, 0.0) + wa * wb
            shape_rep.setdefault(key, (a, b))

    total_weight = sum(shape_weight.values())
    if total_weight == 0.0:
        raise ValueError("no valid (non-conflicting) combo pairs between these two ranges given this board")

    acc_a = 0.0
    for key, w in shape_weight.items():
        a, b = shape_rep[key]
        eq = equity_exact([list(a), list(b)], list(board), spec)
        acc_a += float(eq[0]) * w

    equity_a = acc_a / total_weight
    return equity_a, 1.0 - equity_a
