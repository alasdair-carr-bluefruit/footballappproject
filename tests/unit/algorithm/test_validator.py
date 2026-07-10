"""Unit tests for the rotation plan validator."""

from datetime import date

from backend.algorithm.rotation_engine import generate_rotation
from backend.algorithm.validator import validate
from backend.models.game_config import build_tournament_config
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
        from backend.models.rotation import normalize_position
        for slot in plan.slots:
            for pos, player in slot.lineup.items():
                if normalize_position(pos) == "DEF":
                    assert player is not restricted, (
                        f"DEF-restricted Alice found in {pos} at slot {slot.slot_index}"
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


class TestConsecutiveSitOut:
    """Issue1: a player benched for an entire tournament match must be
    guaranteed at least one slot in the next match (fairness <= 50)."""

    def test_bench_player_prioritised_into_next_match(self):
        # Short tournament match (no halftime): 2 slots x 5 players = 10 slots
        # for a 12-player squad — some players necessarily get 0 slots, mirroring
        # the real Issue1 scenario (single-period tournament matches).
        squad = Squad(players=[make_player(f"P{i}") for i in range(12)])
        match = Match(date=date(2026, 3, 23))
        match.fairness = "equal"
        match.game_config = build_tournament_config(5, "1-2-1", 10, False)

        match1_plan = generate_rotation(squad, match)
        benched_in_match1 = {
            p for p in squad.available if match1_plan.slot_count_for_player(p) == 0
        }
        assert benched_in_match1, "test setup expects at least one player to sit out match 1"

        match2_plan = generate_rotation(
            squad, match, previous_match_zero_slot_players=benched_in_match1,
        )
        for p in benched_in_match1:
            assert match2_plan.slot_count_for_player(p) >= 1, (
                f"{p.name} sat out match 1 entirely and must not sit out match 2 too "
                f"(12-vs-3-style spread must be impossible)"
            )

    def test_validate_flags_consecutive_sit_out_violation(self):
        squad = Squad(players=[make_player(f"P{i}") for i in range(10)])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        # Simulate a player who sat out entirely last match but got 0 again by
        # constructing a fake "still zero" scenario directly against validate().
        zero_slot_player = squad.available[0]
        # Force the scenario: pretend this player got 0 slots in this plan too.
        for slot in plan.slots:
            for pos in list(slot.lineup):
                if slot.lineup[pos] is zero_slot_player:
                    del slot.lineup[pos]

        violations = validate(
            plan, squad.available, previous_match_zero_slot_players={zero_slot_player},
        )
        assert any("Consecutive sit-out" in v for v in violations)

    def test_no_violation_when_not_previously_benched(self):
        squad = Squad(players=[make_player(f"P{i}") for i in range(10)])
        match = Match(date=date(2026, 3, 23))
        plan = generate_rotation(squad, match)
        violations = validate(plan, squad.available, previous_match_zero_slot_players=None)
        assert not any("Consecutive sit-out" in v for v in violations)
