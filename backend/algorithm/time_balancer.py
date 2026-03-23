"""Playing time balancer.

Ensures each available player gets equal (or near-equal) half-quarter slots.
Max difference between most-played and least-played: 1 slot.

Extra slots priority:
  1. Players who covered non-specialist GK slots get rewarded first
  2. Remaining players share further extra slots in rotation
"""
from __future__ import annotations

from backend.models.player import GKTier, Player


def compute_target_slots(
    players: list,
    total_slots: int,
    non_specialist_gk_players: list,
) -> dict:
    """Return target slot count per player.

    Args:
        players: all available players for this match
        total_slots: total player-slots in the match (e.g. 8 * 5 = 40)
        non_specialist_gk_players: players who will cover GK slots but are not specialists
    """
    n = len(players)
    base = total_slots // n
    remainder = total_slots % n

    priority_order = _extra_slot_priority(players, non_specialist_gk_players)

    targets: dict = {p: base for p in players}
    for i in range(remainder):
        targets[priority_order[i]] += 1

    return targets


def _extra_slot_priority(players: list, non_specialist_gk_players: list) -> list:
    """Return players in priority order for receiving extra slots."""
    priority = [p for p in non_specialist_gk_players if p in players]
    priority += [p for p in players if p not in priority]
    return priority
