"""GK slot assignment logic.

GK assignments are made per quarter (not per slot), since the GK never
changes mid-quarter. The same GK is duplicated for both half-quarters
of each quarter.

Priority order (strict tier fallback, not mixing):
  1. specialist  -- see squad_size rules
  2. preferred   -- first choice when specialist absent or off-bench
  3. can_play    -- second choice
  4. emergency_only -- last resort; adds warning to plan

Time budget:
  max GK quarters per player = floor(fair_share_slots / 2)
  This prevents any one GK player from exceeding their fair share of total slots.
  When a player exhausts their GK quarter budget, the next eligible tier is used.
"""
from __future__ import annotations

import random

from backend.models.player import GKTier, Player


def select_gk_for_slots(
    players: list,
    num_slots: int,
    squad_size: int,
    players_per_slot: int = 5,
    share_gk: bool | None = None,
    specialist_max_slots: int | None = None,
) -> tuple:
    """Return a list of GK assignments (one per slot) and any warnings.

    GK assignments are made per-period (same GK for both sub-periods).

    ``share_gk`` controls how a *specialist* keeper's time is handled:
      * True  — the keeper splits goal duty (plays alternate periods, rests the
        others while a backup covers) so their total pitch time matches the rest
        of the squad. This is the fair-time default set by the setup form.
      * False — the keeper stays in goal every period (traditional; they play
        more total time than outfielders).
      * None  — legacy heuristic used by bare callers/tests: share only when the
        squad has 10+ players.
    Sharing needs at least one spare player to cover goal while the keeper rests,
    so it is forced off when ``squad_size <= players_per_slot`` (no bench).

    ``specialist_max_slots`` adds a *cross-match* cap for tournaments: when sharing
    is on, the specialist keeps goal only up to this many slots this match (their
    fair share across the day minus what they've already played — see
    ``match_service``), then a backup covers and the keeper rests. Within a single
    match, one goal period alternates within it as before. ``None`` = no cap
    (season / single match) — the legacy within-match alternation is used. Ignored
    when sharing is off (the keeper stays in goal all match by the coach's choice).

    Returns:
        gk_assignments: list of length num_slots
        warnings: list of warning strings
    """
    num_quarters = num_slots // 2
    total_player_slots = num_slots * players_per_slot
    fair_share = total_player_slots // squad_size
    # Max GK quarters one player can take within their fair-share budget.
    # Each GK quarter = 2 slots. Use floor(fair_share / 2) so outfield time is possible.
    max_gk_quarters = max(1, fair_share // 2)

    warnings: list = []
    specialist = next((p for p in players if p.gk_status == GKTier.SPECIALIST), None)

    if specialist is not None:
        if share_gk is None:
            share = squad_size >= 10  # legacy default
        else:
            share = share_gk
        # Can only rest the keeper if a spare player exists to cover goal.
        if squad_size <= players_per_slot:
            share = False
        if not share:
            # Specialist plays every quarter
            gk_per_quarter = [specialist] * num_quarters
        elif specialist_max_slots is not None:
            # Tournament: keeper keeps goal only up to their cross-match budget;
            # a backup covers once it's spent (keeper rests, never plays outfield).
            spec_quarter_budget = specialist_max_slots // 2  # 2 slots per goal period
            other_players = [p for p in players if p is not specialist]
            backup_pool = _ranked_gk_pool(other_players, warnings)
            q_counts: dict = {}
            gk_per_quarter = []
            spec_used = 0
            for _ in range(num_quarters):
                if spec_used < spec_quarter_budget:
                    gk_per_quarter.append(specialist)
                    spec_used += 1
                elif backup_pool:
                    gk = _pick_gk_for_quarter(backup_pool, q_counts, max_gk_quarters)
                    gk_per_quarter.append(gk)
                    q_counts[id(gk)] = q_counts.get(id(gk), 0) + 1
                else:
                    # No backup keeper available — the specialist must cover goal.
                    gk_per_quarter.append(specialist)
                    spec_used += 1
        else:
            # Specialist plays Q1 and Q3 (alternating quarters).
            # Non-specialist GKs cover Q2 and Q4 — spreads GK experience more evenly.
            other_players = [p for p in players if p is not specialist]
            gk_pool = _ranked_gk_pool(other_players, warnings)
            q_counts = {}
            gk_per_quarter = []
            for q in range(num_quarters):
                if q % 2 == 0:  # Q1, Q3
                    gk_per_quarter.append(specialist)
                else:           # Q2, Q4
                    gk = _pick_gk_for_quarter(gk_pool, q_counts, max_gk_quarters)
                    gk_per_quarter.append(gk)
                    q_counts[id(gk)] = q_counts.get(id(gk), 0) + 1
    else:
        gk_pool = _ranked_gk_pool(players, warnings)
        if not gk_pool:
            warnings.append("No GK-capable player available. Manual assignment required.")
            return [None] * num_slots, warnings

        gk_per_quarter = []
        q_counts_: dict = {}
        for _ in range(num_quarters):
            gk = _pick_gk_for_quarter(gk_pool, q_counts_, max_gk_quarters)
            gk_per_quarter.append(gk)
            q_counts_[id(gk)] = q_counts_.get(id(gk), 0) + 1

    # Expand: each quarter produces 2 slots with the same GK
    gk_per_slot = [gk for gk in gk_per_quarter for _ in range(2)]
    return gk_per_slot, warnings


def _pick_gk_for_quarter(gk_pool: list, q_counts: dict, max_quarters: int) -> Player:
    """Pick the best-tier GK who still has budget remaining.

    Within a tier, picks the least-used player (random tiebreak so the same
    player isn't always chosen first). Falls back to least-used overall if all
    players have exhausted their budget.
    """
    # Walk tier-by-tier; within each tier pick the least-used eligible player
    seen_tier = None
    tier_candidates: list = []
    for p in gk_pool:
        tier = p.gk_status
        if tier != seen_tier:
            # Entering a new tier — check if previous tier had eligible candidates
            if tier_candidates:
                break
            seen_tier = tier
            tier_candidates = []
        if q_counts.get(id(p), 0) < max_quarters:
            tier_candidates.append(p)

    if not tier_candidates:
        # All exhausted — pick least-used overall (random tiebreak)
        min_count = min(q_counts.get(id(p), 0) for p in gk_pool)
        tier_candidates = [p for p in gk_pool if q_counts.get(id(p), 0) == min_count]

    # Among candidates, pick least-used; shuffle first so ties are broken randomly
    random.shuffle(tier_candidates)
    return min(tier_candidates, key=lambda p: q_counts.get(id(p), 0))


def _ranked_gk_pool(players: list, warnings: list) -> list:
    """Return all capable non-specialist GK players, best-tier first.

    Never mixes players from different tiers — uses best available tier only
    for the initial pool, but falls back to lower tiers when budget is exceeded.

    Actually returns ALL capable players ordered by tier, so the per-quarter
    picker can fall back tier-by-tier naturally.
    """
    preferred = [p for p in players if p.gk_status == GKTier.PREFERRED]
    can_play = [p for p in players if p.gk_status == GKTier.CAN_PLAY]
    emergency = [p for p in players if p.gk_status == GKTier.EMERGENCY_ONLY]

    if emergency and not preferred and not can_play:
        warnings.append(
            "Warning: Only emergency GK players available "
            "(" + ", ".join(p.name for p in emergency) + "). "
            "Please review the rotation plan."
        )

    # Return in tier order: _pick_gk_for_quarter iterates this list
    return preferred + can_play + emergency
