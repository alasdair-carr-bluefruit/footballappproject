"""Tests for competitive fairness mode."""
import pytest

from backend.algorithm.time_balancer import compute_target_slots
from backend.models.player import GKTier
from tests.conftest import make_player


@pytest.mark.unit
class TestEqualMode:
    def test_equal_distribution_10_players(self):
        players = [make_player(f"P{i}", skill_rating=i % 5 + 1) for i in range(10)]
        targets = compute_target_slots(players, 40, [], fairness="equal")
        assert all(t == 4 for t in targets.values())

    def test_equal_with_remainder(self):
        players = [make_player(f"P{i}") for i in range(9)]
        targets = compute_target_slots(players, 40, [], fairness="equal")
        values = sorted(targets.values())
        assert values[0] >= 4
        assert values[-1] <= 5


@pytest.mark.unit
class TestCompetitiveMode:
    def test_high_skill_gets_more_slots(self):
        players = [
            make_player("Star", skill_rating=5),
            make_player("Good", skill_rating=4),
            make_player("Avg1", skill_rating=3),
            make_player("Avg2", skill_rating=3),
            make_player("Dev1", skill_rating=2),
            make_player("Dev2", skill_rating=1),
            make_player("Dev3", skill_rating=1),
            make_player("Dev4", skill_rating=2),
            make_player("Dev5", skill_rating=1),
            make_player("Dev6", skill_rating=2),
        ]
        targets = compute_target_slots(
            players, 40, [], fairness="competitive", fairness_value=80,
        )
        star = next(p for p in players if p.name == "Star")
        dev = next(p for p in players if p.name == "Dev3")
        assert targets[star] > targets[dev], (
            f"Star ({targets[star]}) should get more slots than Dev3 ({targets[dev]})"
        )

    def test_everyone_gets_minimum(self):
        players = [
            make_player("Star", skill_rating=5),
            *[make_player(f"Dev{i}", skill_rating=1) for i in range(9)],
        ]
        targets = compute_target_slots(
            players, 40, [], fairness="competitive", fairness_value=100,
        )
        min_target = min(targets.values())
        assert min_target >= 3, f"Minimum slots {min_target} is too low (expected >= 3)"

    def test_total_slots_preserved(self):
        players = [make_player(f"P{i}", skill_rating=i % 5 + 1) for i in range(10)]
        targets = compute_target_slots(
            players, 40, [], fairness="competitive", fairness_value=70,
        )
        assert sum(targets.values()) == 40

    def test_mild_competitive_small_difference(self):
        players = [
            make_player("High", skill_rating=5),
            make_player("Low", skill_rating=1),
            *[make_player(f"Mid{i}", skill_rating=3) for i in range(8)],
        ]
        targets = compute_target_slots(
            players, 40, [], fairness="competitive", fairness_value=25,
        )
        high = next(p for p in players if p.name == "High")
        low = next(p for p in players if p.name == "Low")
        diff = targets[high] - targets[low]
        assert diff <= 2, f"Mild competitive should have small diff, got {diff}"

    def test_aggressive_competitive_larger_difference(self):
        players = [
            make_player("Star", skill_rating=5),
            make_player("Bench", skill_rating=1),
            *[make_player(f"Mid{i}", skill_rating=3) for i in range(8)],
        ]
        targets = compute_target_slots(
            players, 40, [], fairness="competitive", fairness_value=90,
        )
        star = next(p for p in players if p.name == "Star")
        bench = next(p for p in players if p.name == "Bench")
        assert targets[star] > targets[bench]


@pytest.mark.unit
class TestConsecutiveSitOutFloor:
    """must_play: players who sat out the entire previous tournament match
    must be guaranteed at least 1 slot this match, in both fairness modes."""

    def test_equal_mode_must_play_gets_at_least_one_slot(self):
        # 12 players, 8 slots: base=0, only 8 of 12 get a slot via the remainder.
        players = [make_player(f"P{i}") for i in range(12)]
        bench_last_time = players[0]
        targets = compute_target_slots(
            players, 8, [], fairness="equal", must_play={bench_last_time},
        )
        assert targets[bench_last_time] >= 1
        assert sum(targets.values()) == 8

    def test_equal_mode_multiple_must_play_all_satisfied(self):
        players = [make_player(f"P{i}") for i in range(12)]
        must_play = {players[0], players[1], players[2], players[3]}
        targets = compute_target_slots(
            players, 8, [], fairness="equal", must_play=must_play,
        )
        for p in must_play:
            assert targets[p] >= 1
        assert sum(targets.values()) == 8

    def test_equal_mode_must_play_preserves_total_when_all_at_floor(self):
        # Every player already at target 1 (8 players, 8 slots) — no spare capacity,
        # but the must_play player is already satisfied so nothing to steal.
        players = [make_player(f"P{i}") for i in range(8)]
        targets = compute_target_slots(
            players, 8, [], fairness="equal", must_play={players[0]},
        )
        assert sum(targets.values()) == 8
        assert targets[players[0]] >= 1

    def test_competitive_mode_must_play_gets_at_least_one_slot(self):
        players = [
            make_player("Star", skill_rating=5),
            *[make_player(f"Dev{i}", skill_rating=1) for i in range(9)],
        ]
        bench_last_time = players[-1]
        targets = compute_target_slots(
            players, 40, [], fairness="competitive", fairness_value=90,
            must_play={bench_last_time},
        )
        assert targets[bench_last_time] >= 1
        assert sum(targets.values()) == 40

    def test_no_must_play_unaffected(self):
        players = [make_player(f"P{i}") for i in range(9)]
        targets = compute_target_slots(players, 40, [], fairness="equal", must_play=None)
        values = sorted(targets.values())
        assert values[0] >= 4
        assert values[-1] <= 5
