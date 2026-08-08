"""Direct unit tests for `soft_warnings()` — the coach-facing plan-quality flags.

These are NOT hard constraints: every plan below is legal, and `validate()` is
silent on most of them. What is being pinned here is that the three things a
coach must not scroll past — a player in a position they didn't pick, a long
unbroken bench spell, and a wide game-time gap — are each detected, and that the
boundary cases (exactly at the limit → silent) hold, so the thresholds can't
drift without a test failing.

Deliberately built plans rather than generated ones: the engine's output depends
on the seeded RNG, which would make a threshold test assert on a draw rather than
on the checker.
"""

from backend.algorithm.validator import (
    MAX_BENCH_STREAK,
    MIN_NOTABLE_SPREAD,
    slot_spread_tolerance,
    soft_warnings,
)
from backend.models.player import GKTier, Player
from backend.models.rotation import Position, RotationPlan, SlotAssignment

_POS = [Position.GK, Position.CB, Position.LM, Position.RM, Position.CF]


def _p(name: str, prefs: list[str] | None = None, best: str = "") -> Player:
    return Player(
        name=name,
        gk_status=GKTier.EMERGENCY_ONLY,
        preferred_positions=list(prefs) if prefs is not None else [],
        best_position=best,
    )


def _slot(index: int, five) -> SlotAssignment:
    return SlotAssignment(slot_index=index, lineup=dict(zip(_POS, five)))


def _uniform_plan(five, n: int = 8) -> RotationPlan:
    """n identical slots — everyone plays every slot in the same position."""
    return RotationPlan(slots=[_slot(i, five) for i in range(n)])


def _messages(plan, players, prefix: str, fairness_value: int = 0) -> list[str]:
    return [
        w for w in soft_warnings(plan, players, fairness_value=fairness_value)
        if w.startswith(prefix)
    ]


# ── Baseline ──────────────────────────────────────────────────────────────────

def test_clean_plan_produces_no_warnings():
    """Everyone in a picked position, nobody benched, identical game time."""
    five = [
        _p("Gk", ["GK"]), _p("Def", ["DEF"]), _p("Mid1", ["MID"]),
        _p("Mid2", ["MID"]), _p("Fwd", ["FWD"]),
    ]
    assert soft_warnings(_uniform_plan(five), five) == []


def test_players_with_no_picks_are_never_flagged_out_of_position():
    """An empty preferred_positions list means 'happy anywhere', not 'happy nowhere'."""
    five = [_p(n) for n in ("Gk", "Def", "Mid1", "Mid2", "Fwd")]
    assert _messages(_uniform_plan(five), five, "Out of position") == []


# ── Out of position ───────────────────────────────────────────────────────────

def test_out_of_position_flags_a_player_in_a_type_they_did_not_pick():
    five = [
        _p("Gk", ["GK"]), _p("Def", ["DEF"]), _p("Mid1", ["MID"]),
        _p("Mid2", ["MID"]), _p("Striker", ["FWD"]),
    ]
    # Swap the striker into a DEF slot for the whole match.
    five[1], five[4] = five[4], five[1]
    warnings = _messages(_uniform_plan(five), five, "Out of position")

    assert any("Striker" in w and "DEF" in w for w in warnings)


def test_out_of_position_counts_slots_and_aggregates_per_position_type():
    """One line per player+position, not one per slot — a squeezed squad would
    otherwise produce dozens of near-identical lines."""
    fwd = _p("Striker", ["FWD"])
    others = [_p("Gk", ["GK"]), _p("Mid1", ["MID"]), _p("Mid2", ["MID"]), _p("Fwd", ["FWD"])]
    # Striker at CB in 3 of 4 slots, in their own FWD slot for the 4th.
    slots = [
        _slot(0, [others[0], fwd, others[1], others[2], others[3]]),
        _slot(1, [others[0], fwd, others[1], others[2], others[3]]),
        _slot(2, [others[0], fwd, others[1], others[2], others[3]]),
        _slot(3, [others[0], others[3], others[1], others[2], fwd]),
    ]
    players = [fwd, *others]
    warnings = _messages(RotationPlan(slots=slots), players, "Out of position")
    striker_lines = [w for w in warnings if "Striker" in w]

    assert len(striker_lines) == 1
    assert "3 slots" in striker_lines[0]


