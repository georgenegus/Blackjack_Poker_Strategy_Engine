"""Phase 10: scripts/poker/solve_preflop.py's helper functions
(parse_spec_key, format_strategy, _solver_hash). See
markdowns/poker/poker_build_plan_v1.md Phase 10.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.poker.solve_preflop import _solver_hash, format_strategy, parse_spec_key
from src.poker.spec import GameSpec


# --- parse_spec_key -----------------------------------------------------------


def test_parse_spec_key_round_trips_the_plans_example_spec():
    spec = parse_spec_key("hu-100bb-r5c3-s5")
    assert spec.key() == "hu-100bb-r5c3-s5"
    assert spec.num_players == 2
    assert spec.stack_bb == 100.0
    assert spec.rake_pct == pytest.approx(0.05)
    assert spec.rake_cap_bb == 3.0
    assert spec.bet_sizes == GameSpec().bet_sizes


def test_parse_spec_key_round_trips_arbitrary_default_bet_size_specs():
    for stack in (10.0, 20.5, 30.0, 200.0):
        original = GameSpec(stack_bb=stack)
        parsed = parse_spec_key(original.key())
        assert parsed.key() == original.key()


def test_parse_spec_key_raises_loudly_for_non_default_bet_size_counts():
    """A key like "s1" (one bet size) can't be reconstructed exactly -- the
    key only records the COUNT, not the values -- so this must raise rather
    than silently solving a different game than the one requested."""
    spec = GameSpec(stack_bb=10.0, bet_sizes=(1.0,))
    with pytest.raises(ValueError):
        parse_spec_key(spec.key())


def test_parse_spec_key_handles_6max():
    spec = parse_spec_key("6max-50bb-r5c3-s5")
    assert spec.num_players == 6
    assert spec.key() == "6max-50bb-r5c3-s5"


# --- format_strategy ------------------------------------------------------


def test_format_strategy_produces_every_class_at_the_root_infoset():
    """Every infoset actually touched during a solve must appear; using a
    strategy dict that covers ALL 169 classes at the root confirms the
    output structure (situation label, per-hand frequency dict) is right,
    independent of whether a real solve happened to visit every one."""
    import numpy as np

    from src.poker.ranges import CLASS_LABELS

    spec = GameSpec(stack_bb=10.0, bet_sizes=(1.0,))
    fake_avg_strategy = {(i, ()): np.array([0.7, 0.3]) for i in range(169)}  # root infoset for player 0

    out = format_strategy(fake_avg_strategy, spec)
    assert "BTN:open" in out
    assert set(out["BTN:open"].keys()) == set(CLASS_LABELS)
    for hand, freqs in out["BTN:open"].items():
        assert sum(freqs.values()) == pytest.approx(1.0, abs=1e-3)


def test_format_strategy_omits_infosets_never_visited():
    spec = GameSpec(stack_bb=10.0, bet_sizes=(1.0,))
    out = format_strategy({}, spec)
    assert out == {}


# --- _solver_hash --------------------------------------------------------


def test_solver_hash_is_deterministic_and_nonempty():
    h1 = _solver_hash()
    h2 = _solver_hash()
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest
