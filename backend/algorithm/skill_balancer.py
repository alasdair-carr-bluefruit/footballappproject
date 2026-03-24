"""Skill balancer — soft preference optimiser (v0.3).

Post-processes a RotationPlan to reduce variance in per-slot outfield skill
totals by trying pairwise player swaps between slots.

Constraints respected during swaps:
- DEF-restricted players never moved into DEF
- GK specialist never swapped into outfield
- Mid-quarter swap limit: at most 2 player changes between slot i and i+1
  where i is even (i.e. within a quarter). Swapping a player between a
  mid-quarter pair counts as an additional change.
- GK never changed (swaps only touch outfield players)
- Position variety: a swap that would give either player a 3rd position type
  is skipped (soft — we attempt it but don't force it)

Strategy: iterative improvement. Repeat until no improving swap is found
or a maximum iteration cap is hit.
"""
from __future__ import annotations

import itertools
from dataclasses import replace

from backend.models.player import GKTier, Player
from backend.models.rotation import OUTFIELD_POSITIONS, Position, RotationPlan, SlotAssignment


def balance_skills(plan: RotationPlan) -> RotationPlan:
    """Return a new RotationPlan with improved outfield skill balance.

    Performs iterative pairwise swaps. Original plan is not mutated.
    """
    slots = [_copy_slot(s) for s in plan.slots]
    improved = True
    iterations = 0
    max_iterations = 50  # safety cap

    while improved and iterations < max_iterations:
        improved = False
        iterations += 1
        for i, j in itertools.combinations(range(len(slots)), 2):
            if _try_best_swap(slots, i, j):
                improved = True

    return RotationPlan(slots=slots, warnings=list(plan.warnings))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _copy_slot(slot: SlotAssignment) -> SlotAssignment:
    new = SlotAssignment(slot_index=slot.slot_index)
    new.lineup = dict(slot.lineup)
    return new


def _skill_variance(slots: list) -> float:
    totals = [s.outfield_skill_total for s in slots]
    mean = sum(totals) / len(totals)
    return sum((t - mean) ** 2 for t in totals)


def _try_best_swap(slots: list, i: int, j: int) -> bool:
    """Try all outfield player pairs between slot i and slot j.

    Applies the best variance-reducing swap found (if any).
    Returns True if a swap was applied.
    """
    slot_i = slots[i]
    slot_j = slots[j]

    best_delta = 0.0
    best_swap = None

    outfield_i = [(pos, p) for pos, p in slot_i.lineup.items() if pos != Position.GK]
    outfield_j = [(pos, p) for pos, p in slot_j.lineup.items() if pos != Position.GK]

    current_variance = _skill_variance(slots)

    for (pos_i, player_i), (pos_j, player_j) in itertools.product(outfield_i, outfield_j):
        if player_i is player_j:
            continue

        # Check hard constraints for both directions of the swap
        if not _swap_is_valid(slots, i, j, pos_i, player_i, pos_j, player_j):
            continue

        # Tentatively apply swap
        slot_i.lineup[pos_i] = player_j
        slot_j.lineup[pos_j] = player_i

        new_variance = _skill_variance(slots)
        delta = current_variance - new_variance

        # Revert
        slot_i.lineup[pos_i] = player_i
        slot_j.lineup[pos_j] = player_j

        if delta > best_delta:
            best_delta = delta
            best_swap = (pos_i, player_i, pos_j, player_j)

    if best_swap is not None:
        pos_i, player_i, pos_j, player_j = best_swap
        slots[i].lineup[pos_i] = player_j
        slots[j].lineup[pos_j] = player_i
        return True

    return False


