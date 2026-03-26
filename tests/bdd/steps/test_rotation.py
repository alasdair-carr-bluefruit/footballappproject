"""Step definitions for rotation_generation.feature."""
from __future__ import annotations

from datetime import date

from pytest_bdd import given, scenarios, then, when

from backend.algorithm.rotation_engine import generate_rotation
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import Position, RotationPlan
from tests.conftest import make_player

# Link all scenarios in the feature file
scenarios("rotation_generation.feature")


# ── Given ─────────────────────────────────────────────────────────────────────

@given("a squad of 10 available players with a GK specialist", target_fixture="context")
def squad_10_specialist():
    return {
        "squad": Squad(players=[
            make_player("Specialist", GKTier.SPECIALIST),
            *[make_player(f"Player{i}", GKTier.EMERGENCY_ONLY, skill_rating=3) for i in range(2, 11)],
        ]),
        "match": Match(date=date(2026, 3, 23)),
        "plan": None,
    }


@given("a squad of 9 players including 1 GK specialist", target_fixture="context")
def squad_9_specialist():
    return {
        "squad": Squad(players=[
            make_player("Specialist", GKTier.SPECIALIST),
            *[make_player(f"Player{i}", GKTier.EMERGENCY_ONLY, skill_rating=3) for i in range(2, 10)],
        ]),
        "match": Match(date=date(2026, 3, 23)),
        "plan": None,
    }


@given("a squad of 9 players with no GK specialist", target_fixture="context")
def squad_9_no_specialist():
    return {
        "squad": Squad(players=[
            make_player("Preferred", GKTier.PREFERRED, skill_rating=3),
            *[make_player(f"Player{i}", GKTier.EMERGENCY_ONLY, skill_rating=3) for i in range(2, 10)],
        ]),
        "match": Match(date=date(2026, 3, 23)),
        "plan": None,
    }


# ── When ──────────────────────────────────────────────────────────────────────

@when("the system generates a rotation plan for 4 quarters")
def generate_plan(context):
    context["plan"] = generate_rotation(context["squad"], context["match"])


# ── Then ──────────────────────────────────────────────────────────────────────

@then("each player should appear in exactly 4 half-quarter slots")
def each_player_4_slots(context):
    plan: RotationPlan = context["plan"]
    for player in context["squad"].available:
        count = plan.slot_count_for_player(player)
        assert count == 4, f"{player.name} has {count} slots, expected 4"


@then("the GK specialist's 4 slots must all be in the GK position")
def specialist_gk_slots_only(context):
    plan: RotationPlan = context["plan"]
    specialist = next(p for p in context["squad"].available if p.gk_status == GKTier.SPECIALIST)
    for slot in plan.slots:
        for pos, player in slot.lineup.items():
            if player is specialist:
                assert pos == Position.GK, (
                    f"Specialist {specialist.name} found in {pos} at slot {slot.slot_index}"
                )


@then("the specialist should appear in all 8 GK slots")
def specialist_in_all_gk_slots(context):
    plan: RotationPlan = context["plan"]
    specialist = next(p for p in context["squad"].available if p.gk_status == GKTier.SPECIALIST)
    for slot in plan.slots:
        assert slot.gk is specialist, (
            f"Slot {slot.slot_index}: expected specialist GK, got {getattr(slot.gk, 'name', None)}"
        )


@then("each of the other 8 players should appear in exactly 4 slots")
def other_players_4_slots(context):
    plan: RotationPlan = context["plan"]
    players = [p for p in context["squad"].available if p.gk_status != GKTier.SPECIALIST]
    for player in players:
        count = plan.slot_count_for_player(player)
        assert count == 4, f"{player.name} has {count} slots, expected 4"


@then("no player should appear in more than 5 half-quarter slots")
def no_player_over_5_slots(context):
    plan: RotationPlan = context["plan"]
    for player in context["squad"].available:
        count = plan.slot_count_for_player(player)
        assert count <= 5, f"{player.name} has {count} slots, max is 5"


@then("no player should appear in fewer than 4 half-quarter slots")
def no_player_under_4_slots(context):
    plan: RotationPlan = context["plan"]
    for player in context["squad"].available:
        count = plan.slot_count_for_player(player)
        assert count >= 4, f"{player.name} has {count} slots, min is 4"