def test_out_of_position_flags_an_unpicked_keeper():
    """Being put in goal when you didn't pick GK is the classic 'stuck in goal'
    complaint — it must flag, not be treated as a free position."""
    outfielder = _p("Winger", ["FWD"])
    rest = [_p("Def", ["DEF"]), _p("Mid1", ["MID"]), _p("Mid2", ["MID"]), _p("Fwd", ["FWD"])]
    plan = _uniform_plan([outfielder, *rest])
    warnings = _messages(plan, [outfielder, *rest], "Out of position")

    assert any("Winger" in w and "GK" in w for w in warnings)


# ── Long bench spell ──────────────────────────────────────────────────────────

def _plan_with_bench_streak(streak: int, total: int = 8):
    """`Sub` starts on the bench for `streak` slots, then plays the rest.

    `Starter` covers those slots and so picks up a long spell of their own —
    tests assert per-player rather than on the whole list.
    """
    sub = _p("Sub", ["MID"])
    starter = _p("Starter", ["MID"])
    rest = [_p("Gk", ["GK"]), _p("Def", ["DEF"]), _p("Mid2", ["MID"]), _p("Fwd", ["FWD"])]
    slots = []
    for i in range(total):
        on = starter if i < streak else sub
        slots.append(_slot(i, [rest[0], rest[1], on, rest[2], rest[3]]))
    return RotationPlan(slots=slots), [sub, starter, *rest]


def _for_player(plan, players, name: str, prefix: str, fairness_value: int = 0) -> list[str]:
    return [w for w in _messages(plan, players, prefix, fairness_value) if name in w]


def test_bench_streak_at_the_limit_is_silent():
    plan, players = _plan_with_bench_streak(MAX_BENCH_STREAK)
    assert _for_player(plan, players, "Sub", "Long bench spell") == []


def test_bench_streak_one_over_the_limit_flags():
    plan, players = _plan_with_bench_streak(MAX_BENCH_STREAK + 1)
    warnings = _for_player(plan, players, "Sub", "Long bench spell")

    assert len(warnings) == 1
    assert f"{MAX_BENCH_STREAK + 1} slots in a row" in warnings[0]


def test_bench_streak_reports_the_longest_run_not_the_total_benched():
    """Two short spells must not add up into a false long one."""
    sub = _p("Sub", ["MID"])
    starter = _p("Starter", ["MID"])
    rest = [_p("Gk", ["GK"]), _p("Def", ["DEF"]), _p("Mid2", ["MID"]), _p("Fwd", ["FWD"])]
    # Benched for slots 0-1 and 4-5 — four slots off, but never more than two
    # consecutively, which is ordinary rotation.
    off = {0, 1, 4, 5}
    slots = [
        _slot(i, [rest[0], rest[1], starter if i in off else sub, rest[2], rest[3]])
        for i in range(8)
    ]
    players = [sub, starter, *rest]

    assert _messages(RotationPlan(slots=slots), players, "Long bench spell") == []


# ── Uneven game time ──────────────────────────────────────────────────────────

def _plan_from_counts(counts: dict[str, int], total: int = 8):
    """Build a plan in which each named player plays exactly `counts[name]` slots.

    Player *i* always occupies position *i*, and plays the first `counts[name]`
    slots. `soft_warnings` never looks at the formation, so an arbitrary-width
    lineup is fine here and lets the spread be set exactly.
    """
    pos_pool = [
        Position.GK, Position.CB, Position.CB2, Position.LB, Position.RB,
        Position.LM, Position.CM, Position.RM, Position.CF,
    ]
    assert len(counts) <= len(pos_pool), "add more positions to pos_pool"
    players = [_p(name) for name in counts]
    slots = []
    for i in range(total):
        lineup = {
            pos_pool[j]: p
            for j, p in enumerate(players)
            if i < counts[p.name]
        }
        slots.append(SlotAssignment(slot_index=i, lineup=lineup))
    return RotationPlan(slots=slots), players


