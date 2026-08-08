"""Rotation plan validator.

Two separate concerns live here:

* ``validate()`` — HARD constraints. Anything it returns is a rule the engine
  was not supposed to break; callers prefix these with "VIOLATION: ".
* ``soft_warnings()`` — plan-QUALITY flags. The plan is legal but the coach
  should see it before kick-off: a player stuck in a position they didn't pick,
  a long unbroken spell on the bench, or a wide spread in total game time.
  These are informational — they never block a plan, and in competitive mode
  the spread flag is the expected, opted-into cost of the fairness slider.
"""
from __future__ import annotations

from backend.models.game_config import DEFAULT_CONFIG, GameConfig
from backend.models.player import GKTier
from backend.models.rotation import Position, RotationPlan, is_def_position, normalize_position


def validate(
    plan: RotationPlan,
    all_players: list,
    config: GameConfig | None = None,
    previous_match_zero_slot_players: set | None = None,
) -> list:
    """Return list of constraint violations. Empty = valid.

    Args:
        previous_match_zero_slot_players: optional set of players who sat out
            the entire immediately preceding tournament match. Used to flag a
            hard violation if any of them sit out this match too.
    """
    cfg = config or DEFAULT_CONFIG
    violations: list = []
    violations += _check_def_restrictions(plan, all_players)
    violations += _check_position_variety(plan, all_players, cfg)
    violations += _check_gk_mid_period_change(plan)
    violations += _check_mid_period_sub_limit(plan, cfg)
    violations += _check_playing_time_equality(plan, all_players, cfg)
    violations += _check_specialist_never_outfield(plan, all_players)
    violations += _check_consecutive_sit_out(plan, all_players, previous_match_zero_slot_players)
    return violations


# A bench spell longer than this many consecutive slots gets flagged. Two slots
# is one full period off in a quarters match — normal rotation. Three is a kid
# standing on the touchline long enough to notice.
MAX_BENCH_STREAK = 2

# A game-time gap this wide is worth mentioning even when the coach asked for a
# competitive plan — below it, ordinary rotation noise.
MIN_NOTABLE_SPREAD = 2

# The slider value at or below which the coach is asking for equal play. Matches
# the same boundary in `time_balancer.compute_target_slots`.
EQUAL_FAIRNESS_MAX = 15


