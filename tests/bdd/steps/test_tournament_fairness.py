"""Step definitions for tournament_fairness.feature (Issue1: consecutive sit-out)."""
from __future__ import annotations

from datetime import date

import pytest
from pytest_bdd import given, scenarios, then, when

pytestmark = pytest.mark.bdd

from backend.algorithm.rotation_engine import generate_rotation
from backend.algorithm.validator import validate
from backend.models.game_config import build_tournament_config
from backend.models.match import Match, Squad
from tests.conftest import make_player

scenarios("tournament_fairness.feature")


# ── Given ─────────────────────────────────────────────────────────────────────

@given("a 12-player squad and a short single-period tournament match", target_fixture="context")
def squad_12_short_match():
    squad = Squad(players=[make_player(f"Player{i}") for i in range(12)])
    match = Match(date=date(2026, 4, 12))
    match.fairness = "equal"
    match.game_config = build_tournament_config(5, "1-2-1", 10, False)
    return {"squad": squad, "match": match, "match1_plan": None, "match2_plan": None}


@given("a player who sat out the entire previous tournament match")
def mark_a_player_as_previously_benched(context):
    context["previously_benched"] = {context["squad"].available[0]}


# ── When ──────────────────────────────────────────────────────────────────────

@when("the system generates the first match's rotation plan")
def generate_first_match_plan(context):
    context["match1_plan"] = generate_rotation(context["squad"], context["match"])


@when("the system generates the second match's rotation plan for players benched entirely in the first match")
def generate_second_match_plan(context):
    benched = {
        p for p in context["squad"].available
        if context["match1_plan"].slot_count_for_player(p) == 0
    }
    assert benched, "test setup expects at least one player to sit out match 1 entirely"
    context["benched_in_match1"] = benched
    context["match2_plan"] = generate_rotation(
        context["squad"], context["match"], previous_match_zero_slot_players=benched,
    )


@when("that player is forced to zero slots in the current rotation plan")
def force_zero_slots(context):
    plan = generate_rotation(context["squad"], context["match"])
    zero_slot_player = next(iter(context["previously_benched"]))
    for slot in plan.slots:
        for pos in list(slot.lineup):
            if slot.lineup[pos] is zero_slot_player:
                del slot.lineup[pos]
    context["plan"] = plan


# ── Then ──────────────────────────────────────────────────────────────────────

@then("no player benched entirely in the first match should sit out the second match too")
def no_repeat_sit_out(context):
    for p in context["benched_in_match1"]:
        count = context["match2_plan"].slot_count_for_player(p)
        assert count >= 1, (
            f"{p.name} sat out match 1 entirely and must not sit out match 2 too "
            f"(12-vs-3-style spread must be impossible)"
        )


@then("the validator should report a consecutive sit-out violation")
def validator_reports_violation(context):
    violations = validate(
        context["plan"], context["squad"].available,
        previous_match_zero_slot_players=context["previously_benched"],
    )
    assert any("Consecutive sit-out" in v for v in violations)
