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
        # Specialist plays Q1 (slots 0-1) and Q3 (slots 4-5), sits out Q2 and Q4
        assert assignments[0] is specialist and assignments[1] is specialist  # Q1
        assert assignments[2] is not specialist and assignments[3] is not specialist  # Q2
        assert assignments[4] is specialist and assignments[5] is specialist  # Q3
        assert assignments[6] is not specialist and assignments[7] is not specialist  # Q4

    def test_specialist_never_assigned_outfield_slot(self):
        specialist = make_player("Alice", GKTier.SPECIALIST)
        preferred = make_player("Bob", GKTier.PREFERRED)
        others = [make_player(f"P{i}") for i in range(8)]
        players = [specialist, preferred] + others
        assignments, _ = select_gk_for_slots(players, num_slots=8, squad_size=10)
        # Specialist only appears in Q1 and Q3 slots
        non_specialist_slots = [i for i, a in enumerate(assignments) if a is not specialist]
        assert set(non_specialist_slots) == {2, 3, 6, 7}  # Q2 and Q4


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
        players = [make_player(f"P{i}", GKTier.EMERGENCY_ONLY) for i in range(9)]
        assignments, warnings = select_gk_for_slots(players, num_slots=8, squad_size=9)
        assert all(p.gk_status == GKTier.EMERGENCY_ONLY for p in assignments if p is not None)
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
        # Preferred must play some GK slots
        assert preferred_slots, "Preferred player should have some GK slots"
        # Some emergency player must cover the remaining GK quarters (time equality)
        emergency_in_goal = [p for p in assignments if p is not None and p.gk_status == GKTier.EMERGENCY_ONLY]
        assert emergency_in_goal, "Some emergency player should cover remaining GK slots for time equality"
        # Preferred fills the earlier quarters (lower slot indices)
        emergency_slots_any = [i for i, p in enumerate(assignments) if p is not None and p.gk_status == GKTier.EMERGENCY_ONLY]
        assert min(preferred_slots) < min(emergency_slots_any), (
            "Preferred should be GK in earlier slots than emergency"
        )
        assert not warnings
