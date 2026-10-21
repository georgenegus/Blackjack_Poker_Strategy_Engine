"""Phase 1: GameSpec -- the single source of truth for every poker equity, EV,
frequency, and exploitability figure, playing the role src/engine/rules.py's
RuleSet plays on the blackjack side. See
.agents/skills/poker_solver_conventions/SKILL.md.

No function outside this module may hardcode a stack depth, rake, or bet-size
grid -- a new game type is a different GameSpec, never a branch on a string.
"""
from __future__ import annotations

from dataclasses import dataclass


def _fmt_num(x: float) -> str:
    if float(x) == int(x):
        return str(int(x))
    return f"{x:g}"


@dataclass(frozen=True)
class GameSpec:
    num_players: int = 2
    stack_bb: float = 100.0
    sb: float = 0.5
    bb: float = 1.0
    ante_bb: float = 0.0
    bb_ante: bool = False
    rake_pct: float = 0.05
    rake_cap_bb: float = 3.0
    no_flop_no_drop: bool = True
    bet_sizes: tuple[float, ...] = (0.33, 0.5, 0.75, 1.0, 1.5)
    allow_allin: bool = True
    raise_cap: int | None = None
    variant: str = "nlhe"

    def __post_init__(self) -> None:
        assert self.num_players >= 2, "num_players must be at least 2"
        assert self.stack_bb > 0, "stack_bb must be positive"
        assert self.sb > 0 and self.bb > 0, "sb and bb must be positive"
        assert self.ante_bb >= 0, "ante_bb must be non-negative"
        assert 0 <= self.rake_pct <= 1, "rake_pct must be in [0, 1]"
        assert self.rake_cap_bb >= 0, "rake_cap_bb must be non-negative"
        assert len(self.bet_sizes) > 0, "bet_sizes must not be empty"
        assert all(x > 0 for x in self.bet_sizes), "bet_sizes must all be positive"
        assert self.variant in ("nlhe", "lhe"), "variant must be 'nlhe' or 'lhe'"

    def key(self) -> str:
        """Deterministic short string, e.g. "hu-100bb-r5c3-s5". Used as the
        directory name for every cached solve and as the cache-manifest key --
        the poker analogue of RuleSet.key(). Two solves under different specs
        must never collide on this key, so every field that changes the game
        being solved (not just cosmetic fields) is represented here.
        """
        players = "hu" if self.num_players == 2 else f"{self.num_players}max"
        stack = f"{_fmt_num(self.stack_bb)}bb"
        rake = f"r{_fmt_num(self.rake_pct * 100)}c{_fmt_num(self.rake_cap_bb)}"
        sizes = f"s{len(self.bet_sizes)}"
        parts = [players, stack, rake, sizes]
        if self.ante_bb:
            ante_tag = "bba" if self.bb_ante else "a"
            parts.append(f"{ante_tag}{_fmt_num(self.ante_bb)}")
        if not self.no_flop_no_drop:
            parts.append("nfnd0")
        if self.raise_cap is not None:
            parts.append(f"cap{self.raise_cap}")
        if self.variant != "nlhe":
            parts.append(self.variant)
        return "-".join(parts)

    def pot_after_rake(self, pot_bb: float, saw_flop: bool) -> float:
        """The single place rake is ever applied. No other module computes rake."""
        if self.no_flop_no_drop and not saw_flop:
            return pot_bb
        rake = min(pot_bb * self.rake_pct, self.rake_cap_bb)
        return pot_bb - rake
