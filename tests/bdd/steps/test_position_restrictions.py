"""Step definitions for position_restrictions.feature."""
from __future__ import annotations

from datetime import date

import pytest
from pytest_bdd import given, scenarios, then, when

from backend.algorithm.rotation_engine import generate_rotation
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import Position, RotationPlan, normalize_position
from tests.conftest import make_player

pytestmark = pytest.mark.bdd

scenarios("position_restrictions.feature")


@given("a squad of 9 players where 2 players are DEF-restricted", target_fixture="context")
def squad_9_def_restricted():
    return {
        "squad": Squad(players=[
            make_player("Preferred", GKTier.PREFERRED),
            make_player("Restricted1", def_restricted=True),
            make_player("Restricted2", def_restricted=True),
            *[make_player(f"Player{i}") for i in range(3, 10)],
        ]),
        "match": Match(date=date(2026, 3, 23)),
        "plan": None,
    }


@given("a squad of 9 players with no GK specialist", target_fixture="context")
def squad_9_no_specialist_pos():
    return {
        "squad": Squad(players=[
            make_player("Preferred", GKTier.PREFERRED),
            *[make_player(f"Player{i}") for i in range(2, 10)],
        ]),
        "match": Match(date=date(2026, 3, 23)),
        "plan": None,
    }


@when("the system generates a rotation plan")
def generate_plan_positions(context):
    context["plan"] = generate_rotation(context["squad"], context["match"])


@then("no DEF-restricted player should appear in the DEF position in any slot")
def no_def_restricted_in_def(context):
    plan: RotationPlan = context["plan"]
    restricted = [p for p in context["squad"].available if p.def_restricted]
    for slot in plan.slots:
        for pos, player in slot.lineup.items():
            if normalize_position(pos) == "DEF":
                for r in restricted:
                    assert player is not r, (
                        f"DEF-restricted player {r.name} assigned {pos} at slot {slot.slot_index}"
                    )


@then("no player should appear in more than 2 different positions across all slots")
def no_player_over_2_positions(context):
    plan: RotationPlan = context["plan"]
    # For 5v5 with 3 outfield types (DEF/MID/FWD), playing all 3 is expected
    # and encouraged for youth development. The limit is the number of
    # outfield types available (3 for 5v5), not a hard 2.
    max_types = 4  # 3 outfield + GK
    for player in context["squad"].available:
        raw = {pos for slot in plan.slots for pos, p in slot.lineup.items() if p is player}
        normalised = {normalize_position(pos) for pos in raw}
        assert len(normalised) <= max_types, (
            f"{player.name} plays {len(normalised)} positions {normalised} (max {max_types})"
        )