def _swap_is_valid(
    slots: list,
    i: int,
    j: int,
    pos_i: Position,
    player_i: Player,
    pos_j: Position,
    player_j: Player,
) -> bool:
    """Return True if swapping player_i (at pos_i in slot i) with player_j
    (at pos_j in slot j) is valid under all hard constraints."""

    # Specialist never plays outfield
    if player_i.gk_status == GKTier.SPECIALIST or player_j.gk_status == GKTier.SPECIALIST:
        return False

    # DEF restriction
    if pos_i == Position.DEF and player_j.def_restricted:
        return False
    if pos_j == Position.DEF and player_i.def_restricted:
        return False

    # Prevent duplicate: player must not already exist in the destination slot
    slot_i_players = {id(p) for pos, p in slots[i].lineup.items() if pos != pos_i}
    slot_j_players = {id(p) for pos, p in slots[j].lineup.items() if pos != pos_j}
    if id(player_j) in slot_i_players:
        return False
    if id(player_i) in slot_j_players:
        return False

    # Mid-quarter sub limit: any mid-quarter transition (H1→H2 within a quarter)
    # must have ≤ 2 outfield changes after this swap.
    # A swap can affect the transition within slot i's quarter AND slot j's quarter,
    # so we check all impacted pairs.
    if not _all_mid_quarter_limits_ok(slots, i, j, pos_i, player_i, pos_j, player_j):
        return False

    # Position variety: skip if either player would gain a 3rd position type
    norm_i = _norm_pos(pos_i)
    norm_j = _norm_pos(pos_j)
    if not _position_variety_ok(slots, i, player_i, norm_j):
        return False
    if not _position_variety_ok(slots, j, player_j, norm_i):
        return False

    return True


def _all_mid_quarter_limits_ok(
    slots: list,
    i: int,
    j: int,
    pos_i: Position,
    player_i: Player,
    pos_j: Position,
    player_j: Player,
) -> bool:
    """Return True if all mid-quarter transitions still respect ≤2 changes after this swap.

    A swap of player_i (slot i) with player_j (slot j) can affect the mid-quarter
    transition within slot i's quarter AND slot j's quarter — we check both.
    """
    # Find every (H1, H2) pair whose transition is affected by this swap
    affected_pairs: set = set()
    for slot_idx in [i, j]:
        partner = slot_idx + 1 if slot_idx % 2 == 0 else slot_idx - 1
        if 0 <= partner < len(slots):
            pair = (min(slot_idx, partner), max(slot_idx, partner))
            affected_pairs.add(pair)

    for (first_idx, second_idx) in affected_pairs:
        if not _transition_ok_after_swap(slots, first_idx, second_idx, i, j, player_i, player_j):
            return False
    return True


def _effective_outfield_ids(
    slot: SlotAssignment,
    slot_idx: int,
    swap_from: int,
    swap_to: int,
    player_out: Player,
    player_in: Player,
) -> frozenset:
    """Return the set of outfield player ids in this slot after a proposed swap.

    If slot_idx == swap_from: player_out is replaced by player_in.
    If slot_idx == swap_to: player_in is replaced by player_out.
    """
    ids = {id(p) for p in slot.outfield_players}
    if slot_idx == swap_from:
        ids = (ids - {id(player_out)}) | {id(player_in)}
    elif slot_idx == swap_to:
        ids = (ids - {id(player_in)}) | {id(player_out)}
    return frozenset(ids)


def _transition_ok_after_swap(
    slots: list,
    first_idx: int,
    second_idx: int,
    i: int,
    j: int,
    player_i: Player,
    player_j: Player,
) -> bool:
    """Check that the mid-quarter transition (first_idx → second_idx) has ≤ 2 changes."""
    first_ids = _effective_outfield_ids(slots[first_idx], first_idx, i, j, player_i, player_j)
    second_ids = _effective_outfield_ids(slots[second_idx], second_idx, i, j, player_i, player_j)
    changes = len(first_ids.symmetric_difference(second_ids)) // 2
    return changes <= 2


def _norm_pos(pos: Position) -> str:
    return "MID" if pos in (Position.MID1, Position.MID2) else pos.value


def _position_variety_ok(slots: list, slot_idx: int, player: Player, new_pos_label: str) -> bool:
    """Return True if assigning player to new_pos_label in slot_idx doesn't
    give them more than 2 distinct position types across the whole plan."""
    current_positions: set = set()
    for s in slots:
        for pos, p in s.lineup.items():
            if p is player and pos != Position.GK:
                current_positions.add(_norm_pos(pos))

    # new_pos_label may already be in their set — fine
    after = current_positions | {new_pos_label}
    return len(after) <= 2
