"""Direct unit tests for `validate()` and its constraint checks.

The sibling `test_validator.py` asserts the *rotation engine's output* obeys the
constraints — it re-implements each check inline and never calls `validate()`.
That left the validator itself (the safety net that flags a bad plan) almost
entirely unexercised: mutation testing showed ~60 surviving mutants across its
seven checks.

These tests drive `validate()` directly. Each builds a deliberately-clean base
plan, perturbs exactly one thing, and asserts the *specific* violation fires —
so an inverted condition, a dropped check, or an off-by-one boundary in any one
checker changes the returned list and fails a test. Boundary cases (exactly at
the limit → no violation) pin the comparison operators.
"""

from backend.algorithm.validator import validate
from backend.models.game_config import DEFAULT_CONFIG, build_tournament_config
from backend.models.player import GKTier
from backend.models.rotation import Position, RotationPlan, SlotAssignment
from tests.conftest import make_player

# 5v5 default lineup order: GK + CB + LM + RM + CF.
_POS = [Position.GK, Position.CB, Position.LM, Position.RM, Position.CF]


def _slot(index: int, five) -> SlotAssignment:
    """One slot from five players in _POS order."""
    return SlotAssignment(slot_index=index, lineup=dict(zip(_POS, five)))


def _uniform_plan(five, n: int = 8) -> RotationPlan:
    """n identical slots — same five players in the same positions throughout.

    This is a *fully valid* DEFAULT_CONFIG plan: GK never changes, no subs,
    everyone plays every slot (equal time), one position type each.
    """
    return RotationPlan(slots=[_slot(i, five) for i in range(n)])


def _base_five():
    return [make_player(n) for n in ("Gk", "Def", "Mid1", "Mid2", "Fwd")]


# ── Baseline: a clean plan must be silent ──────────────────────────────────────

def test_valid_plan_reports_no_violations():
    five = _base_five()
    assert validate(_uniform_plan(five), five, DEFAULT_CONFIG) == []


def test_valid_plan_defaults_config_when_omitted():
    """Omitting config must fall back to DEFAULT_CONFIG, not crash — exercises
    the `cfg = config or DEFAULT_CONFIG` path (checks below read cfg)."""
    five = _base_five()
    assert validate(_uniform_plan(five), five) == []


# ── DEF restriction ────────────────────────────────────────────────────────────

def test_def_restricted_player_in_def_slot_flagged():
    gk, _def, m1, m2, fwd = _base_five()
    restricted = make_player("Def", def_restricted=True)  # sits at CB every slot
    five = [gk, restricted, m1, m2, fwd]
    violations = validate(_uniform_plan(five), five, DEFAULT_CONFIG)
    assert any("DEF restriction" in v for v in violations), violations
    assert any("Def" in v for v in violations)


def test_def_restricted_player_off_def_not_flagged():
    """A restricted player parked in a non-DEF slot must NOT trip the check."""
    gk, _def, m1, m2, fwd = _base_five()
    restricted = make_player("Mid1", def_restricted=True)
    five = [gk, _def, restricted, m2, fwd]  # restricted plays LM (a MID slot)
    assert validate(_uniform_plan(five), five, DEFAULT_CONFIG) == []


# ── GK mid-period change ────────────────────────────────────────────────────────

def test_gk_change_within_period_flagged():
    gk, _def, m1, m2, fwd = _base_five()
    sub_gk = make_player("Gk2")
    # One period (slots 0,1): keeper swaps at the mid-period point.
    plan = RotationPlan(slots=[
        _slot(0, [gk, _def, m1, m2, fwd]),
        _slot(1, [sub_gk, _def, m1, m2, fwd]),
    ])
    violations = validate(plan, [gk, sub_gk, _def, m1, m2, fwd], DEFAULT_CONFIG)
    assert any("GK mid-period change" in v for v in violations), violations
    # The message must name both keepers, in order — pins the getattr(...'name')
    # formatting so a garbled message can't pass as a valid report.
    assert any("Gk -> Gk2" in v for v in violations), violations


def test_gk_change_involving_empty_slot_reported_without_crashing():
    """A slot missing its keeper entirely is malformed but must still be
    *reported* (change to/from None), not crash the validator — pins the
    `getattr(..., 'name', None)` default on both keeper operands."""
    gk, _def, m1, m2, fwd = _base_five()
    no_gk = {Position.CB: _def, Position.LM: m1, Position.RM: m2, Position.CF: fwd}
    plan = RotationPlan(slots=[
        SlotAssignment(slot_index=0, lineup=dict(no_gk)),      # None -> Gk
        _slot(1, [gk, _def, m1, m2, fwd]),
        _slot(2, [gk, _def, m1, m2, fwd]),
        SlotAssignment(slot_index=3, lineup=dict(no_gk)),      # Gk -> None
    ])
    violations = validate(plan, [gk, _def, m1, m2, fwd], DEFAULT_CONFIG)
    assert any("None -> Gk" in v for v in violations), violations
    assert any("Gk -> None" in v for v in violations), violations


def test_gk_constant_within_period_not_flagged():
    gk, _def, m1, m2, fwd = _base_five()
    plan = RotationPlan(slots=[
        _slot(0, [gk, _def, m1, m2, fwd]),
        _slot(1, [gk, _def, m1, m2, fwd]),
    ])
    assert validate(plan, [gk, _def, m1, m2, fwd], DEFAULT_CONFIG) == []


# ── Mid-period sub limit (DEFAULT_CONFIG: max 2) ────────────────────────────────

