"""Rotation plan validator.

Checks hard constraints and returns a list of violation messages.
Empty list = plan is valid.
"""
from __future__ import annotations

from backend.models.game_config import DEFAULT_CONFIG, GameConfig
from backend.models.player import GKTier
from backend.models.rotation import Position, RotationPlan, is_def_position, normalize_position


def validate(
    plan: RotationPlan,
    all_players: list,
    config: GameConfig | None = None,
) -> list:
    """Return list of constraint violations. Empty = valid."""
    cfg = config or DEFAULT_CONFIG
    violations: list = []
    violations += _check_def_restrictions(plan, all_players)
    violations += _check_position_variety(plan, all_players, cfg)
    violations += _check_gk_mid_period_change(plan)
    violations += _check_mid_period_sub_limit(plan, cfg)
    violations += _check_playing_time_equality(plan, all_players, cfg)
    violations += _check_specialist_never_outfield(plan, all_players)
    return violations


def _check_def_restrictions(plan: RotationPlan, players: list) -> list:
    violations = []
    for slot in plan.slots:
        for pos, player in slot.lineup.items():
            if is_def_position(pos) and player.def_restricted:
                violations.append(
                    f"DEF restriction violated: {player.name} "
                    f"assigned {pos} in slot {slot.slot_index}"
                )
    return violations


def _check_position_variety(plan: RotationPlan, players: list, config: GameConfig) -> list:
    # Max position types = number of distinct outfield types in the formation + GK
    outfield_types = {normalize_position(p) for p in config.formation.outfield_positions()}
    max_types = len(outfield_types) + 1  # +1 for GK
    violations = []
    for player in players:
        positions_used = {
            pos
            for slot in plan.slots
            for pos, p in slot.lineup.items()
            if p is player
        }
        normalised = {normalize_position(pos) for pos in positions_used}
        if len(normalised) > max_types:
            violations.append(
                f"Position variety violated: {player.name} plays "
                f"{len(normalised)} different positions "
                f"({', '.join(sorted(normalised))})"
            )
    return violations


def _check_gk_mid_period_change(plan: RotationPlan) -> list:
    violations = []
    for i in range(0, len(plan.slots) - 1, 2):
        if i + 1 >= len(plan.slots):
            break
        gk_first = plan.slots[i].gk
        gk_second = plan.slots[i + 1].gk
        if gk_first != gk_second:
            violations.append(
                f"GK mid-period change in period {plan.slots[i].quarter}: "
                f"{getattr(gk_first, 'name', None)} -> {getattr(gk_second, 'name', None)}"
            )
    return violations


def _check_mid_period_sub_limit(plan: RotationPlan, config: GameConfig) -> list:
    violations = []
    max_subs = config.mid_period_subs
    for i in range(0, len(plan.slots) - 1, 2):
        if i + 1 >= len(plan.slots):
            break
        players_before = set(id(p) for p in plan.slots[i].players)
        players_after = set(id(p) for p in plan.slots[i + 1].players)
        changes = len(players_before - players_after)
        if changes > max_subs:
            violations.append(
                f"Mid-period sub limit exceeded in period {plan.slots[i].quarter}: "
                f"{changes} players changed (max {max_subs})"
            )
    return violations


def _check_playing_time_equality(
    plan: RotationPlan, players: list, config: GameConfig,
) -> list:
    counts = {p: plan.slot_count_for_player(p) for p in players}
    if not counts:
        return []
    min_slots = min(counts.values())
    max_slots = max(counts.values())
    # In competitive mode, allow wider distribution (scaled by total slots)
    # Equal mode: max 1 slot diff. Competitive: up to ~30% of total slots
    max_allowed = max(1, config.total_slots // 3)
    if max_slots - min_slots > max_allowed:
        return [
            f"Playing time inequality: max {max_slots} vs min {min_slots} slots "
            f"(difference {max_slots - min_slots}, max allowed {max_allowed})"
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
