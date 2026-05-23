"""Rotation engine -- main entry point for generating a RotationPlan.

Usage:
    from backend.algorithm.rotation_engine import generate_rotation
    from backend.models.match import Match, Squad

    plan = generate_rotation(squad, match)
    # plan.slots -- list of SlotAssignments (8 for 5v5, 4 for 9v9, etc.)
    # plan.warnings -- any soft warnings (e.g. emergency GK used)
"""
from __future__ import annotations

import random
from collections import defaultdict

from backend.algorithm.gk_selector import select_gk_for_slots
from backend.algorithm.skill_balancer import balance_skills
from backend.algorithm.time_balancer import compute_target_slots
from backend.algorithm.validator import validate
from backend.models.game_config import DEFAULT_CONFIG, GameConfig
from backend.models.match import Match, Squad
from backend.models.player import GKTier, Player
from backend.models.rotation import (
    Position,
    RotationPlan,
    SlotAssignment,
    is_def_position,
    normalize_position,
)


def _resolve_config(match: Match) -> GameConfig:
    return match.game_config or DEFAULT_CONFIG


def generate_rotation(squad: Squad, match: Match) -> RotationPlan:
    """Generate a full rotation plan for the match.

    Raises:
        ValueError: if the squad is too small to fill a lineup
    """
    config = _resolve_config(match)
    rotation_intensity = match.rotation_intensity
    players = squad.available
    n = len(players)
    num_slots = config.total_slots
    outfield_count = config.formation.outfield_count

    if n < config.players_per_slot:
        raise ValueError(
            f"Squad too small: need at least {config.players_per_slot} players, got {n}"
        )

    # Step 1: Determine GK per slot (same GK for both sub-periods of a period)
    gk_assignments, warnings = select_gk_for_slots(
        players, num_slots, squad_size=n, players_per_slot=config.players_per_slot,
    )

    # Identify non-specialist players who will cover GK slots (ordered, de-duped by identity)
    seen_ids: set = set()
    non_specialist_gk_players = []
    for p in gk_assignments:
        if p is not None and p.gk_status != GKTier.SPECIALIST and id(p) not in seen_ids:
            seen_ids.add(id(p))
            non_specialist_gk_players.append(p)

    # Step 2: Compute target slot counts per player
    total_player_slots = num_slots * config.players_per_slot
    targets = compute_target_slots(players, total_player_slots, non_specialist_gk_players)

    # Pre-compute future GK slots for each player (slots not yet processed).
    future_gk: dict = defaultdict(int)
    for gk in gk_assignments:
        if gk is not None:
            future_gk[id(gk)] += 1

    # Step 3: Build slot assignments
    plan = _build_slots(players, gk_assignments, targets, future_gk, num_slots, config, rotation_intensity)
    plan.warnings.extend(warnings)

    # Step 4: Skill balance optimisation (soft preference)
    plan = balance_skills(plan, config)

    # Step 4b: Restore position consistency — carried players should keep their H1 position
    plan = _align_mid_quarter_positions(plan, config)

    # Step 5: Validate
    violations = validate(plan, players, config)
    if violations:
        plan.warnings.extend(["VIOLATION: " + v for v in violations])

    return plan


