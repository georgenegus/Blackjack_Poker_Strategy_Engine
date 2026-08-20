"""N-deck shoe: 10-bucket rank composition, dealing, cut-card penetration."""

from typing import Optional

import numpy as np

from src.engine.cards import Card, NUM_BUCKETS, RANK_INDEX, SUITS

# Cards per bucket in one 52-card deck: 4 each of 2-9 and A, 16 of T (T/J/Q/K collapsed).
_DECK_COMPOSITION = np.array([4, 4, 4, 4, 4, 4, 4, 4, 16, 4], dtype=np.int64)
_BUCKET_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "A"]
_TEN_FACES = ["T", "J", "Q", "K"]


class Shoe:
    def __init__(self, num_decks: int, penetration: float = 0.75, rng: Optional[np.random.Generator] = None):
        self.num_decks = num_decks
        self.penetration = penetration
        self.composition = _DECK_COMPOSITION * num_decks
        self._initial_composition = self.composition.copy()
        self.total_cards = int(self.composition.sum())
        self.dealt = 0
        self._rng = rng if rng is not None else np.random.default_rng()

    @classmethod
    def from_composition(
        cls, composition, penetration: float = 0.75, rng: Optional[np.random.Generator] = None
    ) -> "Shoe":
        """Construct a hypothetical shoe from an explicit 10-bucket composition vector --
        used by the solver (Phase 3) and the count-index builder (Phase 7)."""
        shoe = cls.__new__(cls)
        shoe.num_decks = None
        shoe.penetration = penetration
        shoe.composition = np.array(composition, dtype=np.int64)
        shoe._initial_composition = shoe.composition.copy()
        shoe.total_cards = int(shoe.composition.sum())
        shoe.dealt = 0
        shoe._rng = rng if rng is not None else np.random.default_rng()
        return shoe

    @property
    def remaining(self) -> int:
        return int(self.composition.sum())

    @property
    def cut_card_reached(self) -> bool:
        return self.dealt / self.total_cards >= self.penetration

    def deal(self) -> Card:
        remaining = self.composition.sum()
        probs = self.composition / remaining
        bucket = int(self._rng.choice(NUM_BUCKETS, p=probs))
        self.composition[bucket] -= 1
        self.dealt += 1
        # Composition tracks only the 10 rank buckets (see cards.py) -- the exact face
        # within the T bucket and the suit are not tracked, so assign both uniformly at
        # deal time. This is exact for every rule and count system except Red Seven,
        # where red/black is an independent 50/50 draw per 7 regardless.
        rank = str(self._rng.choice(_TEN_FACES)) if bucket == RANK_INDEX["T"] else _BUCKET_RANKS[bucket]
        suit = str(self._rng.choice(SUITS))
        return Card(rank=rank, suit=suit)

    def reset(self) -> None:
        self.composition = self._initial_composition.copy()
        self.dealt = 0
