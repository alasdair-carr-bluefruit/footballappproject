"""Unit tests for the rotation plan validator."""

from datetime import date

from backend.algorithm.rotation_engine import generate_rotation
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import Position
from tests.conftest import make_player


class TestDEFRestriction:
    def test_def_restricted_player_never_in_def(self):
        restricted = make_player("Alice", def_restricted=True)
        squad = Squad(players=[
            restricted,
            make_player("Bob", GKTier.PREFERRED),
            *[make_player(f"P{i}") for i in range(7)],
        ])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        for slot in plan.slots:
            assert slot.lineup.get(Position.DEF) is not restricted, (
                f"DEF-restricted Alice found in DEF at slot {slot.slot_index}"
            )


class TestGKMidQuarterChange:
    def test_gk_same_within_quarter(self):
        squad = Squad(players=[
            make_player("GK", GKTier.PREFERRED),
            *[make_player(f"P{i}") for i in range(9)],
        ])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        for i in range(0, 8, 2):
            gk_first = plan.slots[i].gk
            gk_second = plan.slots[i + 1].gk
            assert gk_first is gk_second, (
                f"GK changed mid-quarter at Q{plan.slots[i].quarter}: "
                f"{getattr(gk_first, 'name', None)} → {getattr(gk_second, 'name', None)}"
            )


class TestMidQuarterSubLimit:
    def test_max_2_subs_mid_quarter(self):
        squad = Squad(players=[
            make_player("GK", GKTier.PREFERRED),
            *[make_player(f"P{i}") for i in range(9)],
        ])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        for i in range(0, 8, 2):
            players_before = set(plan.slots[i].players)
            players_after = set(plan.slots[i + 1].players)
            changes = len(players_before - players_after)
            assert changes <= 2, (
                f"Mid-quarter Q{plan.slots[i].quarter}: {changes} subs (max 2)"
            )


class TestPlayingTimeEquality:
    def test_10_players_all_get_4_slots(self):
        squad = Squad(players=[
            make_player("Specialist", GKTier.SPECIALIST),
            *[make_player(f"P{i}") for i in range(9)],
        ])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        for player in squad.available:
            assert plan.slot_count_for_player(player) == 4

    def test_9_players_no_specialist_max_diff_1(self):
        squad = Squad(players=[
            make_player("GK", GKTier.PREFERRED),
            *[make_player(f"P{i}") for i in range(8)],
        ])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        counts = [plan.slot_count_for_player(p) for p in squad.available]
        assert max(counts) - min(counts) <= 1