def _align_mid_quarter_positions(
    plan: RotationPlan, config: GameConfig,
) -> RotationPlan:
    """Swap outfield positions within H2 slots so carried players keep their H1 position.

    Only swaps position *labels* within a slot — never changes which players
    are on the pitch — so sub limits and playing-time constraints are unaffected.
    DEF-restriction is explicitly checked before any swap.
    """
    outfield_pos_keys = config.formation.outfield_positions()
    for period in range(len(plan.slots) // 2):
        h1 = plan.slots[period * 2]
        h2 = plan.slots[period * 2 + 1]
        for pos_key in outfield_pos_keys:
            pos = Position(pos_key)
            h1_player = h1.lineup.get(pos)
            if h1_player is None:
                continue
            # Find where this player ended up in H2
            h2_pos = next(
                (p for p, pl in h2.lineup.items() if pl is h1_player and p != Position.GK),
                None,
            )
            if h2_pos is None or h2_pos == pos:
                continue  # went to bench, or already correct
            # Swap with whoever occupies `pos` in H2
            h2_occupant = h2.lineup.get(pos)
            if h2_occupant is None:
                continue
            # Skip if either player would end up in DEF while def_restricted
            if is_def_position(pos) and h1_player.def_restricted:
                continue
            if is_def_position(h2_pos) and h2_occupant.def_restricted:
                continue
            # Skip if moving h2_occupant to h2_pos would give them a 3rd position type
            h2_pos_label = normalize_position(h2_pos)
            occupant_positions = {
                normalize_position(p)
                for s in plan.slots for p, pl in s.lineup.items()
                if pl is h2_occupant and p != Position.GK
            }
            if h2_pos_label not in occupant_positions and len(occupant_positions) >= 2:
                continue
            h2.lineup[pos] = h1_player
            h2.lineup[h2_pos] = h2_occupant
    return plan


def _build_slots(
    players: list,
    gk_assignments: list,
    targets: dict,
    future_gk: dict,
    num_slots: int,
    config: GameConfig,
    rotation_intensity: int = 50,
) -> RotationPlan:
    """Assign players to all slots respecting constraints."""
    outfield_count = config.formation.outfield_count
    slot_counts: dict = defaultdict(int)
    position_sets: dict = defaultdict(set)
    slots: list = []
    remaining_gk = dict(future_gk)

    for slot_index in range(num_slots):
        gk_player = gk_assignments[slot_index]
        slot = SlotAssignment(slot_index=slot_index)

        if gk_player is not None:
            slot.lineup[Position.GK] = gk_player
            slot_counts[gk_player] += 1
            position_sets[gk_player].add("GK")
            remaining_gk[id(gk_player)] = max(0, remaining_gk.get(id(gk_player), 0) - 1)

        is_mid_period = slot_index % 2 == 1
        prev_slot = slots[-1] if slots else None

        if is_mid_period and prev_slot is not None:
            outfield_players = _select_outfield_mid_period(
                players, gk_player, prev_slot, targets, slot_counts, remaining_gk,
                outfield_count, config.mid_period_subs,
            )
        else:
            outfield_candidates = _eligible_outfield(
                players, gk_player, targets, slot_counts, remaining_gk
            )
            outfield_players = _select_outfield(
                outfield_candidates, targets, slot_counts, remaining_gk, outfield_count,
            )

        _assign_outfield_positions(
            slot, outfield_players, position_sets, slot_counts, config, rotation_intensity,
        )
        slots.append(slot)

    return RotationPlan(slots=slots)


def _eligible_outfield(
    players: list,
    gk_player: object,
    targets: dict,
    slot_counts: dict,
    remaining_gk: dict,
) -> list:
    """Return players eligible for outfield selection."""
    return [
        p for p in players
        if p is not gk_player
        and p.gk_status != GKTier.SPECIALIST
        and slot_counts[p] + remaining_gk.get(id(p), 0) < targets.get(p, 0)
    ]


def _select_outfield(
    candidates: list, targets: dict, slot_counts: dict, remaining_gk: dict,
    outfield_count: int,
) -> list:
    """Select outfield players for a regular (period-start) slot."""
    def sort_key(p: Player) -> tuple:
        outfield_budget = targets.get(p, 0) - slot_counts[p] - remaining_gk.get(id(p), 0)
        return (slot_counts[p], -outfield_budget)

    shuffled = list(candidates)
    random.shuffle(shuffled)
    selected = sorted(shuffled, key=sort_key)[:outfield_count]
    return selected


def _select_outfield_mid_period(
    all_players: list,
    gk_player: object,
    prev_slot: SlotAssignment,
    targets: dict,
    slot_counts: dict,
    remaining_gk: dict,
    outfield_count: int,
    mid_period_subs: int,
) -> list:
    """Select outfield players for a mid-period slot (limited new players vs previous slot).

    Strategy:
    - Carry over as many outfield players as possible from the previous slot
    - Bring in at most mid_period_subs new players
    """
    prev_outfield = prev_slot.outfield_players

    def budget(p: Player) -> int:
        return targets.get(p, 0) - slot_counts[p] - remaining_gk.get(id(p), 0)

    # Sort prev outfield by budget descending — most remaining time = stay on
    shuffled_prev = list(prev_outfield)
    random.shuffle(shuffled_prev)
    carried_candidates = sorted(shuffled_prev, key=lambda p: -budget(p))

    # Carry players who still have budget remaining
    max_carry = outfield_count - 1  # at least 1 slot for potential new player
    carry_over = [p for p in carried_candidates if budget(p) > 0][:max_carry]

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
    slots_needed = outfield_count - len(carry_over)
    # Cap new players by mid-period sub limit
    max_new = min(slots_needed, mid_period_subs)
    new_players = bench_sorted[:max_new]

    # If we capped new players, fill remaining from carry-over
    if len(new_players) < slots_needed:
        extra_carry = [p for p in carried_candidates if budget(p) > 0 and p not in carry_over]
        carry_over += extra_carry[:slots_needed - len(new_players)]

    result = carry_over + new_players

    # If still short, pull remaining within-budget players from anywhere
    if len(result) < outfield_count:
        result_ids = {id(p) for p in result}
        if gk_player is not None:
            result_ids.add(id(gk_player))
        extras_in_budget = [
            p for p in all_players
            if id(p) not in result_ids
            and p.gk_status != GKTier.SPECIALIST
            and budget(p) > 0
        ]
        result += extras_in_budget[:outfield_count - len(result)]

    # Last resort: prefer over-budget carry-overs (minimizes changes), then bench
    if len(result) < outfield_count:
        result_ids = {id(p) for p in result}
        if gk_player is not None:
            result_ids.add(id(gk_player))
        # First try carrying over more from previous slot (over-budget but fewer changes)
        over_budget_carry = [
            p for p in prev_outfield
            if id(p) not in result_ids and p.gk_status != GKTier.SPECIALIST
        ]
        result += over_budget_carry[:outfield_count - len(result)]

    if len(result) < outfield_count:
        result_ids = {id(p) for p in result}
        if gk_player is not None:
            result_ids.add(id(gk_player))
        over_budget_bench = [
            p for p in all_players
            if id(p) not in result_ids and p.gk_status != GKTier.SPECIALIST
        ]
        result += over_budget_bench[:outfield_count - len(result)]

    return result


def _assign_outfield_positions(
    slot: SlotAssignment,
    players: list,
    position_sets: dict,
    slot_counts: dict,
    config: GameConfig,
    rotation_intensity: int = 50,
) -> None:
    """Assign outfield positions to selected players.

    Uses a most-constrained-first ordering: the position type with fewest
    players who can fill it without a 3rd-position violation is assigned first.
    DEF restriction is enforced as a hard constraint throughout.
    """
    unassigned = list(players)
    assigned: dict = {}

    # Build position map dynamically from formation
    pos_keys = config.formation.outfield_positions()
    pos_enum = {key: Position(key) for key in pos_keys}

    # How many distinct outfield position types exist in this formation
    outfield_types = {normalize_position(k) for k in pos_keys}
    num_outfield_types = len(outfield_types)  # e.g. 3 for DEF/MID/FWD

    # rotation_intensity controls how many position types a player can accumulate:
    # 0 (specialist) → 1 type, 50 → ~2 types, 100 (all-rounder) → all types
    max_pos_types = max(1, round(1 + (num_outfield_types - 1) * rotation_intensity / 100))

    def free_candidates(pos_label: str, pool: list) -> list:
        """Players who can take pos_label without exceeding the position type limit."""
        norm = normalize_position(pos_label)
        return [
            p for p in pool
            if norm in position_sets[p] or len(position_sets[p]) < max_pos_types
        ]

    remaining = list(pos_enum.keys())
    while remaining and unassigned:
        def pool_for(lbl: str) -> list:
            norm = normalize_position(lbl)
            # Filter by preferred_positions (hard constraint) and DEF restriction
            p = [
                x for x in unassigned
                if not (is_def_position(lbl) and x.def_restricted)
                and _can_play_position(x, norm)
            ]
            # Fallback: if nobody's preferred_positions match, use anyone eligible
            if not p:
                p = [x for x in unassigned if not (is_def_position(lbl) and x.def_restricted)]
            return p if p else unassigned

        remaining.sort(key=lambda lbl: len(free_candidates(lbl, pool_for(lbl))))
        pos_label = remaining.pop(0)

        pool = pool_for(pos_label)
        player = _pick_for_position(
            pos_label, pool, position_sets, max_pos_types, rotation_intensity,
        )
        assigned[pos_enum[pos_label]] = player
        unassigned.remove(player)

    for pos, player in assigned.items():
        slot.lineup[pos] = player
        position_sets[player].add(normalize_position(pos))
        slot_counts[player] += 1


def _can_play_position(player: Player, norm_pos: str) -> bool:
    """Return True if a player's preferred_positions allow this position type.

    Players with empty preferred_positions can play anything (backward compat).
    """
    if not player.preferred_positions:
        return True
    return norm_pos in player.preferred_positions


def _pick_for_position(
    pos_label: str, candidates: list, position_sets: dict,
    max_pos_types: int = 3, rotation_intensity: int = 50,
) -> Player:
    """Pick the best candidate for a position.

    Low rotation (specialist): prefer players whose best_position matches,
    then players who already play this position.
    High rotation (all-rounder): prefer players who HAVEN'T played this
    position yet, spreading experience across preferred positions.
    """
    norm_label = normalize_position(pos_label)

    if rotation_intensity < 40:
        # Low rotation: prefer best_position match, then already plays
        best_match = [
            p for p in candidates
            if p.best_position and normalize_position(p.best_position) == norm_label
        ]
        if best_match:
            return min(best_match, key=lambda p: len(position_sets[p]))

        already_plays = [p for p in candidates if norm_label in position_sets[p]]
        if already_plays:
            return min(already_plays, key=lambda p: len(position_sets[p]))
    else:
        # High rotation: prefer new experience
        new_experience = [
            p for p in candidates
            if norm_label not in position_sets[p] and len(position_sets[p]) < max_pos_types
        ]
        if new_experience:
            return min(new_experience, key=lambda p: len(position_sets[p]))

    # Fallback: anyone who can absorb without exceeding the type limit
    can_absorb = [p for p in candidates if len(position_sets[p]) < max_pos_types]
    if can_absorb:
        return min(can_absorb, key=lambda p: len(position_sets[p]))

    # Last resort
    return min(candidates, key=lambda p: len(position_sets[p]))
