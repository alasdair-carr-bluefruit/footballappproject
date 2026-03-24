"""Step definitions for team_balance.feature."""
from __future__ import annotations

from datetime import date

import pytest
from pytest_bdd import given, scenarios, then, when

from backend.algorithm.rotation_engine import generate_rotation
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import RotationPlan, Position
from tests.conftest import make_player


scenarios("team_balance.feature")


@given("players with varying skill ratings", target_fixture="context")
def players_with_varying_skills():
    players = [
        make_player("Specialist", GKTier.SPECIALIST, skill_rating=3),
        make_player("High1", GKTier.PREFERRED, skill_rating=5),
        make_player("High2", skill_rating=5),
        make_player("High3", skill_rating=4),
        make_player("Mid1", skill_rating=3),
        make_player("Mid2", skill_rating=3),
        make_player("Low1", skill_rating=1),
        make_player("Low2", skill_rating=1),
        make_player("Low3", skill_rating=2),
        make_player("Low4", skill_rating=2),
    ]
    return {
        "squad": Squad(players=players),
        "match": Match(date=date(2026, 3, 24)),
        "plan": None,
    }


@when("the system generates a rotation plan")
def generate_plan(context):
    context["plan"] = generate_rotation(context["squad"], context["match"])


@then("the total outfield skill rating variance across slots should be minimal")
def skill_variance_is_minimal(context):
    plan: RotationPlan = context["plan"]
    totals = [s.outfield_skill_total for s in plan.slots]
    mean = sum(totals) / len(totals)
    variance = sum((t - mean) ** 2 for t in totals) / len(totals)

    # Max allowed variance: 2.0 (equivalent to roughly ±1.4 skill points per slot)
    # This is a soft goal — the balancer should get close but perfect is rare
    assert variance <= 2.0, (
        f"Skill variance too high: {variance:.2f}. Slot totals: {totals}"
    )


@then("the GK slot skill rating is excluded from this calculation")
def gk_excluded_from_skill(context):
    plan: RotationPlan = context["plan"]
    for slot in plan.slots:
        # outfield_skill_total must not include the GK's rating
        gk = slot.gk
        if gk is None:
            continue
        outfield_total = slot.outfield_skill_total
        full_total = sum(p.skill_rating for p in slot.players)
        assert outfield_total == full_total - gk.skill_rating, (
            f"Slot {slot.slot_index}: outfield skill total includes GK rating"
        )
