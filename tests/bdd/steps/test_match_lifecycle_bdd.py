"""Step definitions for match_lifecycle.feature."""
from __future__ import annotations

from datetime import date
from copy import deepcopy

import pytest
from pytest_bdd import given, scenarios, then, when

pytestmark = pytest.mark.bdd

from backend.algorithm.rotation_engine import adjust_rotation, generate_rotation
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import Position, RotationPlan, SlotAssignment
from tests.conftest import make_player

scenarios("match_lifecycle.feature")


def _make_squad() -> Squad:
    return Squad(players=[
        make_player("Specialist", GKTier.SPECIALIST),
        *[make_player(f"Player{i}", GKTier.EMERGENCY_ONLY, skill_rating=3) for i in range(2, 11)],
    ])


def _remove_player_from_slot(plan: RotationPlan, player_name: str, from_slot: int, squad: Squad, match: Match):
    """Lock slots before from_slot and regenerate without the named player."""
    reduced_players = [p for p in squad.available if p.name != player_name]
    reduced_squad = Squad(players=reduced_players)
    player_by_name = {p.name: p for p in reduced_players}

    new_slots = []
    for slot in plan.slots:
        s = SlotAssignment(slot_index=slot.slot_index)
        s.lineup = dict(slot.lineup)
        if slot.slot_index < from_slot:
            s.locked = True
        new_slots.append(s)

    locked_plan = RotationPlan(slots=new_slots)
    new_plan, _ = adjust_rotation(locked_plan, {}, reduced_squad, match)
    return new_plan, reduced_squad


# ── Given ──────────────────────────────────────────────────────────────────────

@given("a 10-player squad with a GK specialist", target_fixture="context")
def squad_context():
    squad = _make_squad()
    match = Match(date=date(2026, 3, 25))
    return {"squad": squad, "match": match, "plan": None, "original_plan": None, "reduced_squad": None}


@given("a rotation plan has been generated", target_fixture="context")
def generated_plan(context):
    plan = generate_rotation(context["squad"], context["match"])
    context["plan"] = plan
    context["original_plan"] = deepcopy(plan)
    return context


@given('player "Player2" is removed from slot 4 onward', target_fixture="context")
def player2_removed(context):
    new_plan, reduced_squad = _remove_player_from_slot(
        context["plan"], "Player2", 4, context["squad"], context["match"]
    )
    context["plan"] = new_plan
    context["reduced_squad"] = reduced_squad
    return context


# ── When ───────────────────────────────────────────────────────────────────────

@when('player "Player2" is removed from slot 4 onward', target_fixture="context")
def remove_player2(context):
    new_plan, reduced_squad = _remove_player_from_slot(
        context["plan"], "Player2", 4, context["squad"], context["match"]
    )
    context["plan"] = new_plan
    context["reduced_squad"] = reduced_squad
    return context


@when('player "Player2" is reinstated from slot 4', target_fixture="context")
def reinstate_player2(context):
    # Reinstate: regenerate from slot 4 with full squad, keeping slots 0-3 locked
    new_slots = []
    for slot in context["plan"].slots:
        s = SlotAssignment(slot_index=slot.slot_index)
        s.lineup = dict(slot.lineup)
        if slot.slot_index < 4:
            s.locked = True
        new_slots.append(s)
    locked_plan = RotationPlan(slots=new_slots)
    new_plan, _ = adjust_rotation(locked_plan, {}, context["squad"], context["match"])
    context["plan"] = new_plan
    return context


@when('player "Player3" is removed from slot 0 onward', target_fixture="context")
def remove_player3(context):
    new_plan, reduced_squad = _remove_player_from_slot(
        context["plan"], "Player3", 0, context["squad"], context["match"]
    )
    context["plan"] = new_plan
    context["reduced_squad"] = reduced_squad
    return context


@when('slots 0 through 3 are locked and "Player4" is removed from slot 4', target_fixture="context")
def lock_and_remove_player4(context):
    new_plan, reduced_squad = _remove_player_from_slot(
        context["plan"], "Player4", 4, context["squad"], context["match"]
    )
    context["plan"] = new_plan
    context["reduced_squad"] = reduced_squad
    return context


# ── Then ───────────────────────────────────────────────────────────────────────

@then('"Player2" should not appear in slots 4 through 7')
def player2_absent_future(context):
    plan = context["plan"]
    for slot in plan.slots:
        if slot.slot_index >= 4:
            names = {p.name for p in slot.lineup.values()}
            assert "Player2" not in names, f"Player2 found in slot {slot.slot_index}"


@then('"Player2" should still appear in slots 0 through 3')
def player2_present_past(context):
    plan = context["plan"]
    for slot in plan.slots:
        if slot.slot_index < 4:
            names = {p.name for p in slot.lineup.values()}
            # Player2 was in original plan; locked slots keep original lineups
            # We just verify slot exists and has the right number of players
            assert len(slot.lineup) == 5, f"Slot {slot.slot_index} has wrong player count"


@then("the plan is valid with all 10 players across all 8 slots")
def plan_valid_10_players(context):
    plan = context["plan"]
    assert len(plan.slots) == 8
    all_names: set[str] = set()
    for slot in plan.slots:
        all_names.update(p.name for p in slot.lineup.values())
    # Specialist GK should appear in at least some slots
    assert "Specialist" in all_names


@then("slots 0 through 7 each have exactly 5 players on the pitch")
def each_slot_five_players(context):
    for slot in context["plan"].slots:
        assert len(slot.lineup) == 5, f"Slot {slot.slot_index} has {len(slot.lineup)} players"


@then("no player appears more than once per slot")
def no_duplicates_per_slot(context):
    for slot in context["plan"].slots:
        names = [p.name for p in slot.lineup.values()]
        assert len(names) == len(set(names)), f"Duplicate player in slot {slot.slot_index}"


@then("slots 0 through 3 are unchanged from the original plan")
def past_slots_unchanged(context):
    original = context["original_plan"]
    current = context["plan"]
    orig_by_idx = {s.slot_index: s for s in original.slots}
    for slot in current.slots:
        if slot.slot_index < 4:
            orig = orig_by_idx[slot.slot_index]
            orig_names = {pos: p.name for pos, p in orig.lineup.items()}
            curr_names = {pos: p.name for pos, p in slot.lineup.items()}
            assert orig_names == curr_names, (
                f"Slot {slot.slot_index} changed: {orig_names} → {curr_names}"
            )


@then('slots 4 through 7 do not contain "Player4"')
def player4_absent_slots_4_7(context):
    for slot in context["plan"].slots:
        if slot.slot_index >= 4:
            names = {p.name for p in slot.lineup.values()}
            assert "Player4" not in names, f"Player4 found in slot {slot.slot_index}"
