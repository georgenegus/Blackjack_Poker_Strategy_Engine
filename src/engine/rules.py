"""RuleSet -- the single source of truth for every blackjack rule variant.

Every EV, strategy decision, and house-edge figure downstream is a function of
a RuleSet instance, never a hardcoded assumption about deck count, S17/H17,
DAS, or payout. See .agents/instructions.md's "RuleSet Is the Single Source
of Truth" section.
"""

import itertools
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterator

_SURRENDER_CODES = {"late": "ls", "early": "es", "none": "ns"}
DOUBLE_RANGES = {"any": None, "9-11": {9, 10, 11}, "10-11": {10, 11}}

# The 32 rulesets scripts/build_all_grids.py, build_all_indices.py, and app.py's
# startup registries all pre-solve/load -- the one definition, not three copies
# to keep in sync (all three used to define this independently).
SHIPPED_DECKS = (2, 4, 6, 8)
SHIPPED_H17_OPTIONS = (False, True)
SHIPPED_DAS_OPTIONS = (True, False)
SHIPPED_SURRENDER_OPTIONS = ("late", "none")


@dataclass(frozen=True)
class RuleSet:
    num_decks: int = 6
    dealer_hits_soft_17: bool = False
    blackjack_payout: Fraction = Fraction(3, 2)
    double_after_split: bool = True
    double_on: str = "any"            # "any" | "9-11" | "10-11"
    surrender: str = "late"           # "late" | "early" | "none"
    resplit_to: int = 4
    resplit_aces: bool = False
    hit_split_aces: bool = False
    dealer_peeks: bool = True
    obbo: bool = False                # "original bets only": under no-peek, a dealer blackjack
                                       # revealed after the player has doubled/split costs only the
                                       # original bet, not the doubled/split additions. Irrelevant
                                       # when dealer_peeks=True.
    penetration: float = 0.75
    split_by_value: bool = True       # True: T/J/Q/K mutually splittable

    def key(self) -> str:
        """Short deterministic id, e.g. '6d-s17-das-ls-p75' -- the cache-manifest key
        and the filename stem for this ruleset's solved grid/index files."""
        parts = [
            f"{self.num_decks}d",
            "h17" if self.dealer_hits_soft_17 else "s17",
            "das" if self.double_after_split else "ndas",
            _SURRENDER_CODES[self.surrender],
            f"p{round(self.penetration * 100)}",
        ]
        if self.double_on != "any":
            parts.append("do" + self.double_on.replace("-", ""))
        if self.blackjack_payout != Fraction(3, 2):
            parts.append(f"bj{self.blackjack_payout.numerator}{self.blackjack_payout.denominator}")
        if self.resplit_to != 4:
            parts.append(f"rs{self.resplit_to}")
        if self.resplit_aces:
            parts.append("rsa")
        if self.hit_split_aces:
            parts.append("hsa")
        if not self.dealer_peeks:
            parts.append("nopeek")
            if self.obbo:
                parts.append("obbo")
        if not self.split_by_value:
            parts.append("novalsplit")
        return "-".join(parts)


def double_allowed(rules: RuleSet, total: int, is_soft: bool) -> bool:
    """Whether rules.double_on permits doubling a 2-card hand with this total.
    Shared by game.py (mechanics) and grid_builder.py (solving) so the two never
    drift apart on what "double_on" means."""
    allowed = DOUBLE_RANGES[rules.double_on]
    hard_equivalent = total - 10 if is_soft else total
    return allowed is None or hard_equivalent in allowed


def shipped_rulesets() -> Iterator[RuleSet]:
    """Every ruleset this project pre-solves and ships (2/4/6/8 decks x S17/H17
    x DAS/no-DAS x late/no surrender = 32) -- all other fields left at their
    RuleSet defaults."""
    for decks, h17, das, surrender in itertools.product(
        SHIPPED_DECKS, SHIPPED_H17_OPTIONS, SHIPPED_DAS_OPTIONS, SHIPPED_SURRENDER_OPTIONS
    ):
        yield RuleSet(num_decks=decks, dealer_hits_soft_17=h17, double_after_split=das, surrender=surrender)
