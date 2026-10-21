"""Phase 9: Kelly criterion bet sizing. See the build plan's Phase 9
[!IMPORTANT] -- half-Kelly (the default) isn't conservatism for its own sake,
it's the standard hedge against a counter's edge ESTIMATE carrying real
uncertainty (from the Phase 8 edge model's fit, from deck-count estimation
error, and from the count itself being a lossy summary of the shoe).
Overbetting relative to a mis-estimated edge is punished far more severely
than underbetting.

`edge` always comes from Phase 8's edge model, never a hardcoded constant --
see src.counting.edge_model.predict_edge(). This module itself is edge-model-
agnostic (a numeric edge in, a bet size out) -- the caller (bet_ramp.py) is
what sweeps true counts through the model. In dual-system mode (Phase 6), the
true_count fed into predict_edge() must always be the BETTING-system
counter's, never the playing counter's -- the edge model's fit is keyed to
one specific system.
"""


def kelly_fraction(edge: float, variance: float = 1.3, fraction: float = 0.5) -> float:
    """Growth-optimal fraction of bankroll to wager, scaled by `fraction`
    (half-Kelly default). Floors at 0 -- Kelly never recommends betting on a
    negative-edge game; the "must bet something anyway" case (a player who
    can't leave the table) is kelly_bet's own chip/table-min clamping, applied
    honestly rather than pretending a forced floor bet is free."""
    return max(0.0, fraction * edge / variance)


def clamp_and_round(raw_bet: float, table_min: float, table_max: float, chip: float) -> float:
    """Round to the nearest chip denomination, then clamp to the table's
    limits -- a $38.46 Kelly bet isn't a real bet a casino will take. Clamping
    up to table_min even when the raw bet is 0 (or negative-edge) is
    deliberate: it's what makes kelly_bet's floor-at-table-min behavior fall
    out naturally rather than needing a special case."""
    rounded = round(raw_bet / chip) * chip
    return max(table_min, min(table_max, rounded))


def kelly_bet(
    bankroll: float,
    edge: float,
    variance: float = 1.3,
    fraction: float = 0.5,
    table_min: float = 10,
    table_max: float = 1000,
    chip: float = 5,
) -> float:
    """The bet a real casino will actually let you place: half-Kelly's fraction
    of `bankroll`, rounded to `chip` and clamped to [table_min, table_max]."""
    raw = kelly_fraction(edge, variance, fraction) * bankroll
    return clamp_and_round(raw, table_min, table_max, chip)
