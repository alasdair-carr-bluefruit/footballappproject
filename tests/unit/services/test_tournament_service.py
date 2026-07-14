"""Unit tests for the pure helpers in tournament_service (Phase C.5)."""
from __future__ import annotations

import json

from backend.db.models import PlayerDB, TournamentDB
from backend.services import tournament_service


def _tournament(**kw) -> TournamentDB:
    base = dict(squad_id=1, date="2026-04-12", team_size=5, formation="1-2-1",
                match_duration_mins=20, has_halftime=0, fairness_value=50)
    base.update(kw)
    return TournamentDB(**base)


class TestDerivePeriodStructure:
    def test_no_halftime_is_single_period(self):
        assert tournament_service.derive_period_structure(_tournament(match_duration_mins=12)) == (1, 12)

    def test_halftime_splits_in_two(self):
        assert tournament_service.derive_period_structure(
            _tournament(has_halftime=1, match_duration_mins=20)
        ) == (2, 10)

    def test_halftime_odd_duration_floors_to_min_one(self):
        # 1 minute total, halved -> max(1, 0) == 1
        assert tournament_service.derive_period_structure(
            _tournament(has_halftime=1, match_duration_mins=1)
        ) == (2, 1)


class TestResolveFairness:
    def test_group_uses_tournament_default(self):
        assert tournament_service.resolve_fairness(_tournament(fairness_value=60), "group", None) == (60, "competitive")

    def test_group_ignores_knockout_override(self):
        assert tournament_service.resolve_fairness(_tournament(fairness_value=10), "group", 90) == (10, "equal")

    def test_knockout_override_applied(self):
        assert tournament_service.resolve_fairness(_tournament(fairness_value=10), "knockout", 80) == (80, "competitive")

    def test_knockout_without_override_uses_default(self):
        assert tournament_service.resolve_fairness(_tournament(fairness_value=50), "knockout", None) == (50, "competitive")

    def test_fairness_boundary_at_15(self):
        # > 15 is competitive; 15 itself is equal
        assert tournament_service.resolve_fairness(_tournament(fairness_value=15), "group", None) == (15, "equal")
        assert tournament_service.resolve_fairness(_tournament(fairness_value=16), "group", None) == (16, "competitive")


class TestApplyPositionOverrides:
    def _player(self, pid: int) -> PlayerDB:
        return PlayerDB(id=pid, squad_id=1, name=f"P{pid}", gk_status="can_play",
                        preferred_positions=json.dumps(["MID"]))

    def test_gk_only_becomes_specialist(self):
        [out] = tournament_service.apply_position_overrides([self._player(1)], {"1": ["GK"]})
        assert out.gk_status == "specialist"
        assert out.def_restricted is True  # GK-only excludes DEF
        assert json.loads(out.preferred_positions) == ["GK"]

    def test_gk_plus_others_becomes_can_play(self):
        [out] = tournament_service.apply_position_overrides([self._player(1)], {"1": ["GK", "DEF"]})
        assert out.gk_status == "can_play"
        assert out.def_restricted is False  # DEF is allowed

    def test_no_gk_becomes_emergency_and_def_restricted_derived(self):
        [out] = tournament_service.apply_position_overrides([self._player(1)], {"1": ["MID", "FWD"]})
        assert out.gk_status == "emergency_only"
        assert out.def_restricted is True  # no DEF in the selection

    def test_untouched_player_returned_unchanged(self):
        p = self._player(2)
        [out] = tournament_service.apply_position_overrides([p], {"1": ["GK"]})
        assert out is p  # no override for id 2 -> same object

    def test_does_not_mutate_original(self):
        p = self._player(1)
        tournament_service.apply_position_overrides([p], {"1": ["GK"]})
        assert p.gk_status == "can_play"  # original untouched
        assert json.loads(p.preferred_positions) == ["MID"]

    def test_empty_override_list_leaves_player_unchanged(self):
        p = self._player(1)
        [out] = tournament_service.apply_position_overrides([p], {"1": []})
        assert out is p  # falsy override -> skipped
