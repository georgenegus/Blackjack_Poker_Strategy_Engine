"""RuleSet -- the single source of truth for every blackjack rule variant.

Every EV, strategy decision, and house-edge figure downstream is a function of
a RuleSet instance, never a hardcoded assumption about deck count, S17/H17,
DAS, or payout. See .agents/instructions.md's "RuleSet Is the Single Source
of Truth" section.
"""

from dataclasses import dataclass
from fractions import Fraction

_SURRENDER_CODES = {"late": "ls", "early": "es", "none": "ns"}


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
        if not self.split_by_value:
            parts.append("novalsplit")
        return "-".join(parts)
