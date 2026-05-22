"""Step definitions for substitution_rules.feature."""
from __future__ import annotations

from datetime import date

import pytest
from pytest_bdd import given, scenarios, then, when

from backend.algorithm.rotation_engine import generate_rotation
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import RotationPlan
from tests.conftest import make_player

pytestmark = pytest.mark.bdd

scenarios("substitution_rules.feature")


@given("a generated rotation plan for 10 players", target_fixture="context")
def squad_10_rotation():
    return {
        "squad": Squad(players=[
            make_player("Specialist", GKTier.SPECIALIST),
            *[make_player(f"Player{i}", GKTier.EMERGENCY_ONLY, skill_rating=3) for i in range(2, 11)],
        ]),
        "match": Match(date=date(2026, 3, 23)),
        "plan": generate_rotation(
            Squad(players=[
                make_player("Specialist", GKTier.SPECIALIST),
                *[make_player(f"Player{i}", GKTier.EMERGENCY_ONLY, skill_rating=3) for i in range(2, 11)],
            ]),
            Match(date=date(2026, 3, 23)),
        ),
    }


@when("comparing any two consecutive half-quarter slots within the same quarter")
def when_compare_mid_quarter(context):
    pass  # assertion happens in Then; context["plan"] is already set


@then("no more than 2 players should differ between the two lineups")
def max_2_changes_mid_quarter(context):
    plan: RotationPlan = context["plan"]
    # Mid-quarter transitions: 0->1, 2->3, 4->5, 6->7
    for q in range(4):
        first = plan.slots[q * 2]
        second = plan.slots[q * 2 + 1]
        first_players = set(first.players)
        second_players = set(second.players)
        changes = len(first_players - second_players)
        assert changes <= 2, (
            f"Q{q+1} mid-quarter: {changes} player changes (max 2). "
            f"Out: {[p.name for p in first_players - second_players]}"
        )


@when("comparing the two half-quarter slots within any single quarter")
def when_compare_gk_mid_quarter(context):
    pass  # assertion happens in Then


@then("the GK must be the same player in both half-quarter slots of that quarter")
def gk_stable_mid_quarter(context):
    plan: RotationPlan = context["plan"]
    for q in range(4):
        first = plan.slots[q * 2]
        second = plan.slots[q * 2 + 1]
        assert first.gk is second.gk, (
            f"Q{q+1}: GK changed mid-quarter from {getattr(first.gk, 'name', None)} "
            f"to {getattr(second.gk, 'name', None)}"
        )