def _mid_period_change_plan(n_changes: int) -> tuple[RotationPlan, list]:
    gk, _def, m1, m2, fwd = _base_five()
    replacements = [make_player(f"Sub{i}") for i in range(n_changes)]
    outfield = [_def, m1, m2, fwd]
    after = list(outfield)
    for i in range(n_changes):
        after[i] = replacements[i]  # swap out i outfielders (GK unchanged)
    plan = RotationPlan(slots=[
        _slot(0, [gk, *outfield]),
        _slot(1, [gk, *after]),
    ])
    return plan, [gk, *outfield, *replacements]


def test_sub_limit_exceeded_flagged():
    plan, players = _mid_period_change_plan(3)  # 3 > max 2
    violations = validate(plan, players, DEFAULT_CONFIG)
    assert any("sub limit exceeded" in v for v in violations), violations


def test_sub_limit_at_max_not_flagged():
    """Exactly `mid_period_subs` changes is allowed — pins the `>` boundary."""
    plan, players = _mid_period_change_plan(2)  # == max 2
    violations = validate(plan, players, DEFAULT_CONFIG)
    assert not any("sub limit exceeded" in v for v in violations), violations


# ── Playing-time equality (DEFAULT_CONFIG max allowed diff = total_slots//3 = 2) ─

def test_playing_time_inequality_flagged():
    gk, _def, m1, m2, fwd = _base_five()
    extra = make_player("Extra")
    # Fwd sits the first two slots (plays 6); Extra covers them (plays 2). Every
    # other player plays 8 → max 8, min 2, gap 6 > allowed 2. Non-zero min is
    # deliberate: it pins `max_slots - min_slots` (8-2=6) apart from `+` (=10).
    slots = [_slot(0, [gk, _def, m1, m2, extra]),
             _slot(1, [gk, _def, m1, m2, extra])]
    slots += [_slot(i, [gk, _def, m1, m2, fwd]) for i in range(2, 8)]
    players = [gk, _def, m1, m2, fwd, extra]
    violations = validate(RotationPlan(slots=slots), players, DEFAULT_CONFIG)
    assert any("Playing time inequality" in v for v in violations), violations
    assert any("max 8 vs min 2" in v and "difference 6" in v for v in violations), violations


def test_playing_time_allowance_scales_with_total_slots():
    """max_allowed = total_slots // 3, floored at 1. A short (4-slot) tournament
    match allows only a 1-slot gap, so a 2-slot gap must fire — this pins the
    `max(1, ...)` floor, which a wider default config would mask."""
    cfg = build_tournament_config(5, "1-2-1", 20, has_halftime=True)  # total_slots = 4
    assert cfg.total_slots == 4  # guard the premise
    five = _base_five()
    bench = make_player("Benched")  # 0 slots vs 2 → gap 2 > allowed 1
    violations = validate(_uniform_plan(five, n=2), [*five, bench], cfg)
    assert any("Playing time inequality" in v for v in violations), violations


def test_playing_time_within_allowance_not_flagged():
    """A max-vs-min gap equal to the allowance must not fire — pins the
    `max_slots - min_slots > max_allowed` boundary. max_allowed = total_slots//3
    = 2, so a 2-slot plan where the bench player gets 0 gives a gap of exactly 2."""
    five = _base_five()
    bench = make_player("Benched")  # plays 0; everyone else plays 2 → gap == 2
    violations = validate(_uniform_plan(five, n=2), [*five, bench], DEFAULT_CONFIG)
    assert not any("Playing time inequality" in v for v in violations), violations


# ── Specialist never outfield ───────────────────────────────────────────────────

def test_specialist_in_outfield_flagged():
    gk, _def, m1, m2, fwd = _base_five()
    specialist = make_player("Spec", GKTier.SPECIALIST)  # parked at CB
    five = [gk, specialist, m1, m2, fwd]
    violations = validate(RotationPlan(slots=[_slot(0, five)]), five, DEFAULT_CONFIG)
    assert any("Specialist" in v and "outfield" in v for v in violations), violations


def test_specialist_in_goal_not_flagged():
    _gk, _def, m1, m2, fwd = _base_five()
    specialist = make_player("Spec", GKTier.SPECIALIST)  # in goal — legitimate
    five = [specialist, _def, m1, m2, fwd]
    assert validate(RotationPlan(slots=[_slot(0, five)]), five, DEFAULT_CONFIG) == []


# ── Consecutive sit-out ─────────────────────────────────────────────────────────

def test_consecutive_sit_out_flagged():
    five = _base_five()
    benched = make_player("Benched")  # sat out last match, sits out again (0 slots)
    violations = validate(
        _uniform_plan(five), [*five, benched], DEFAULT_CONFIG,
        previous_match_zero_slot_players={benched},
    )
    assert any("Consecutive sit-out" in v for v in violations), violations


def test_consecutive_sit_out_cleared_when_player_features():
    five = _base_five()  # the previously-benched player now plays every slot
    prev_benched = five[4]
    assert validate(
        _uniform_plan(five), five, DEFAULT_CONFIG,
        previous_match_zero_slot_players={prev_benched},
    ) == []


def test_no_previous_match_means_no_sit_out_check():
    """Without a previous-match set the check is a no-op even for a 0-slot player."""
    five = _base_five()
    benched = make_player("Benched")
    violations = validate(
        _uniform_plan(five), [*five, benched], DEFAULT_CONFIG,
        previous_match_zero_slot_players=None,
    )
    assert not any("Consecutive sit-out" in v for v in violations), violations
