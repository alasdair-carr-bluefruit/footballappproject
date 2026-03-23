"""Unit tests for gk_selector module."""

import pytest
from backend.models.player import GKTier, Player
from backend.algorithm.gk_selector import select_gk_for_slots
from tests.conftest import make_player


class TestSpecialistPresent:
    def test_specialist_plays_all_slots_squad_under_10(self):
        specialist = make_player("Alice", GKTier.SPECIALIST)
        others = [make_player(f"P{i}") for i in range(7)]
        players = [specialist] + others
        assignments, warnings = select_gk_for_slots(players, num_slots=8, squad_size=8)
        assert all(a is specialist for a in assignments)
        assert not warnings

    def test_specialist_plays_first_4_slots_squad_of_10(self):
        specialist = make_player("Alice", GKTier.SPECIALIST)
        preferred = make_player("Bob", GKTier.PREFERRED)
        others = [make_player(f"P{i}") for i in range(8)]
        players = [specialist, preferred] + others
        assignments, warnings = select_gk_for_slots(players, num_slots=8, squad_size=10)
        assert all(a is specialist for a in assignments[:4])
        assert all(a is not specialist for a in assignments[4:])

    def test_specialist_never_assigned_outfield_slot(self):
        specialist = make_player("Alice", GKTier.SPECIALIST)
        preferred = make_player("Bob", GKTier.PREFERRED)
        others = [make_player(f"P{i}") for i in range(8)]
        players = [specialist, preferred] + others
        assignments, _ = select_gk_for_slots(players, num_slots=8, squad_size=10)
        # None of the non-GK slots should be the specialist
        assert specialist not in assignments[4:]


class TestNoSpecialist:
    def test_preferred_used_before_can_play(self):
        preferred = make_player("Bob", GKTier.PREFERRED)
        can_play = make_player("Carol", GKTier.CAN_PLAY)
        others = [make_player(f"P{i}") for i in range(7)]
        players = [preferred, can_play] + others
        assignments, warnings = select_gk_for_slots(players, num_slots=8, squad_size=9)
        # Preferred player should appear in GK assignments
        assert preferred in assignments
        assert not warnings

    def test_emergency_only_triggers_warning(self):
        emergency = make_player("Eve", GKTier.EMERGENCY_ONLY)
        others = [make_player(f"P{i}") for i in range(8)]
        players = [emergency] + others
        assignments, warnings = select_gk_for_slots(players, num_slots=8, squad_size=9)
        assert emergency in assignments
        assert any("emergency" in w.lower() for w in warnings)

    def test_preferred_before_emergency(self):
        """Preferred fills GK first (within their time budget), then emergency covers the rest.

        With squad=9 and fair_share=4, each player can cover at most 2 GK quarters.
        Preferred covers Q1+Q2, emergency covers Q3+Q4 — preferred IS first.
        Emergency is used for the remaining quarters to maintain time equality.
        """
        preferred = make_player("Bob", GKTier.PREFERRED)
        emergency = make_player("Eve", GKTier.EMERGENCY_ONLY)
        others = [make_player(f"P{i}") for i in range(7)]
        players = [preferred, emergency] + others
        assignments, warnings = select_gk_for_slots(players, num_slots=8, squad_size=9)
        # Preferred fills GK slots BEFORE emergency (chronological priority)
        preferred_slots = [i for i, p in enumerate(assignments) if p is preferred]
        emergency_slots = [i for i, p in enumerate(assignments) if p is emergency]
        assert preferred_slots, "Preferred player should have some GK slots"
        assert emergency_slots, "Emergency should cover remaining GK slots for time equality"
        # Preferred should cover more or equal GK slots than any single emergency player
        assert len(preferred_slots) >= len(emergency_slots)
        # Preferred fills the earlier quarters (lower slot indices)
        assert min(preferred_slots) < min(emergency_slots), (
            "Preferred should be GK in earlier slots than emergency"
        )
        assert not warnings
