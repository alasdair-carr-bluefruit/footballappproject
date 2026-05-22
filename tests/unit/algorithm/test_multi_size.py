"""Tests for rotation generation across different team sizes."""
import pytest

from backend.algorithm.rotation_engine import generate_rotation
from backend.models.game_config import get_config
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import normalize_position
from tests.conftest import make_player

from datetime import date


def _squad(n: int, specialist: bool = True) -> Squad:
    """Generate a squad of n players with optional GK specialist."""
    players = []
    if specialist:
        players.append(make_player("Specialist", GKTier.SPECIALIST))
        for i in range(2, n + 1):
            players.append(make_player(f"P{i}", GKTier.EMERGENCY_ONLY, skill_rating=(i % 5) + 1))
    else:
        players.append(make_player("Preferred", GKTier.PREFERRED, skill_rating=3))
        for i in range(2, n + 1):
            players.append(make_player(f"P{i}", GKTier.EMERGENCY_ONLY, skill_rating=(i % 5) + 1))
    return players


def _match_with_config(team_size: int, formation: str) -> Match:
    config = get_config(team_size, formation)
    return Match(date=date(2026, 6, 1), game_config=config)


@pytest.mark.unit
class TestMultiSize5v5:
    def test_5v5_1_2_1_generates_8_slots(self):
        match = _match_with_config(5, "1-2-1")
        squad = Squad(players=_squad(10))
        plan = generate_rotation(squad, match)
        assert len(plan.slots) == 8

    def test_5v5_each_slot_has_5_players(self):
        match = _match_with_config(5, "1-2-1")
        squad = Squad(players=_squad(10))
        plan = generate_rotation(squad, match)
        for slot in plan.slots:
            assert len(slot.players) == 5, f"Slot {slot.slot_index} has {len(slot.players)} players"

    def test_5v5_2_1_1_formation(self):
        match = _match_with_config(5, "2-1-1")
        squad = Squad(players=_squad(10))
        plan = generate_rotation(squad, match)
        assert len(plan.slots) == 8
        for slot in plan.slots:
            assert len(slot.players) == 5
            positions = set(slot.lineup.keys())
            assert "GK" in {p.value for p in positions}


@pytest.mark.unit
class TestMultiSize7v7:
    def test_7v7_generates_8_slots(self):
        match = _match_with_config(7, "2-3-1")
        squad = Squad(players=_squad(12))
        plan = generate_rotation(squad, match)
        assert len(plan.slots) == 8

    def test_7v7_each_slot_has_7_players(self):
        match = _match_with_config(7, "2-3-1")
        squad = Squad(players=_squad(12))
        plan = generate_rotation(squad, match)
        for slot in plan.slots:
            assert len(slot.players) == 7, f"Slot {slot.slot_index} has {len(slot.players)} players"

    def test_7v7_correct_positions(self):
        match = _match_with_config(7, "2-3-1")
        squad = Squad(players=_squad(12))
        plan = generate_rotation(squad, match)
        expected = {"GK", "DEF", "DEF2", "MID1", "MID2", "MID3", "FWD"}
        for slot in plan.slots:
            pos_names = {p.value for p in slot.lineup.keys()}
            assert pos_names == expected, f"Slot {slot.slot_index}: {pos_names}"

    def test_7v7_gk_same_within_period(self):
        match = _match_with_config(7, "2-3-1")
        squad = Squad(players=_squad(12))
        plan = generate_rotation(squad, match)
        for q in range(4):
            h1_gk = plan.slots[q * 2].gk
            h2_gk = plan.slots[q * 2 + 1].gk
            assert h1_gk is h2_gk, f"GK changed mid-period in Q{q+1}"

    def test_7v7_mid_period_max_3_subs(self):
        match = _match_with_config(7, "2-3-1")
        squad = Squad(players=_squad(12))
        plan = generate_rotation(squad, match)
        for q in range(4):
            h1_players = set(plan.slots[q * 2].players)
            h2_players = set(plan.slots[q * 2 + 1].players)
            changes = len(h1_players - h2_players)
            assert changes <= 3, f"Q{q+1}: {changes} mid-period changes (max 3)"

    def test_7v7_playing_time_near_equal(self):
        match = _match_with_config(7, "2-3-1")
        squad = Squad(players=_squad(12))
        plan = generate_rotation(squad, match)
        counts = [plan.slot_count_for_player(p) for p in squad.available]
        # Allow up to 2 slot diff: specialist GK may undershoot target
        # since they can't play outfield, causing redistribution
        assert max(counts) - min(counts) <= 2


