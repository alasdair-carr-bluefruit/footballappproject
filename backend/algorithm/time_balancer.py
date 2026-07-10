"""Playing time balancer.

Equal mode: each player gets near-equal slots (max 1 slot difference).
Competitive mode: higher-skilled players get proportionally more time,
but everyone is guaranteed a minimum. The fairness value (0-100) controls
how much skill rating influences the distribution.

Extra slots priority (equal mode):
  1. Players who sat out the entire immediately preceding tournament match
     (hard floor: guaranteed at least 1 slot this match)
  2. Players with the most accumulated deficit from prior tournament matches
  3. Players who covered non-specialist GK slots get rewarded first within deficit tier
  4. Remaining players share further extra slots in rotation
"""
from __future__ import annotations


def compute_target_slots(
    players: list,
    total_slots: int,
    non_specialist_gk_players: list,
    fairness: str = "equal",
    fairness_value: int = 0,
    prior_slots: dict | None = None,
    must_play: set | None = None,
) -> dict:
    """Return target slot count per player.

    Args:
        players: all available players for this match
        total_slots: total player-slots in the match (e.g. 8 * 5 = 40)
        non_specialist_gk_players: players who will cover GK slots but are not specialists
        fairness: "equal" or "competitive"
        fairness_value: 0-100 slider value (only used in competitive mode)
        prior_slots: optional {player: slots_played_in_earlier_tournament_matches}.
            When provided, players who have played more than their fair share so far
            get lower priority for extra slots in this match (cross-match balancing).
        must_play: optional set of players who sat out the entire immediately preceding
            tournament match. These players are guaranteed at least 1 slot this match,
            even if their computed target would otherwise be 0 (consecutive sit-out
            hard constraint).
    """
    if fairness == "competitive" and fairness_value > 15:
        return _competitive_targets(players, total_slots, fairness_value, prior_slots, must_play)
    return _equal_targets(players, total_slots, non_specialist_gk_players, prior_slots, must_play)


def _equal_targets(
    players: list,
    total_slots: int,
    non_specialist_gk_players: list,
    prior_slots: dict | None = None,
    must_play: set | None = None,
) -> dict:
    """Equal distribution: max 1 slot difference between any two players."""
    n = len(players)
    base = total_slots // n
    remainder = total_slots % n

    priority_order = _extra_slot_priority(
        players, non_specialist_gk_players, prior_slots, must_play,
    )

    targets: dict = {p: base for p in players}
    for i in range(remainder):
        targets[priority_order[i]] += 1

    if must_play:
        _enforce_must_play_floor(targets, must_play, players)

    return targets


def _competitive_targets(
    players: list,
    total_slots: int,
    fairness_value: int,
    prior_slots: dict | None = None,
    must_play: set | None = None,
) -> dict:
    """Skill-weighted distribution: higher-skilled players get more time.

    The fairness_value (16-100) controls how aggressively skill is weighted:
    - 16-40: mild weighting, max ~1-2 slot difference
    - 41-70: moderate, best players get noticeably more
    - 71-100: aggressive, star players dominate playing time

    Everyone gets at least floor(total / n) - 1 slots (guaranteed minimum).

    When prior_slots is provided (tournament context), the raw skill-weighted targets
    are adjusted so players who have already played more than their fair share this
    tournament day receive proportionally less time in this match.
    """
    n = len(players)
    if n == 0:
        return {}

    base = total_slots // n
    min_slots = max(1, base - 1)  # guaranteed minimum

    # Weight factor: how much skill matters (0.0 to 1.0)
    weight = (fairness_value - 15) / 85  # normalise 16-100 → 0.0-1.0

    # Compute raw weighted shares based on skill rating
    raw_weights = []
    for p in players:
        equal_share = 1.0
        skill_share = p.skill_rating / 3.0  # normalise around average (3)
        blended = equal_share * (1 - weight) + skill_share * weight
        raw_weights.append(blended)

    # Normalise to sum to total_slots
    total_weight = sum(raw_weights)
    raw_targets = [w / total_weight * total_slots for w in raw_weights]

    # Apply cross-match adjustment: reduce targets for players with prior surplus
    if prior_slots:
        avg_prior = sum(prior_slots.get(p, 0) for p in players) / n
        for i, p in enumerate(players):
            surplus = prior_slots.get(p, 0) - avg_prior
            raw_targets[i] = max(float(min_slots), raw_targets[i] - surplus * 0.5)
        # Renormalise to preserve total
        adj_total = sum(raw_targets)
        if adj_total > 0:
            raw_targets = [t / adj_total * total_slots for t in raw_targets]

    # Round to integers while preserving total
    targets_list = _round_preserving_total(raw_targets, total_slots)

    # Enforce minimum
    targets: dict = {}
    for i, p in enumerate(players):
        targets[p] = max(min_slots, targets_list[i])

    # If enforcing minimums pushed total above target, trim from highest
    current_total = sum(targets.values())
    while current_total > total_slots:
        candidates = [p for p in players if targets[p] > min_slots]
        if not candidates:
            break
        victim = max(candidates, key=lambda p: targets[p])
        targets[victim] -= 1
        current_total -= 1

    if must_play:
        _enforce_must_play_floor(targets, must_play, players)

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


def _extra_slot_priority(
    players: list,
    non_specialist_gk_players: list,
    prior_slots: dict | None = None,
    must_play: set | None = None,
) -> list:
    """Return players in priority order for receiving extra slots.

    Priority: players who sat out the entire previous tournament match first,
    then players with the most accumulated deficit (fewest prior slots relative
    to average), then GK-covering players, then others.
    """
    must_play = must_play or set()

    if prior_slots is not None and len(players) > 0:
        avg_prior = sum(prior_slots.get(p, 0) for p in players) / len(players)
        # Sort: must-play first, then most deficit first (prior < avg), then GK bonus
        gk_set = set(id(p) for p in non_specialist_gk_players if p in players)

        def sort_key(p):
            must_play_bonus = 1 if p in must_play else 0
            deficit = avg_prior - prior_slots.get(p, 0)  # positive = behind on minutes
            gk_bonus = 1 if id(p) in gk_set else 0
            return (-must_play_bonus, -deficit, -gk_bonus)  # must-play first, then most deficit

        return sorted(players, key=sort_key)

    # Original behaviour: must-play players first, then GK players, then others
    priority = [p for p in players if p in must_play]
    priority += [p for p in non_specialist_gk_players if p in players and p not in must_play]
    priority += [p for p in players if p not in priority]
    return priority


def _enforce_must_play_floor(targets: dict, must_play: set, players: list) -> None:
    """Guarantee every must_play player gets at least 1 slot, preserving the total.

    Takes a slot away from whoever currently has the highest target (preferring
    to steal from players not themselves in must_play) so the overall slot total
    for this match is unchanged.
    """
    for p in players:
        if p not in must_play or targets.get(p, 0) >= 1:
            continue
        donors = sorted(
            (q for q in players if q is not p and targets.get(q, 0) > 0),
            key=lambda q: (q in must_play, -targets[q]),
        )
        if not donors:
            continue  # squad too small / slots too few to satisfy without breaking someone else
        donor = donors[0]
        targets[donor] -= 1
        targets[p] = 1