def slot_spread_tolerance(fairness_value: int, total_slots: int) -> int:
    """Game-time spread (most slots minus fewest) tolerated before it's a warning.

    The fairness slider IS the coach telling us how even they want the match to
    be, so it sets this threshold. On equal, any real gap is a surprise. Towards
    competitive, a gap is the entire point of the setting — warning about it
    every time is how you train someone to ignore a banner.

    Also scales with match length: two slots is a quarter of an 8-slot match but
    half of a 4-slot 9v9, so a fixed number would be far stricter on the short
    format.

        8 slots: equal → 1, competitive → 2, max competitive → 3
        4 slots: equal → 1, competitive → 2

    Deliberately tighter than the hard `_check_playing_time_equality` tolerance:
    that one only fires on a plan that is broken, this on a plan worth a look.
    """
    if fairness_value <= EQUAL_FAIRNESS_MAX:
        return 1
    reach = max(1, total_slots // 3)
    frac = (min(100, fairness_value) - EQUAL_FAIRNESS_MAX) / (100 - EQUAL_FAIRNESS_MAX)
    return 1 + max(1, round(frac * reach))


def soft_warnings(
    plan: RotationPlan,
    all_players: list,
    config: GameConfig | None = None,
    fairness_value: int = 0,
) -> list:
    """Return non-blocking plan-quality warnings. Empty list = nothing to flag.

    Kept separate from `validate()` so hard violations and coaching flags never
    get mixed into one undifferentiated list.

    `fairness_value` is the 0-100 slider position. It widens the game-time gap
    the coach is taken to have asked for, and changes how that gap is reported —
    a gap the coach chose is stated as a consequence, not a warning. It does not
    touch the other two checks: a child in a position they didn't pick, or stood
    on the touchline three slots running, is worth flagging whatever the slider
    says.
    """
    warnings: list = []
    warnings += _warn_out_of_preference(plan, all_players)
    warnings += _warn_bench_streak(plan, all_players)
    warnings += _warn_slot_spread(plan, all_players, fairness_value)
    return warnings


def _warn_out_of_preference(plan: RotationPlan, players: list) -> list:
    """Flag players used in a position type they did not pick.

    `preferred_positions` is a soft constraint — the position assigner falls back
    to any eligible player when a preferred pool empties (see
    `_assign_outfield_positions.pool_for`), so this fires more often in squads
    where everyone picked the same position. Aggregated per player+position type
    rather than per slot, otherwise a squeezed squad produces dozens of lines.
    """
    warnings = []
    for player in players:
        prefs = list(player.preferred_positions or [])
        if not prefs:
            continue  # no picks recorded = happy anywhere
        counts: dict[str, int] = {}
        for slot in plan.slots:
            for pos, p in slot.lineup.items():
                if p is not player:
                    continue
                norm = normalize_position(pos)
                if norm not in prefs:
                    counts[norm] = counts.get(norm, 0) + 1
        for norm, count in sorted(counts.items()):
            warnings.append(
                f"Out of position: {player.name} plays {norm} in {count} "
                f"slot{'s' if count != 1 else ''} but only picked "
                f"{', '.join(prefs)}"
            )
    return warnings


def _warn_bench_streak(plan: RotationPlan, players: list) -> list:
    """Flag any unbroken run of more than MAX_BENCH_STREAK slots on the bench."""
    warnings = []
    total = len(plan.slots)
    for player in players:
        on = [player in slot.players for slot in plan.slots]
        streak = 0
        longest = 0
        start_of_longest = 0
        for i, playing in enumerate(on):
            if playing:
                streak = 0
                continue
            streak += 1
            if streak > longest:
                longest = streak
                start_of_longest = i - streak + 1
        if longest > MAX_BENCH_STREAK:
            warnings.append(
                f"Long bench spell: {player.name} sits out {longest} slots in a "
                f"row (slots {start_of_longest + 1}-{start_of_longest + longest} "
                f"of {total})"
            )
    return warnings


def _warn_slot_spread(plan: RotationPlan, players: list, fairness_value: int = 0) -> list:
    """Report the gap between the most- and least-used players.

    Two outcomes rather than one, because the same gap means different things
    depending on the slider. Over tolerance it's a warning — the plan is more
    uneven than the coach asked for. Within tolerance but still notable, on a
    competitive setting, it's stated as the cost of a choice already made
    ("Expected game-time gap"), so the coach sees who is short without being
    told off for a setting they deliberately chose.
    """
    if not players:
        return []
    counts = {p: plan.slot_count_for_player(p) for p in players}
    most = max(counts.values())
    fewest = min(counts.values())
    spread = most - fewest
    if spread < MIN_NOTABLE_SPREAD:
        return []

    short = sorted(p.name for p, c in counts.items() if c == fewest)
    detail = (
        f"{spread}-slot spread across the squad "
        f"(most {most}, fewest {fewest} — {', '.join(short)})"
    )
    tolerance = slot_spread_tolerance(fairness_value, len(plan.slots))
    if spread > tolerance:
        return [f"Uneven game time: {detail}"]
    return [f"Expected game-time gap: {detail}"]


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


def _check_consecutive_sit_out(
    plan: RotationPlan,
    players: list,
    previous_match_zero_slot_players: set | None,
) -> list:
    if not previous_match_zero_slot_players:
        return []
    violations = []
    for player in players:
        if player in previous_match_zero_slot_players and plan.slot_count_for_player(player) == 0:
            violations.append(
                f"Consecutive sit-out: {player.name} sat out the entire previous "
                f"tournament match and sits out this match too"
            )
    return violations


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