def _spread_plan(gap: int, total: int = 8):
    """Four players on every slot, one player `gap` slots short of them."""
    counts = {"Ever1": total, "Ever2": total, "Ever3": total, "Short": total - gap}
    return _plan_from_counts(counts, total)


# ── the tolerance curve itself ────────────────────────────────────────────────

def test_equal_play_tolerates_only_a_one_slot_gap():
    """On the equal end of the slider any real gap is unintended."""
    assert slot_spread_tolerance(0, 8) == 1
    assert slot_spread_tolerance(15, 8) == 1


def test_tolerance_widens_towards_competitive():
    """A gap is the point of the competitive setting, so the bar rises with it."""
    assert slot_spread_tolerance(16, 8) == 2
    assert slot_spread_tolerance(100, 8) == 3


def test_tolerance_scales_with_match_length():
    """Two slots is a quarter of an 8-slot match but half of a 4-slot 9v9, so a
    fixed number would be far stricter on the short format."""
    assert slot_spread_tolerance(100, 4) == 2
    assert slot_spread_tolerance(100, 8) == 3


def test_tolerance_clamps_out_of_range_slider_values():
    assert slot_spread_tolerance(-10, 8) == 1
    assert slot_spread_tolerance(999, 8) == slot_spread_tolerance(100, 8)


# ── what gets reported, and in which tone ─────────────────────────────────────

def test_gap_below_the_notable_floor_is_silent_on_any_setting():
    plan, players = _spread_plan(MIN_NOTABLE_SPREAD - 1)
    assert _messages(plan, players, "Uneven game time") == []
    assert _messages(plan, players, "Expected game-time gap") == []


def test_equal_play_reports_a_two_slot_gap_as_a_warning():
    """Tolerance is 1 on equal, so a 2-slot gap is more than the coach asked for."""
    plan, players = _spread_plan(2)
    warnings = _messages(plan, players, "Uneven game time", fairness_value=0)

    assert len(warnings) == 1
    assert "2-slot spread" in warnings[0]
    assert "Short" in warnings[0]


def test_competitive_reports_the_same_gap_as_expected_not_as_a_warning():
    """Identical plan, identical gap — only the slider differs. The coach chose
    this, so it is stated as a consequence rather than a telling-off."""
    plan, players = _spread_plan(2)

    assert _messages(plan, players, "Uneven game time", fairness_value=60) == []
    expected = _messages(plan, players, "Expected game-time gap", fairness_value=60)
    assert len(expected) == 1
    assert "2-slot spread" in expected[0]


def test_competitive_still_warns_once_the_gap_exceeds_what_was_asked_for():
    """Competitive widens the bar; it does not remove it."""
    plan, players = _spread_plan(slot_spread_tolerance(60, 8) + 1)
    warnings = _messages(plan, players, "Uneven game time", fairness_value=60)

    assert len(warnings) == 1


def test_slot_spread_names_every_player_on_the_fewest_slots():
    plan, players = _plan_from_counts(
        {"Ever1": 8, "Ever2": 8, "Ann": 5, "Bob": 5}, total=8,
    )
    warnings = _messages(plan, players, "Uneven game time")

    assert len(warnings) == 1
    assert "Ann" in warnings[0] and "Bob" in warnings[0]


def test_slider_does_not_soften_the_bench_or_position_checks():
    """Competitive buys a wider game-time gap, not a child parked on the
    touchline or played somewhere they never picked."""
    plan, players = _plan_with_bench_streak(MAX_BENCH_STREAK + 1)
    for fv in (0, 100):
        assert _for_player(plan, players, "Sub", "Long bench spell", fairness_value=fv)


# ── Separation from hard violations ───────────────────────────────────────────

def test_soft_warnings_never_use_the_violation_wording():
    """These are coaching flags, not rule breaches. 'Violation' is the engine's
    word for a plan that is actually broken, and it must not leak into anything
    a coach could end up reading."""
    plan, players = _spread_plan(4)
    warnings = soft_warnings(plan, players)

    assert warnings
    assert not any("VIOLATION" in w.upper() for w in warnings)
