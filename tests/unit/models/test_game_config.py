"""Tests for Formation, GameConfig, and preset configurations."""
import pytest

from backend.models.game_config import (
    DEFAULT_CONFIG,
    DEFAULT_FORMATIONS,
    PRESET_CONFIGS,
    Formation,
    GameConfig,
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
        """The default 1-2-1 must produce DEF, MID1, MID2, FWD for backward compat."""
        f = Formation.parse("1-2-1")
        assert f.outfield_positions() == ["DEF", "MID1", "MID2", "FWD"]

    def test_outfield_positions_7v7(self):
        f = Formation.parse("2-3-1")
        assert f.outfield_positions() == ["DEF", "DEF2", "MID1", "MID2", "MID3", "FWD"]

    def test_outfield_positions_9v9(self):
        f = Formation.parse("3-3-2")
        assert f.outfield_positions() == [
            "DEF", "DEF2", "DEF3", "MID1", "MID2", "MID3", "FWD", "FWD2",
        ]

    def test_outfield_positions_11v11(self):
        f = Formation.parse("4-4-2")
        assert f.outfield_positions() == [
            "DEF", "DEF2", "DEF3", "DEF4", "MID1", "MID2", "MID3", "MID4", "FWD", "FWD2",
        ]

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
        assert DEFAULT_CONFIG.all_positions() == ["GK", "DEF", "MID1", "MID2", "FWD"]

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
