"""Rotation plan validator.

Checks hard constraints and returns a list of violation messages.
Empty list = plan is valid.
"""
from __future__ import annotations

from backend.models.player import GKTier, Player
from backend.models.rotation import Position, RotationPlan


def validate(plan: RotationPlan, all_players: list) -> list:
    """Return list of constraint violations. Empty = valid."""
    violations: list = []
    violations += _check_def_restrictions(plan, all_players)
    violations += _check_position_variety(plan, all_players)
    violations += _check_gk_mid_quarter_change(plan)
    violations += _check_mid_quarter_sub_limit(plan)
    violations += _check_playing_time_equality(plan, all_players)
    violations += _check_specialist_never_outfield(plan, all_players)
    return violations


def _check_def_restrictions(plan: RotationPlan, players: list) -> list:
    violations = []
    for slot in plan.slots:
        for pos, player in slot.lineup.items():
            if pos == Position.DEF and player.def_restricted:
                violations.append(
                    f"DEF restriction violated: {player.name} assigned DEF in slot {slot.slot_index}"
                )
    return violations


def _check_position_variety(plan: RotationPlan, players: list) -> list:
    violations = []
    for player in players:
        positions_used = {
            pos
            for slot in plan.slots
            for pos, p in slot.lineup.items()
            if p is player
        }
        # Normalise MID1/MID2 -- both count as "MID" for variety purposes
        normalised = set()
        for pos in positions_used:
            normalised.add("MID" if pos in (Position.MID1, Position.MID2) else pos.value)
        if len(normalised) > 2:
            violations.append(
                f"Position variety violated: {player.name} plays {len(normalised)} different positions "
                f"({', '.join(sorted(normalised))})"
            )
    return violations


def _check_gk_mid_quarter_change(plan: RotationPlan) -> list:
    violations = []
    for i in range(0, len(plan.slots) - 1, 2):
        if i + 1 >= len(plan.slots):
            break
        gk_first = plan.slots[i].gk
        gk_second = plan.slots[i + 1].gk
        if gk_first != gk_second:
            violations.append(
                f"GK mid-quarter change in Q{plan.slots[i].quarter}: "
                f"{getattr(gk_first, 'name', None)} -> {getattr(gk_second, 'name', None)}"
            )
    return violations


def _check_mid_quarter_sub_limit(plan: RotationPlan) -> list:
    violations = []
    for i in range(0, len(plan.slots) - 1, 2):
        if i + 1 >= len(plan.slots):
            break
        players_before = set(id(p) for p in plan.slots[i].players)
        players_after = set(id(p) for p in plan.slots[i + 1].players)
        changes = len(players_before - players_after)
        if changes > 2:
            violations.append(
                f"Mid-quarter sub limit exceeded in Q{plan.slots[i].quarter}: "
                f"{changes} players changed (max 2)"
            )
    return violations


def _check_playing_time_equality(plan: RotationPlan, players: list) -> list:
    counts = {p: plan.slot_count_for_player(p) for p in players}
    if not counts:
        return []
    min_slots = min(counts.values())
    max_slots = max(counts.values())
    if max_slots - min_slots > 1:
        return [
            f"Playing time inequality: max {max_slots} vs min {min_slots} slots "
            f"(difference {max_slots - min_slots}, max allowed 1)"
        ]
    return []


def _check_specialist_never_outfield(plan: RotationPlan, players: list) -> list:
    violations = []
    specialists = [p for p in players if p.gk_status == GKTier.SPECIALIST]
    for specialist in specialists:
        for slot in plan.slots:
            for pos, player in slot.lineup.items():
                if player is specialist and pos != Position.GK:
                    violations.append(
                        f"Specialist {specialist.name} assigned outfield position "
                        f"{pos.value} in slot {slot.slot_index}"
                    )
    return violations