@pytest.mark.unit
class TestMultiSize9v9:
    def test_9v9_generates_4_slots(self):
        match = _match_with_config(9, "3-3-2")
        squad = Squad(players=_squad(14))
        plan = generate_rotation(squad, match)
        assert len(plan.slots) == 4

    def test_9v9_each_slot_has_9_players(self):
        match = _match_with_config(9, "3-3-2")
        squad = Squad(players=_squad(14))
        plan = generate_rotation(squad, match)
        for slot in plan.slots:
            assert len(slot.players) == 9, f"Slot {slot.slot_index} has {len(slot.players)} players"

    def test_9v9_correct_positions(self):
        match = _match_with_config(9, "3-3-2")
        squad = Squad(players=_squad(14))
        plan = generate_rotation(squad, match)
        expected = {"GK", "DEF", "DEF2", "DEF3", "MID1", "MID2", "MID3", "FWD", "FWD2"}
        for slot in plan.slots:
            pos_names = {p.value for p in slot.lineup.keys()}
            assert pos_names == expected, f"Slot {slot.slot_index}: {pos_names}"

    def test_9v9_mid_period_max_4_subs(self):
        match = _match_with_config(9, "3-3-2")
        squad = Squad(players=_squad(14))
        plan = generate_rotation(squad, match)
        # Only 1 mid-period transition per half (slot 0→1, slot 2→3)
        for h in range(2):
            h1 = set(plan.slots[h * 2].players)
            h2 = set(plan.slots[h * 2 + 1].players)
            changes = len(h1 - h2)
            assert changes <= 4, f"H{h+1}: {changes} mid-half changes (max 4)"


@pytest.mark.unit
class TestMultiSize11v11:
    def test_11v11_generates_4_slots(self):
        match = _match_with_config(11, "4-4-2")
        squad = Squad(players=_squad(16))
        plan = generate_rotation(squad, match)
        assert len(plan.slots) == 4

    def test_11v11_each_slot_has_11_players(self):
        match = _match_with_config(11, "4-4-2")
        squad = Squad(players=_squad(16))
        plan = generate_rotation(squad, match)
        for slot in plan.slots:
            assert len(slot.players) == 11, f"Slot {slot.slot_index} has {len(slot.players)} players"

    def test_11v11_correct_positions(self):
        match = _match_with_config(11, "4-4-2")
        squad = Squad(players=_squad(16))
        plan = generate_rotation(squad, match)
        expected = {"GK", "DEF", "DEF2", "DEF3", "DEF4", "MID1", "MID2", "MID3", "MID4", "FWD", "FWD2"}
        for slot in plan.slots:
            pos_names = {p.value for p in slot.lineup.keys()}
            assert pos_names == expected, f"Slot {slot.slot_index}: {pos_names}"


@pytest.mark.unit
class TestMinimumSquad:
    def test_squad_too_small_for_7v7(self):
        match = _match_with_config(7, "2-3-1")
        squad = Squad(players=_squad(6))
        with pytest.raises(ValueError, match="need at least 7"):
            generate_rotation(squad, match)

    def test_squad_too_small_for_11v11(self):
        match = _match_with_config(11, "4-4-2")
        squad = Squad(players=_squad(10))
        with pytest.raises(ValueError, match="need at least 11"):
            generate_rotation(squad, match)
