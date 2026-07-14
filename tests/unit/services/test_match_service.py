"""Unit tests for the pure helpers in match_service (Phase C.5).

These exercise the config-building logic with no DB — the whole point of the
service extraction. DB-coupled functions (generate_and_save_rotation,
reconstruct_plan, adjust_and_save) stay covered by the integration suite.
"""
from __future__ import annotations

from backend.db.models import MatchDB
from backend.services import match_service


class TestSeasonConfig:
    def test_matching_preset_returned_as_is(self):
        # 5v5 1-2-1 default is 4 quarters — exactly the preset.
        cfg = match_service.season_config(5, "1-2-1", quarters=4, quarter_length_mins=10)
        assert cfg.periods == 4
        assert cfg.period_label == "Quarter"
        assert cfg.break_subs == 5

    def test_custom_period_count_builds_halves(self):
        cfg = match_service.season_config(5, "1-2-1", quarters=2, quarter_length_mins=15)
        assert cfg.periods == 2
        assert cfg.period_label == "Half"
        assert cfg.break_subs is None  # no break subs in a 2-half match
        assert cfg.period_length_mins == 15
        # mid_period_subs inherited from the 5v5 preset
        assert cfg.mid_period_subs == 2

    def test_unknown_formation_falls_back_to_defaults(self):
        # No preset for this combo -> custom config with default sub limits.
        cfg = match_service.season_config(5, "9-9-9", quarters=3, quarter_length_mins=10)
        assert cfg.periods == 3
        assert cfg.period_label == "Quarter"
        assert cfg.break_subs == 5
        assert cfg.mid_period_subs == 2


class TestBuildMatchConfig:
    def _match(self, **kw) -> MatchDB:
        base = dict(squad_id=1, date="2026-03-25", team_size=5, formation="1-2-1",
                    quarters=4, quarter_length_mins=10)
        base.update(kw)
        return MatchDB(**base)

    def test_season_match_uses_season_config(self):
        cfg = match_service.build_match_config(self._match(tournament_id=None))
        assert cfg.period_label == "Quarter"
        assert cfg.periods == 4

    def test_tournament_match_single_period(self):
        m = self._match(tournament_id=7, quarters=1, quarter_length_mins=10)
        cfg = match_service.build_match_config(m)
        assert cfg.periods == 1
        assert cfg.period_label == "Period"

    def test_tournament_match_with_halftime(self):
        m = self._match(tournament_id=7, quarters=2, quarter_length_mins=5)
        cfg = match_service.build_match_config(m)
        assert cfg.periods == 2
        assert cfg.period_label == "Half"
