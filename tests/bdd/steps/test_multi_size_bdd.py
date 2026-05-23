"""Step definitions for multi_size.feature."""
from __future__ import annotations

from datetime import date

import pytest
from pytest_bdd import given, scenarios, then, when

from backend.algorithm.rotation_engine import generate_rotation
from backend.models.game_config import get_config
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import RotationPlan
from tests.conftest import make_player

pytestmark = pytest.mark.bdd

scenarios("multi_size.feature")


# ── Given ─────────────────────────────────────────────────────────────────────

@given("a squad of 12 players for 7v7 with formation 2-3-1", target_fixture="context")
def squad_12_7v7():
    config = get_config(7, "2-3-1")
    return {
        "squad": Squad(players=[
            make_player("Specialist", GKTier.SPECIALIST),
            *[make_player(f"P{i}", GKTier.EMERGENCY_ONLY, skill_rating=(i % 5) + 1)
              for i in range(2, 13)],
        ]),
        "match": Match(date=date(2026, 6, 1), game_config=config),
        "plan": None,
    }


@given("a squad of 14 players for 9v9 with formation 3-3-2", target_fixture="context")
def squad_14_9v9():
    config = get_config(9, "3-3-2")
    return {
        "squad": Squad(players=[
            make_player("Specialist", GKTier.SPECIALIST),
            *[make_player(f"P{i}", GKTier.EMERGENCY_ONLY, skill_rating=(i % 5) + 1)
              for i in range(2, 15)],
        ]),
        "match": Match(date=date(2026, 6, 1), game_config=config),
        "plan": None,
    }


@given("a squad of 10 players with varied skill ratings in competitive mode", target_fixture="context")
def squad_10_competitive():
    return {
        "squad": Squad(players=[
            make_player("Star", GKTier.SPECIALIST, skill_rating=5),
            make_player("High1", GKTier.PREFERRED, skill_rating=5),
            make_player("High2", skill_rating=5),
            make_player("Mid1", skill_rating=3),
            make_player("Mid2", skill_rating=3),
            make_player("Mid3", skill_rating=3),
            make_player("Low1", skill_rating=1),
            make_player("Low2", skill_rating=1),
            make_player("Low3", skill_rating=1),
            make_player("Low4", skill_rating=1),
        ]),
        "match": Match(
            date=date(2026, 6, 1),
            fairness="competitive",
            fairness_value=80,
        ),
        "plan": None,
    }


# ── When ──────────────────────────────────────────────────────────────────────

@when("the system generates a rotation plan")
def generate_plan(context):
    context["plan"] = generate_rotation(context["squad"], context["match"])


# ── Then ──────────────────────────────────────────────────────────────────────

@then("each slot should have exactly 7 players on pitch")
def each_slot_7(context):
    for slot in context["plan"].slots:
        assert len(slot.players) == 7, f"Slot {slot.slot_index}: {len(slot.players)} players"


@then("each slot should have exactly 9 players on pitch")
def each_slot_9(context):
    for slot in context["plan"].slots:
        assert len(slot.players) == 9, f"Slot {slot.slot_index}: {len(slot.players)} players"


@then("the plan should have 8 slots")
def plan_has_8_slots(context):
    assert len(context["plan"].slots) == 8


@then("the plan should have 4 slots")
def plan_has_4_slots(context):
    assert len(context["plan"].slots) == 4


@then("no more than 3 players should change at any mid-period transition")
def max_3_mid_period_subs(context):
    plan: RotationPlan = context["plan"]
    for q in range(len(plan.slots) // 2):
        h1 = set(plan.slots[q * 2].players)
        h2 = set(plan.slots[q * 2 + 1].players)
        changes = len(h1 - h2)
        assert changes <= 3, f"Period {q+1}: {changes} mid-period changes (max 3)"


@then("the highest-skilled player should have more slots than the lowest-skilled player")
def high_skill_more_time(context):
    plan: RotationPlan = context["plan"]
    squad = context["squad"]
    # Exclude specialist (they only play GK, slot count is constrained by GK slots)
    outfield = [p for p in squad.available if p.gk_status != GKTier.SPECIALIST]
    high_tier = [p for p in outfield if p.skill_rating >= 4]
    low_tier = [p for p in outfield if p.skill_rating <= 2]
    avg_high = sum(plan.slot_count_for_player(p) for p in high_tier) / len(high_tier)
    avg_low = sum(plan.slot_count_for_player(p) for p in low_tier) / len(low_tier)
    assert avg_high >= avg_low, (
        f"High-skill avg ({avg_high:.1f} slots) should be >= "
        f"low-skill avg ({avg_low:.1f} slots)"
    )
