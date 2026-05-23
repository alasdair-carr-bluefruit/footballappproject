"""Playing time balancer.

Equal mode: each player gets near-equal slots (max 1 slot difference).
Competitive mode: higher-skilled players get proportionally more time,
but everyone is guaranteed a minimum. The fairness value (0-100) controls
how much skill rating influences the distribution.

Extra slots priority (equal mode):
  1. Players who covered non-specialist GK slots get rewarded first
  2. Remaining players share further extra slots in rotation
"""
from __future__ import annotations


def compute_target_slots(
    players: list,
    total_slots: int,
    non_specialist_gk_players: list,
    fairness: str = "equal",
    fairness_value: int = 0,
) -> dict:
    """Return target slot count per player.

    Args:
        players: all available players for this match
        total_slots: total player-slots in the match (e.g. 8 * 5 = 40)
        non_specialist_gk_players: players who will cover GK slots but are not specialists
        fairness: "equal" or "competitive"
        fairness_value: 0-100 slider value (only used in competitive mode)
    """
    if fairness == "competitive" and fairness_value > 15:
        return _competitive_targets(players, total_slots, fairness_value)
    return _equal_targets(players, total_slots, non_specialist_gk_players)


def _equal_targets(
    players: list, total_slots: int, non_specialist_gk_players: list,
) -> dict:
    """Equal distribution: max 1 slot difference between any two players."""
    n = len(players)
    base = total_slots // n
    remainder = total_slots % n

    priority_order = _extra_slot_priority(players, non_specialist_gk_players)

    targets: dict = {p: base for p in players}
    for i in range(remainder):
        targets[priority_order[i]] += 1

    return targets


def _competitive_targets(
    players: list, total_slots: int, fairness_value: int,
) -> dict:
    """Skill-weighted distribution: higher-skilled players get more time.

    The fairness_value (16-100) controls how aggressively skill is weighted:
    - 16-40: mild weighting, max ~1-2 slot difference
    - 41-70: moderate, best players get noticeably more
    - 71-100: aggressive, star players dominate playing time

    Everyone gets at least floor(total / n) - 1 slots (guaranteed minimum).
    """
    n = len(players)
    if n == 0:
        return {}

    base = total_slots // n
    min_slots = max(1, base - 1)  # guaranteed minimum

    # Weight factor: how much skill matters (0.0 to 1.0)
    weight = (fairness_value - 15) / 85  # normalise 16-100 → 0.0-1.0

    # Compute raw weighted shares based on skill rating
    # Blend between equal (all get 1.0) and skill-proportional
    raw_weights = []
    for p in players:
        equal_share = 1.0
        skill_share = p.skill_rating / 3.0  # normalise around average (3)
        blended = equal_share * (1 - weight) + skill_share * weight
        raw_weights.append(blended)

    # Normalise to sum to total_slots
    total_weight = sum(raw_weights)
    raw_targets = [w / total_weight * total_slots for w in raw_weights]

    # Round to integers while preserving total
    targets_list = _round_preserving_total(raw_targets, total_slots)

    # Enforce minimum
    targets: dict = {}
    for i, p in enumerate(players):
        targets[p] = max(min_slots, targets_list[i])

    # If enforcing minimums pushed total above target, trim from highest
    current_total = sum(targets.values())
    while current_total > total_slots:
        # Find the player with the most slots who can lose one
        candidates = [p for p in players if targets[p] > min_slots]
        if not candidates:
            break
        victim = max(candidates, key=lambda p: targets[p])
        targets[victim] -= 1
        current_total -= 1

    return targets


def _round_preserving_total(values: list[float], target_total: int) -> list[int]:
    """Round a list of floats to ints such that they sum to target_total."""
    floored = [int(v) for v in values]
    remainders = [(values[i] - floored[i], i) for i in range(len(values))]
    remainders.sort(reverse=True)

    deficit = target_total - sum(floored)
    for j in range(min(deficit, len(remainders))):
        floored[remainders[j][1]] += 1

    return floored


def _extra_slot_priority(players: list, non_specialist_gk_players: list) -> list:
    """Return players in priority order for receiving extra slots."""
    priority = [p for p in non_specialist_gk_players if p in players]
    priority += [p for p in players if p not in priority]
    return priority
