"""Phase 1: 52-card rank x suit encoding, bitmasks, and suit-isomorphism canonicalisation.

Unlike the blackjack side's 10-bucket rank collapse, poker needs full rank x suit
(52 distinct values) because flushes and suit isomorphism both depend on it -- see
.agents/skills/poker_evaluator_conventions/SKILL.md.
"""
from __future__ import annotations

from itertools import permutations

RANKS = "23456789TJQKA"  # index 0..12, ace high
SUITS = "cdhs"  # index 0..3

_SUIT_PERMS = list(permutations(range(4)))


def card_id(s: str) -> int:
    """Parse one two-character card string (e.g. "As", "Td", "2c") to an id in [0, 52)."""
    rank_char = s[0].upper()
    suit_char = s[1].lower()
    return RANKS.index(rank_char) * 4 + SUITS.index(suit_char)


def card_ids(s: str) -> list[int]:
    """Parse a concatenated string of two-character cards, e.g. "AsKsQsJsTs2c3d"."""
    return [card_id(s[i : i + 2]) for i in range(0, len(s), 2)]


def id_to_str(card: int) -> str:
    return RANKS[card // 4] + SUITS[card % 4]


def rank_of(card: int) -> int:
    return card // 4


def suit_of(card: int) -> int:
    return card % 4


def deck() -> list[int]:
    return list(range(52))


def mask(cards) -> int:
    """52-bit mask for O(1) conflict/blocker checks."""
    m = 0
    for c in cards:
        m |= 1 << c
    return m


def canonical(cards) -> tuple:
    """Canonical form of a set of cards, invariant under relabelling suits.

    Two card sets are strategically identical up to which literal suit is which
    iff they share this canonical form. Used to collapse C(52,2) = 1,326 starting
    hands to 169 classes and C(52,3) = 22,100 flops to 1,755 classes.
    """
    best = None
    for perm in _SUIT_PERMS:
        relabelled = tuple(sorted((c // 4, perm[c % 4]) for c in cards))
        if best is None or relabelled < best:
            best = relabelled
    return best


def canonical_board(cards) -> tuple:
    return canonical(cards)
