"""Unit tests for the rotation engine entry point."""

import pytest
from datetime import date

from backend.models.player import GKTier
from backend.models.match import Match, Squad
from backend.models.rotation import Position
from backend.algorithm.rotation_engine import generate_rotation
from tests.conftest import make_player


class TestBasicGeneration:
    def test_generates_8_slots_for_4_quarter_match(self):
        squad = Squad(players=[
            make_player("GK", GKTier.PREFERRED),
            *[make_player(f"P{i}") for i in range(9)],
        ])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        assert len(plan.slots) == 8

    def test_each_slot_has_5_players(self):
        squad = Squad(players=[
            make_player("GK", GKTier.PREFERRED),
            *[make_player(f"P{i}") for i in range(9)],
        ])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        for slot in plan.slots:
            assert len(slot.lineup) == 5, (
                f"Slot {slot.slot_index} has {len(slot.lineup)} players, expected 5"
            )

    def test_each_slot_has_exactly_one_gk(self):
        squad = Squad(players=[
            make_player("GK", GKTier.PREFERRED),
            *[make_player(f"P{i}") for i in range(9)],
        ])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        for slot in plan.slots:
            gk_count = sum(1 for pos in slot.lineup if pos == Position.GK)
            assert gk_count == 1, f"Slot {slot.slot_index} has {gk_count} GKs"

    def test_raises_for_squad_under_5(self):
        squad = Squad(players=[make_player(f"P{i}") for i in range(4)])
        match = Match(date=date(2026, 3, 23))
        with pytest.raises(ValueError, match="Squad too small"):
            generate_rotation(squad, match)

    def test_no_violations_in_valid_squad(self):
        squad = Squad(players=[
            make_player("Specialist", GKTier.SPECIALIST),
            make_player("Preferred", GKTier.PREFERRED),
            *[make_player(f"P{i}") for i in range(8)],
        ])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        violations = [w for w in plan.warnings if w.startswith("VIOLATION")]
        assert not violations, f"Unexpected violations: {violations}"
