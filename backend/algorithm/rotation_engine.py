"""Rotation engine -- main entry point for generating a RotationPlan.

Usage:
    from backend.algorithm.rotation_engine import generate_rotation
    from backend.models.match import Match, Squad

    plan = generate_rotation(squad, match)
    # plan.slots -- list of 8 SlotAssignments
    # plan.warnings -- any soft warnings (e.g. emergency GK used)
"""
from __future__ import annotations

import random
from collections import defaultdict

from backend.algorithm.gk_selector import select_gk_for_slots
from backend.algorithm.time_balancer import compute_target_slots
from backend.algorithm.validator import validate
from backend.models.match import Match, Squad
from backend.models.player import GKTier, Player
from backend.models.rotation import (
    OUTFIELD_POSITIONS,
    Position,
    RotationPlan,
    SlotAssignment,
)


def generate_rotation(squad: Squad, match: Match) -> RotationPlan:
    """Generate a full rotation plan for the match.

    Raises:
        ValueError: if the squad is too small (< 5) to fill a lineup
    """
    players = squad.available
    n = len(players)
    num_slots = match.half_quarters  # 8 for a standard 4-quarter match

    if n < 5:
        raise ValueError(f"Squad too small: need at least 5 players, got {n}")

    # Step 1: Determine GK per slot (same GK for both half-quarters of a quarter)
    gk_assignments, warnings = select_gk_for_slots(players, num_slots, squad_size=n)

    # Identify non-specialist players who will cover GK slots (ordered, de-duped by identity)
    seen_ids: set = set()
    non_specialist_gk_players = []
    for p in gk_assignments:
        if p is not None and p.gk_status != GKTier.SPECIALIST and id(p) not in seen_ids:
            seen_ids.add(id(p))
            non_specialist_gk_players.append(p)

    # Step 2: Compute target slot counts per player
    targets = compute_target_slots(players, num_slots * 5, non_specialist_gk_players)

    # Pre-compute future GK slots for each player (slots not yet processed).
    # This prevents GK players being over-selected for outfield.
    # future_gk[player_id] = count of GK slots in the entire assignment list
    future_gk: dict = defaultdict(int)
    for gk in gk_assignments:
        if gk is not None:
            future_gk[id(gk)] += 1

    # Step 3: Build slot assignments
    plan = _build_slots(players, gk_assignments, targets, future_gk, num_slots)
    plan.warnings.extend(warnings)

    # Step 4: Validate
    violations = validate(plan, players)
    if violations:
        plan.warnings.extend(["VIOLATION: " + v for v in violations])

    return plan


def _build_slots(
    players: list,
    gk_assignments: list,
    targets: dict,
    future_gk: dict,
    num_slots: int,
) -> RotationPlan:
    """Assign players to all slots respecting constraints.

    Key constraint: at mid-quarter transitions (slot i -> slot i+1 where i is even),
    at most 2 outfield players may change. GK is guaranteed the same by per-quarter
    GK assignment.

    future_gk[player_id] tracks GK slots remaining (decremented as they're processed).
    Outfield candidates must satisfy: slot_counts + future_gk_remaining < target.
    """
    slot_counts: dict = defaultdict(int)
    position_sets: dict = defaultdict(set)
    slots: list = []
    # Track remaining future GK (decremented as slots are processed)
    remaining_gk = dict(future_gk)  # copy so we can decrement

    for slot_index in range(num_slots):
        gk_player = gk_assignments[slot_index]
        slot = SlotAssignment(slot_index=slot_index)

        if gk_player is not None:
            slot.lineup[Position.GK] = gk_player
            slot_counts[gk_player] += 1
            position_sets[gk_player].add("GK")
            remaining_gk[id(gk_player)] = max(0, remaining_gk.get(id(gk_player), 0) - 1)

        is_mid_quarter = slot_index % 2 == 1
        prev_slot = slots[-1] if slots else None

        if is_mid_quarter and prev_slot is not None:
            outfield_players = _select_outfield_mid_quarter(
                players, gk_player, prev_slot, targets, slot_counts, remaining_gk
            )
        else:
            outfield_candidates = _eligible_outfield(
                players, gk_player, targets, slot_counts, remaining_gk
            )
            outfield_players = _select_outfield(outfield_candidates, targets, slot_counts, remaining_gk)

        _assign_outfield_positions(slot, outfield_players, position_sets, slot_counts)
        slots.append(slot)

    return RotationPlan(slots=slots)


def _eligible_outfield(
    players: list,
    gk_player: object,
    targets: dict,
    slot_counts: dict,
    remaining_gk: dict,
) -> list:
    """Return players eligible for outfield selection.

    A player is eligible if:
    - Not the current GK
    - Not a specialist (never plays outfield)
    - Their current slot count + remaining future GK slots < their target
      (i.e. they have outfield budget remaining)
    """
    return [
        p for p in players
        if p is not gk_player
        and p.gk_status != GKTier.SPECIALIST
        and slot_counts[p] + remaining_gk.get(id(p), 0) < targets.get(p, 0)
    ]


