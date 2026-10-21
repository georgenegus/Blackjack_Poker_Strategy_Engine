"""Card-counting tag vectors -- see .agents/skills/counting_systems_conventions/SKILL.md
and the build plan's Phase 6 for the table this encodes and why each field exists.

Betting Correlation (BC) and Playing Efficiency (PE) are published, fixed metrics
carried purely for the UI to display alongside each system -- they don't feed the
count arithmetic itself, which is exact regardless of BC/PE.
"""

from dataclasses import dataclass
from typing import Callable, Tuple

from src.engine.cards import Card, NUM_BUCKETS, RANK_INDEX

# One entry per rank bucket (2,3,4,5,6,7,8,9,T,A -- see cards.py). Red 7's "7" entry is
# 0.5 for DISPLAY ONLY (the published average of +1 red / 0 black) -- CountingSystem.tag_for
# resolves the real per-card value by suit for that one system, never by reading this tuple
# at index 7.
TagVector = Tuple[float, float, float, float, float, float, float, float, float, float]


def _zero_irc(_num_decks: int) -> float:
    return 0.0


def _ko_irc(num_decks: int) -> float:
    return -4.0 * (num_decks - 1)


def _red_seven_irc(num_decks: int) -> float:
    return -2.0 * num_decks


@dataclass(frozen=True)
class CountingSystem:
    name: str
    level: int
    tags: TagVector
    balanced: bool
    betting_correlation: float
    playing_efficiency: float
    irc_fn: Callable[[int], float] = _zero_irc
    needs_ace_side_count: bool = False
    is_red_seven: bool = False

    @property
    def slug(self) -> str:
        """Filesystem/URL-safe id, e.g. "hi-lo", "hi-opt-i" -- used in the
        data/indices/{ruleset_key}__{system}.json cache filename (Phase 7)."""
        return self.name.lower().replace(" ", "-")

    def irc(self, num_decks: int) -> float:
        """Initial running count for a fresh num_decks-deck shoe."""
        return self.irc_fn(num_decks)

    def tag_for(self, card: Card) -> float:
        """The count value of one specific dealt card."""
        if self.is_red_seven and card.rank == "7":
            return 1.0 if card.is_red else 0.0
        return self.tags[RANK_INDEX[card.rank]]


HI_LO = CountingSystem(
    name="Hi-Lo", level=1,
    tags=(1, 1, 1, 1, 1, 0, 0, 0, -1, -1),
    balanced=True, betting_correlation=0.97, playing_efficiency=0.51,
)

KO = CountingSystem(
    name="KO", level=1,
    tags=(1, 1, 1, 1, 1, 1, 0, 0, -1, -1),
    balanced=False, betting_correlation=0.98, playing_efficiency=0.55,
    irc_fn=_ko_irc,
)

HI_OPT_I = CountingSystem(
    name="Hi-Opt I", level=1,
    tags=(0, 1, 1, 1, 1, 0, 0, 0, -1, 0),
    balanced=True, betting_correlation=0.88, playing_efficiency=0.61,
    needs_ace_side_count=True,
)

HI_OPT_II = CountingSystem(
    name="Hi-Opt II", level=2,
    tags=(1, 1, 2, 2, 1, 1, 0, 0, -2, 0),
    balanced=True, betting_correlation=0.91, playing_efficiency=0.67,
    needs_ace_side_count=True,
)

OMEGA_II = CountingSystem(
    name="Omega II", level=2,
    tags=(1, 1, 2, 2, 2, 1, 0, -1, -2, 0),
    balanced=True, betting_correlation=0.92, playing_efficiency=0.67,
    needs_ace_side_count=True,
)

ZEN = CountingSystem(
    name="Zen", level=2,
    tags=(1, 1, 2, 2, 2, 1, 0, 0, -2, -1),
    balanced=True, betting_correlation=0.96, playing_efficiency=0.63,
)

RED_7 = CountingSystem(
    name="Red 7", level=1,
    tags=(1, 1, 1, 1, 1, 0.5, 0, 0, -1, -1),
    balanced=False, betting_correlation=0.98, playing_efficiency=0.54,
    irc_fn=_red_seven_irc, is_red_seven=True,
)

ALL_SYSTEMS: Tuple[CountingSystem, ...] = (HI_LO, KO, HI_OPT_I, HI_OPT_II, OMEGA_II, ZEN, RED_7)


def system_for_slug(slug: str) -> CountingSystem:
    """Looks up a system by its slug (e.g. "hi-lo", "hi-opt-i") -- the one
    definition shared by scripts/build_all_indices.py, run_sim_battery.py, and
    app.py (Phase 10), rather than three copies of the same lookup."""
    for s in ALL_SYSTEMS:
        if s.slug == slug:
            return s
    known = ", ".join(s.slug for s in ALL_SYSTEMS)
    raise ValueError(f"Unknown system {slug!r}; known: {known}")
SYSTEMS_BY_NAME = {s.name: s for s in ALL_SYSTEMS}

DEFAULT_SYSTEM = HI_LO   # highest BC of the level-1 balanced systems; every published index is quoted for it

assert len(HI_LO.tags) == NUM_BUCKETS
