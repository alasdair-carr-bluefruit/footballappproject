"""Granular positions (squad toggle): picks are read as LB/CB/RB… when on, by band
when off — the stored picks never change, so the toggle is reversible."""
from dataclasses import replace
from datetime import date

import pytest

from backend.algorithm.rotation_engine import _max_pos_types, generate_rotation
from backend.models.game_config import get_config
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import (
    Position,
    move_keeps_picks,
    picks_allow,
    picks_label,
    position_mode,
    position_type,
)
from tests.conftest import make_player

pytestmark = pytest.mark.unit


def test_band_mode_reads_detailed_picks_as_their_line():
    with position_mode(False):
        assert picks_allow(["LW"], "RW")          # LW pick = any attacker
        assert picks_allow(["LW"], "CF2")
        assert not picks_allow(["LW"], "CB")
        assert position_type("LB") == position_type("RB") == "DEF"
        assert picks_label(["LB", "RB", "LW"]) == ["DEF", "FWD"]


def test_granular_mode_reads_picks_exactly():
    with position_mode(True):
        assert picks_allow(["LW"], "LW")
        assert not picks_allow(["LW"], "RW")      # LW and RW are two positions
        assert not picks_allow(["LB"], "RB")
        assert picks_allow(["CB"], "CB2")         # a second centre-back is still a CB
        assert picks_allow(["FWD"], "RW")         # a band pick covers its whole line
        assert picks_allow([], "RB")              # no picks = anywhere
        assert position_type("LB") != position_type("RB")
        assert position_type("CM2") == "CM"
        assert picks_label(["LB", "RB"]) == ["LB", "RB"]


def test_mode_is_scoped_to_the_block():
    with position_mode(True):
        assert position_type("LB") == "LB"
    assert position_type("LB") == "DEF"


def test_variety_counts_granular_positions_when_on():
    cfg = get_config(9, "3-3-2")  # LB CB RB / LM CM RM / CF CF2
    with position_mode(False):
        assert _max_pos_types(cfg, 100) == 3
    with position_mode(True):
        assert _max_pos_types(cfg, 100) == 7


def test_late_swaps_never_move_a_player_out_of_a_pick():
    lefty = replace(make_player("Lefty"), preferred_positions=["LB"])
    with position_mode(True):
        assert not move_keeps_picks(lefty, "LB", "RB")
        assert move_keeps_picks(lefty, "CM", "LB")
        assert move_keeps_picks(lefty, "CM", "RM")  # already out of position: no worse
    with position_mode(False):
        assert move_keeps_picks(lefty, "LB", "RB")  # same line when off


def _nine_v_nine(granular: bool) -> tuple[Squad, Match, dict]:
    players = [make_player("Keeper", GKTier.SPECIALIST)]
    picks = {"Lefty": ["LB"], "Righty": ["RB"], "LeftMid": ["LM"]}
    for name, p in picks.items():
        players.append(replace(make_player(name, GKTier.EMERGENCY_ONLY), preferred_positions=p))
    for i in range(8):
        players.append(make_player(f"P{i}", GKTier.EMERGENCY_ONLY, skill_rating=(i % 5) + 1))
    match = Match(date=date(2026, 11, 28), game_config=get_config(9, "3-3-2"),
                  granular_positions=granular, share_gk=False)
    return Squad(players=players), match, picks


def _spots(plan, name):
    return {str(pos) for s in plan.slots for pos, p in s.lineup.items() if p.name == name and pos != Position.GK}


def test_engine_keeps_granular_picks_when_on():
    squad, match, picks = _nine_v_nine(granular=True)
    plan = generate_rotation(squad, match)
    for name, p in picks.items():
        played = _spots(plan, name)
        assert played, f"{name} never played"
        assert played <= set(p), f"{name} played {played}, picked {p}"
    assert not [w for w in plan.warnings if w.startswith("Out of position")]


def test_engine_reads_same_picks_by_line_when_off():
    squad, match, _ = _nine_v_nine(granular=False)
    plan = generate_rotation(squad, match)
    assert _spots(plan, "Lefty") <= {"LB", "CB", "RB"}
    assert _spots(plan, "LeftMid") <= {"LM", "CM", "RM"}
    assert all(Position(p) for p in _spots(plan, "Lefty"))


def test_narrow_picker_not_stranded_out_of_position_when_off():
    """Greedy assignment used to fill the back line with play-anywhere kids and
    leave the DEF-only kid at RM; the same-slot repair swaps them back."""
    squad, match, _ = _nine_v_nine(granular=False)
    plan = generate_rotation(squad, match)
    assert not [w for w in plan.warnings if w.startswith("Out of position")]
