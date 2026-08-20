"""Player/dealer hand: totals, softness, pair/blackjack/bust predicates."""

from typing import Iterable, List, Optional, Tuple, Union

from src.engine.cards import Card, HARD_VALUE, RANK_INDEX


def _as_card(card: Union[Card, str]) -> Card:
    return card if isinstance(card, Card) else Card(rank=card, suit=None)


class Hand:
    def __init__(self, cards: Optional[Iterable[Union[Card, str]]] = None, from_split: bool = False):
        self.cards: List[Card] = [_as_card(c) for c in (cards or [])]
        # A 21 made after a split is not a blackjack and pays even money, not blackjack_payout.
        self.from_split = from_split

    def add(self, card: Union[Card, str]) -> None:
        self.cards.append(_as_card(card))

    def _totals(self) -> Tuple[int, bool]:
        hard_total = 0
        aces_as_11 = 0
        for c in self.cards:
            hard_total += HARD_VALUE[RANK_INDEX[c.rank]]
            if c.rank == "A":
                aces_as_11 += 1
        total = hard_total
        while total > 21 and aces_as_11 > 0:
            total -= 10
            aces_as_11 -= 1
        return total, aces_as_11 > 0

    @property
    def total(self) -> int:
        return self._totals()[0]

    @property
    def is_soft(self) -> bool:
        return self._totals()[1]

    @property
    def is_bust(self) -> bool:
        return self.total > 21

    @property
    def is_blackjack(self) -> bool:
        return len(self.cards) == 2 and self.total == 21 and not self.from_split

    @property
    def is_pair(self) -> bool:
        """Two cards, same rank bucket -- T/J/Q/K count as equal (RuleSet.split_by_value=True)."""
        return len(self.cards) == 2 and self.cards[0].bucket == self.cards[1].bucket

    @property
    def is_pair_exact(self) -> bool:
        """Two cards, exactly the same literal rank -- for RuleSet.split_by_value=False."""
        return len(self.cards) == 2 and self.cards[0].rank == self.cards[1].rank

    def __repr__(self) -> str:
        ranks = ",".join(c.rank for c in self.cards)
        softness = "s" if self.is_soft else ""
        return f"Hand([{ranks}] total={self.total}{softness})"
