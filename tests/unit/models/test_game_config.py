"""Tests for Formation, GameConfig, and preset configurations."""
import pytest

from backend.models.game_config import (
    DEFAULT_CONFIG,
    DEFAULT_FORMATIONS,
    PRESET_CONFIGS,
    Formation,
    build_tournament_config,
    get_config,
)


class TestFormation:
    def test_parse_1_2_1(self):
        f = Formation.parse("1-2-1")
        assert f.defense == 1
        assert f.midfield == 2
        assert f.forward == 1

    def test_parse_4_4_2(self):
        f = Formation.parse("4-4-2")
        assert f.defense == 4
        assert f.midfield == 4
        assert f.forward == 2

    def test_outfield_count(self):
        assert Formation.parse("1-2-1").outfield_count == 4
        assert Formation.parse("2-3-1").outfield_count == 6
        assert Formation.parse("3-3-2").outfield_count == 8
        assert Formation.parse("4-4-2").outfield_count == 10

    def test_team_size(self):
        assert Formation.parse("1-2-1").team_size == 5
        assert Formation.parse("2-3-1").team_size == 7
        assert Formation.parse("3-3-2").team_size == 9
        assert Formation.parse("4-4-2").team_size == 11

    def test_outfield_positions_5v5_default(self):
        f = Formation.parse("1-2-1")
        assert f.outfield_positions() == ["CB", "LM", "RM", "CF"]

    def test_outfield_positions_7v7(self):
        f = Formation.parse("2-3-1")
        assert f.outfield_positions() == ["CB", "CB2", "LM", "CM", "RM", "CF"]

    def test_outfield_positions_9v9(self):
        f = Formation.parse("3-3-2")
        assert f.outfield_positions() == ["LB", "CB", "RB", "LM", "CM", "RM", "CF", "CF2"]

    def test_outfield_positions_4_4_2(self):
        f = Formation.parse("4-4-2")
        assert f.outfield_positions() == ["LB", "CB", "CB2", "RB", "LM", "CM", "CM2", "RM", "CF", "CF2"]

    def test_notation_roundtrip(self):
        assert Formation.parse("2-3-1").notation == "2-3-1"

    def test_invalid_notation(self):
        with pytest.raises(ValueError):
            Formation.parse("4-4")

    def test_str(self):
        assert str(Formation.parse("1-2-1")) == "1-2-1"


class TestGameConfig:
    def test_default_config_is_5v5(self):
        assert DEFAULT_CONFIG.team_size == 5
        assert DEFAULT_CONFIG.formation.notation == "1-2-1"
        assert DEFAULT_CONFIG.periods == 4
        assert DEFAULT_CONFIG.total_slots == 8
        assert DEFAULT_CONFIG.players_per_slot == 5
        assert DEFAULT_CONFIG.period_label == "Quarter"
        assert DEFAULT_CONFIG.mid_period_subs == 2
        assert DEFAULT_CONFIG.break_subs == 5

    def test_all_positions_5v5(self):
        assert DEFAULT_CONFIG.all_positions() == ["GK", "CB", "LM", "RM", "CF"]

    def test_9v9_config(self):
        cfg = get_config(9, "3-3-2")
        assert cfg.team_size == 9
        assert cfg.total_slots == 4
        assert cfg.periods == 2
        assert cfg.period_label == "Half"
        assert cfg.mid_period_subs == 4
        assert cfg.break_subs is None
        assert cfg.players_per_slot == 9

    def test_7v7_config(self):
        cfg = get_config(7, "2-3-1")
        assert cfg.total_slots == 8
        assert cfg.mid_period_subs == 3
        assert cfg.break_subs == 4


class TestBuildTournamentConfig:
    def test_no_halftime_single_period(self):
        cfg = build_tournament_config(5, "1-2-1", 20, has_halftime=False)
        assert cfg.periods == 1
        assert cfg.total_slots == 2
        assert cfg.break_subs is None

    def test_halftime_two_periods(self):
        cfg = build_tournament_config(5, "1-2-1", 20, has_halftime=True)
        assert cfg.periods == 2
        assert cfg.total_slots == 4

    def test_sub_cap_defaults_to_preset_when_unset(self):
        # 5v5 preset mid-period cap is 2; 7v7 is 3.
        assert build_tournament_config(5, "1-2-1", 20, False).mid_period_subs == 2
        assert build_tournament_config(7, "2-3-1", 25, False).mid_period_subs == 3

    def test_max_subs_overrides_preset(self):
        cfg = build_tournament_config(5, "1-2-1", 20, False, max_subs=4)
        assert cfg.mid_period_subs == 4

    def test_max_subs_can_lower_the_cap(self):
        cfg = build_tournament_config(7, "2-3-1", 25, False, max_subs=1)
        assert cfg.mid_period_subs == 1

    def test_max_subs_none_keeps_preset(self):
        cfg = build_tournament_config(9, "3-3-2", 30, True, max_subs=None)
        assert cfg.mid_period_subs == 4


class TestPresets:
    def test_all_team_sizes_have_presets(self):
        assert set(PRESET_CONFIGS.keys()) == {5, 6, 7, 9}

    def test_all_team_sizes_have_defaults(self):
        assert set(DEFAULT_FORMATIONS.keys()) == {5, 6, 7, 9}

    @pytest.mark.parametrize("team_size,formation", [
        (5, "1-2-1"), (5, "2-1-1"),
        (6, "1-3-1"), (6, "2-2-1"), (6, "1-2-2"),
        (7, "2-3-1"), (7, "1-3-2"), (7, "2-2-2"),
        (9, "3-3-2"), (9, "2-4-2"), (9, "3-2-3"),
    ])
    def test_formation_team_size_matches(self, team_size, formation):
        cfg = get_config(team_size, formation)
        assert cfg.formation.team_size == team_size

    def test_invalid_team_size(self):
        with pytest.raises(KeyError):
            get_config(8, "1-2-1")

    def test_invalid_formation_for_size(self):
        with pytest.raises(KeyError):
            get_config(5, "4-4-2")
