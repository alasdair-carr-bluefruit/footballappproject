"""Step definitions for gk_priority.feature."""
from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, when, then
from datetime import date

from backend.models.player import GKTier
from backend.models.match import Match, Squad
from backend.models.rotation import Position, RotationPlan
from backend.algorithm.rotation_engine import generate_rotation
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


@then("no emergency_only player should fill a GK slot")
def no_emergency_in_gk(context):
    plan: RotationPlan = context["plan"]
    preferred = next((p for p in context["squad"].available if p.gk_status == GKTier.PREFERRED), None)
    can_play = [p for p in context["squad"].available if p.gk_status == GKTier.CAN_PLAY]
    # Emergency only forbidden when preferred or can_play exist
    if preferred or can_play:
        for slot in plan.slots:
            if slot.gk is not None:
                assert slot.gk.gk_status != GKTier.EMERGENCY_ONLY, (
                    f"Slot {slot.slot_index}: emergency_only {slot.gk.name} assigned GK "
                    "when preferred/can_play was available"
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
