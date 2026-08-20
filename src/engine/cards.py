"""Card and rank-bucket primitives.

Blackjack rules and every count system operate on 10 rank buckets (2-9, T, A),
never on the 13 literal ranks -- T/J/Q/K are worth the same and are treated
identically everywhere except Hand.is_pair_exact. This collapse is what keeps
the Phase 3 solver's memoisation tractable; see .agents/coding-standards.md.
"""

from typing import NamedTuple, Optional, Tuple

RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]
SUITS = ["S", "H", "D", "C"]
RED_SUITS = {"H", "D"}

# 10 buckets: 2,3,4,5,6,7,8,9,T,A -- J/Q/K collapse into the T bucket.
RANK_INDEX = {
    "2": 0, "3": 1, "4": 2, "5": 3, "6": 4,
    "7": 5, "8": 6, "9": 7,
    "T": 8, "J": 8, "Q": 8, "K": 8,
    "A": 9,
}
NUM_BUCKETS = 10

# Value of each bucket with the ace counted as 11 (soft); Hand downgrades aces as needed.
HARD_VALUE = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11]


class Card(NamedTuple):
    rank: str
    suit: Optional[str] = None

    @property
    def bucket(self) -> int:
        return RANK_INDEX[self.rank]

    @property
    def is_red(self) -> bool:
        """Only meaningful for Red Seven counting (Phase 6); suit is otherwise decorative."""
        return self.suit in RED_SUITS


def advance_total(total: int, is_soft: bool, rank_idx: int) -> Tuple[int, bool]:
    """Add one card (by rank bucket index) to a running (total, is_soft) hand state.

    (total, is_soft) is a sufficient statistic for this: a stable, post-downgrade hand
    never has more than one ace still counted as 11 (two aces at 11 alone already sum
    to 22, forcing an immediate downgrade), so the exact ace count beyond that boolean
    never needs tracking. Shared by the dealer's draw recursion (dealer_probs.py) and
    the player's hit recursion (ev_solver.py) -- see ev_solver_conventions/SKILL.md.
    """
    aces_as_11 = 1 if is_soft else 0
    if rank_idx == RANK_INDEX["A"]:
        aces_as_11 += 1
    t = total + HARD_VALUE[rank_idx]
    while t > 21 and aces_as_11 > 0:
        t -= 10
        aces_as_11 -= 1
    return t, aces_as_11 > 0
