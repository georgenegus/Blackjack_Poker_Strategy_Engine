"""Running/true count tracking for a single card-counting system, and the paired
(betting-system, playing-system) mode from the build plan's Phase 6 Step 3.

See .agents/skills/counting_systems_conventions/SKILL.md for the IRC and true-count
rounding conventions this implements.
"""

import math
from typing import Literal, Optional, Tuple

from src.engine.cards import Card
from src.counting.systems import CountingSystem

TCRounding = Literal["floor", "nearest", "truncate"]
_ROUNDERS = {
    "floor": math.floor,
    "nearest": round,
    "truncate": math.trunc,
}


class Counter:
    def __init__(
        self,
        system: CountingSystem,
        num_decks: int,
        tc_rounding: TCRounding = "floor",
        tc_resolution: float = 0.5,
    ):
        if tc_rounding not in _ROUNDERS:
            raise ValueError(f"Unknown tc_rounding {tc_rounding!r}; expected one of {sorted(_ROUNDERS)}")
        self.system = system
        self.num_decks = num_decks
        self.tc_rounding = tc_rounding
        self.tc_resolution = tc_resolution
        self.total_cards = num_decks * 52
        self.dealt = 0
        self.aces_seen = 0
        self.running_count = system.irc(num_decks)

    def see(self, card: Card) -> None:
        """Register one dealt card. Order-independent -- a running sum, not a lookup."""
        self.running_count += self.system.tag_for(card)
        self.dealt += 1
        if card.rank == "A":
            self.aces_seen += 1

    def reset(self) -> None:
        """Back to a fresh num_decks-deck shoe's IRC -- for a reshuffle (Phase 8's
        simulator battery reshuffles the underlying Shoe at the cut card; the
        counter must reset in step with it)."""
        self.dealt = 0
        self.aces_seen = 0
        self.running_count = self.system.irc(self.num_decks)

    @property
    def decks_remaining_exact(self) -> float:
        return (self.total_cards - self.dealt) / 52

    @property
    def decks_remaining(self) -> float:
        """Decks remaining, floored to tc_resolution -- a real player estimates this
        from the discard tray in coarse increments, not by exact card counting.
        Clamped to at least one resolution unit so true_count stays finite as the
        shoe empties; card-counting practice stops well before this at the cut card."""
        exact = self.decks_remaining_exact
        floored = math.floor(exact / self.tc_resolution) * self.tc_resolution
        return max(floored, self.tc_resolution)

    def true_count(self, rounding: Optional[TCRounding] = None) -> float:
        """Raises for unbalanced systems (KO, Red 7) -- they're designed to be played
        directly off running_count, never converted."""
        if not self.system.balanced:
            raise ValueError(
                f"{self.system.name} is an unbalanced system -- use running_count directly, not true_count"
            )
        rounder = _ROUNDERS[rounding or self.tc_rounding]
        return rounder(self.running_count / self.decks_remaining)

    @classmethod
    def paired(
        cls,
        betting_system: CountingSystem,
        playing_system: CountingSystem,
        num_decks: int,
        **kwargs,
    ) -> Tuple["Counter", "Counter"]:
        """Two independently-advancing counters over the same dealt-card stream (Phase
        6's dual-system mode) -- e.g. Hi-Lo for bet sizing, Omega II for play
        deviations. Feed every dealt card to BOTH returned counters' .see(); they share
        no state, so this is equivalent to (and tested against) constructing each
        separately."""
        betting = cls(betting_system, num_decks, **kwargs)
        playing = cls(playing_system, num_decks, **kwargs)
        return betting, playing
