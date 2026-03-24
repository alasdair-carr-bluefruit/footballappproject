"""Unit tests for skill_balancer module."""
from __future__ import annotations

from datetime import date

import pytest

from backend.algorithm.rotation_engine import generate_rotation
from backend.algorithm.skill_balancer import balance_skills
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import Position, RotationPlan, SlotAssignment
from tests.conftest import make_player


def _make_slot(slot_index: int, gk, outfield: list) -> SlotAssignment:
    slot = SlotAssignment(slot_index=slot_index)
    slot.lineup[Position.GK] = gk
    positions = [Position.DEF, Position.MID1, Position.MID2, Position.FWD]
    for pos, player in zip(positions, outfield):
        slot.lineup[pos] = player
    return slot


class TestBalanceSkills:
    def test_returns_rotation_plan(self):
        specialist = make_player("GK", GKTier.SPECIALIST, skill_rating=3)
        players = [make_player(f"P{i}", skill_rating=3) for i in range(4)]
        slots = [_make_slot(i, specialist, players) for i in range(8)]
        plan = RotationPlan(slots=slots)
        result = balance_skills(plan)
        assert isinstance(result, RotationPlan)
        assert len(result.slots) == 8

    def test_does_not_mutate_original(self):
        specialist = make_player("GK", GKTier.SPECIALIST, skill_rating=3)
        high = make_player("High", skill_rating=5)
        low = make_player("Low", skill_rating=1)
        mid1 = make_player("Mid1", skill_rating=3)
        mid2 = make_player("Mid2", skill_rating=3)
        outfield = [high, low, mid1, mid2]
        slots = [_make_slot(i, specialist, outfield) for i in range(8)]
        plan = RotationPlan(slots=slots)
        original_totals = [s.outfield_skill_total for s in plan.slots]
        balance_skills(plan)
        after_totals = [s.outfield_skill_total for s in plan.slots]
        assert original_totals == after_totals

    def test_warnings_preserved(self):
        specialist = make_player("GK", GKTier.SPECIALIST, skill_rating=3)
        players = [make_player(f"P{i}", skill_rating=3) for i in range(4)]
        slots = [_make_slot(i, specialist, players) for i in range(8)]
        plan = RotationPlan(slots=slots, warnings=["test warning"])
        result = balance_skills(plan)
        assert "test warning" in result.warnings

    def test_reduces_variance_on_polarised_squad(self):
        """Balancer should improve skill variance when skills are very unequal."""
        squad = Squad(players=[
            make_player("GK", GKTier.SPECIALIST, skill_rating=3),
            make_player("H1", GKTier.PREFERRED, skill_rating=5),
            make_player("H2", skill_rating=5),
            make_player("H3", skill_rating=5),
            make_player("H4", skill_rating=5),
            make_player("L1", skill_rating=1),
            make_player("L2", skill_rating=1),
            make_player("L3", skill_rating=1),
            make_player("L4", skill_rating=1),
            make_player("L5", skill_rating=1),
        ])
        match = Match(date=date(2026, 3, 24))
        plan = generate_rotation(squad, match)
        totals = [s.outfield_skill_total for s in plan.slots]
        mean = sum(totals) / len(totals)
        variance = sum((t - mean) ** 2 for t in totals) / len(totals)
        # With 4 high (skill=5) and 5 low (skill=1) players, perfect balance
        # is hard but variance should be under 4 after balancing
        assert variance <= 4.0, f"Variance still too high after balancing: {variance:.2f}, totals: {totals}"

    def test_def_restricted_not_moved_to_def(self):
        """Balancer must not move a DEF-restricted player into DEF."""
        squad = Squad(players=[
            make_player("GK", GKTier.SPECIALIST, skill_rating=3),
            make_player("Restricted", GKTier.PREFERRED, skill_rating=5, def_restricted=True),
            make_player("H1", skill_rating=5),
            make_player("H2", skill_rating=5),
            make_player("L1", skill_rating=1),
            make_player("L2", skill_rating=1),
            make_player("L3", skill_rating=1),
            make_player("L4", skill_rating=1),
            make_player("L5", skill_rating=1),
            make_player("L6", skill_rating=1),
        ])
        match = Match(date=date(2026, 3, 24))
        plan = generate_rotation(squad, match)
        restricted = next(p for p in squad.available if p.def_restricted)
        for slot in plan.slots:
            assert slot.lineup.get(Position.DEF) is not restricted, (
                f"DEF-restricted player found in DEF at slot {slot.slot_index}"
            )