def _select_outfield(candidates: list, targets: dict, slot_counts: dict, remaining_gk: dict) -> list:
    """Select 4 outfield players for a regular (quarter-start) slot.

    Sort: fewest slots played first, then most outfield budget remaining.
    Players with identical priority are shuffled so results vary each run.
    """
    def sort_key(p: Player) -> tuple:
        outfield_budget = targets.get(p, 0) - slot_counts[p] - remaining_gk.get(id(p), 0)
        return (slot_counts[p], -outfield_budget)

    shuffled = list(candidates)
    random.shuffle(shuffled)  # shuffle first so equal-priority players vary each run
    return sorted(shuffled, key=sort_key)[:4]


def _select_outfield_mid_quarter(
    all_players: list,
    gk_player: object,
    prev_slot: SlotAssignment,
    targets: dict,
    slot_counts: dict,
    remaining_gk: dict,
) -> list:
    """Select outfield players for a mid-quarter slot (max 2 new players vs previous slot).

    Strategy:
    - Carry over at least 2 outfield players from the previous slot
    - Bring in at most 2 new players (bench players with most playing time owed)
    """
    prev_outfield = prev_slot.outfield_players

    # Carried candidates sorted by how much outfield budget they have remaining
    # (most budget = most valuable to carry = least urgent to sub off)
    def budget(p: Player) -> int:
        return targets.get(p, 0) - slot_counts[p] - remaining_gk.get(id(p), 0)

    # Sort prev outfield by budget descending — most remaining time = stay on
    shuffled_prev = list(prev_outfield)
    random.shuffle(shuffled_prev)
    carried_candidates = sorted(shuffled_prev, key=lambda p: -budget(p))

    # Carry players who still have budget remaining (never force-carry over target)
    carry_over = [p for p in carried_candidates if budget(p) > 0][:3]

    prev_ids = {id(p) for p in prev_slot.players}
    carried_ids = {id(p) for p in carry_over}
    if gk_player is not None:
        carried_ids.add(id(gk_player))

    # New players from bench (not in the previous slot) with outfield budget
    bench_candidates = [
        p for p in all_players
        if id(p) not in prev_ids
        and id(p) not in carried_ids
        and p.gk_status != GKTier.SPECIALIST
        and (gk_player is None or id(p) != id(gk_player))
        and budget(p) > 0
    ]
    random.shuffle(bench_candidates)

    def bench_sort_key(p: Player) -> tuple:
        return (slot_counts[p], -budget(p))

    bench_sorted = sorted(bench_candidates, key=bench_sort_key)
    slots_needed = 4 - len(carry_over)
    new_players = bench_sorted[:slots_needed]

    result = carry_over + new_players

    # If still short (rare — budget exhaustion), pull remaining within-budget players
    # from anywhere, then as a last resort accept over-budget (validator will flag)
    if len(result) < 4:
        result_ids = {id(p) for p in result}
        if gk_player is not None:
            result_ids.add(id(gk_player))
        extras_in_budget = [
            p for p in all_players
            if id(p) not in result_ids
            and p.gk_status != GKTier.SPECIALIST
            and budget(p) > 0
        ]
        result += extras_in_budget[:4 - len(result)]

    return result


def _assign_outfield_positions(
    slot: SlotAssignment,
    players: list,
    position_sets: dict,
    slot_counts: dict,
) -> None:
    """Assign DEF, MID1, MID2, FWD to the 4 outfield players."""
    unassigned = list(players)
    assigned: dict = {}

    can_play_def = [p for p in unassigned if not p.def_restricted]
    def_restricted_only = [p for p in unassigned if p.def_restricted]

    if can_play_def:
        def_player = _pick_for_position("DEF", can_play_def, position_sets)
        assigned[Position.DEF] = def_player
        unassigned.remove(def_player)
    elif def_restricted_only:
        # No non-restricted player -- validator will flag this
        assigned[Position.DEF] = unassigned[0]
        unassigned.remove(unassigned[0])

    for pos in [Position.MID1, Position.MID2, Position.FWD]:
        if not unassigned:
            break
        player = _pick_for_position(pos.value, unassigned, position_sets)
        assigned[pos] = player
        unassigned.remove(player)

    for pos, player in assigned.items():
        slot.lineup[pos] = player
        pos_label = "MID" if pos in (Position.MID1, Position.MID2) else pos.value
        position_sets[player].add(pos_label)
        slot_counts[player] += 1


def _pick_for_position(pos_label: str, candidates: list, position_sets: dict) -> Player:
    """Pick the best candidate for a position.

    Priority:
    1. Players who already play this position (no new position type introduced)
    2. Players who have fewer than 2 position types (can absorb a new one)
    3. Anyone remaining (validator will flag if >2 positions result)
    """
    norm_label = "MID" if pos_label in ("MID1", "MID2") else pos_label
    already_plays = [p for p in candidates if norm_label in position_sets[p]]
    if already_plays:
        return min(already_plays, key=lambda p: len(position_sets[p]))
    can_absorb = [p for p in candidates if len(position_sets[p]) < 2]
    pool = can_absorb if can_absorb else candidates
    return min(pool, key=lambda p: len(position_sets[p]))
