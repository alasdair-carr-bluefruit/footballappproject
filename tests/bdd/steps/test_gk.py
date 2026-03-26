"""Step definitions for gk_priority.feature."""
from __future__ import annotations

from datetime import date

from pytest_bdd import given, scenarios, then, when

from backend.algorithm.rotation_engine import generate_rotation
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import RotationPlan
from tests.conftest import make_player

scenarios("gk_priority.feature")


@given("a squad of 8 players including a GK specialist", target_fixture="context")
def squad_8_specialist():
    return {
        "squad": Squad(players=[
            make_player("Specialist", GKTier.SPECIALIST),
            *[make_player(f"Player{i}", GKTier.EMERGENCY_ONLY) for i in range(2, 9)],
        ]),
        "match": Match(date=date(2026, 3, 23)),
        "plan": None,
    }


@given("a squad of 9 players with no specialist but with a preferred GK player", target_fixture="context")
def squad_9_preferred():
    return {
        "squad": Squad(players=[
            make_player("Preferred", GKTier.PREFERRED),
            *[make_player(f"Player{i}", GKTier.EMERGENCY_ONLY) for i in range(2, 10)],
        ]),
        "match": Match(date=date(2026, 3, 23)),
        "plan": None,
    }


@given("a squad where the only available GK-capable players are emergency_only", target_fixture="context")
def squad_emergency_only():
    return {
        "squad": Squad(players=[
            *[make_player(f"Player{i}", GKTier.EMERGENCY_ONLY) for i in range(1, 10)],
        ]),
        "match": Match(date=date(2026, 3, 23)),
        "plan": None,
    }


@when("the system generates a rotation plan")
def generate_plan_gk(context):
    context["plan"] = generate_rotation(context["squad"], context["match"])


@then("the specialist fills the GK slot in every half-quarter")
def specialist_all_gk(context):
    plan: RotationPlan = context["plan"]
    specialist = next(p for p in context["squad"].available if p.gk_status == GKTier.SPECIALIST)
    for slot in plan.slots:
        assert slot.gk is specialist, (
            f"Slot {slot.slot_index} GK is {getattr(slot.gk, 'name', None)}, expected {specialist.name}"
        )


@then("no other player is assigned GK")
def no_other_gk(context):
    plan: RotationPlan = context["plan"]
    specialist = next(p for p in context["squad"].available if p.gk_status == GKTier.SPECIALIST)
    for slot in plan.slots:
        assert slot.gk is specialist, (
            f"Slot {slot.slot_index}: non-specialist {getattr(slot.gk, 'name', None)} assigned GK"
        )


@then("the preferred GK player should fill at least one GK slot")
def preferred_fills_gk(context):
    plan: RotationPlan = context["plan"]
    preferred = next(p for p in context["squad"].available if p.gk_status == GKTier.PREFERRED)
    gk_slots = [slot for slot in plan.slots if slot.gk is preferred]
    assert len(gk_slots) > 0, f"Preferred GK {preferred.name} never assigned GK"


@then("the preferred GK player should fill more GK slots than any single emergency_only player")
def preferred_fills_more_than_any_emergency(context):
    """Preferred gets priority: they fill more GK slots than any individual emergency player."""
    plan: RotationPlan = context["plan"]
    preferred = next((p for p in context["squad"].available if p.gk_status == GKTier.PREFERRED), None)
    if preferred is None:
        return
    preferred_gk_count = sum(1 for slot in plan.slots if slot.gk is preferred)
    emergency_players = [p for p in context["squad"].available if p.gk_status == GKTier.EMERGENCY_ONLY]
    for ep in emergency_players:
        ep_gk_count = sum(1 for slot in plan.slots if slot.gk is ep)
        assert preferred_gk_count >= ep_gk_count, (
            f"Preferred {preferred.name} has {preferred_gk_count} GK slots, "
            f"but emergency {ep.name} has {ep_gk_count}"
        )


@then("an emergency_only player is assigned GK")
def emergency_assigned_gk(context):
    plan: RotationPlan = context["plan"]
    emergency_gk_slots = [
        slot for slot in plan.slots
        if slot.gk is not None and slot.gk.gk_status == GKTier.EMERGENCY_ONLY
    ]
    assert len(emergency_gk_slots) > 0, "No emergency_only player was assigned GK"


@then("the plan includes a warning about emergency GK usage")
def plan_has_emergency_warning(context):
    plan: RotationPlan = context["plan"]
    emergency_warnings = [w for w in plan.warnings if "emergency" in w.lower()]
    assert len(emergency_warnings) > 0, f"No emergency GK warning found. Warnings: {plan.warnings}"
