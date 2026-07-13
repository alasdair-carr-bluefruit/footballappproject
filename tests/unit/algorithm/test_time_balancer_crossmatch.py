"""Cross-match (tournament) fairness tests for the time balancer.

`test_fairness.py` never passes `prior_slots`, so the cross-match cumulative
fairness logic — the heart of tournament mode — was unasserted: `compute_target_slots`
must give players who are *behind on minutes* across earlier matches priority for
this match's extra slots, while a consecutive sit-out (`must_play`) still outranks
raw deficit. These tests pin that ordering with exact target counts.

The time balancer is pure and deterministic (no RNG), so exact-value assertions
are stable without seeding.
"""

from backend.algorithm.time_balancer import compute_target_slots
from tests.conftest import make_player


def _nine():
    return [make_player(f"P{i}") for i in range(9)]


# ── Equal mode: cross-match deficit ordering ────────────────────────────────────

def test_equal_prior_slots_favours_players_behind_on_minutes():
    """9 players, 40 slots → base 4, remainder 4. The 4 extra slots must go to
    the players who have played *least* across the tournament so far; players
    already ahead get base only. Pins the `avg_prior - prior` deficit and the
    sort direction in `_extra_slot_priority`."""
    players = _nine()
    ahead, behind = players[:4], players[4:]
    prior = {p: 10 for p in ahead} | {p: 0 for p in behind}
    targets = compute_target_slots(players, 40, [], fairness="equal", prior_slots=prior)

    assert sum(targets.values()) == 40
    assert all(targets[p] == 4 for p in ahead), [targets[p] for p in ahead]
    assert sum(1 for p in behind if targets[p] == 5) == 4, [targets[p] for p in behind]


def test_equal_prior_slots_must_play_outranks_deficit():
    """A player who is *ahead* on minutes but sat out the previous match
    (`must_play`) must still be pulled up to an extra slot — must_play_bonus is
    the primary sort key, ahead of deficit."""
    players = _nine()
    prior = {players[i]: (10 if i < 4 else 0) for i in range(9)}  # P0..3 ahead
    ahead_but_must_play = players[0]
    targets = compute_target_slots(
        players, 40, [], fairness="equal",
        prior_slots=prior, must_play={ahead_but_must_play},
    )
    assert targets[ahead_but_must_play] == 5, targets[ahead_but_must_play]
    assert sum(targets.values()) == 40


# ── Competitive mode: cross-match surplus reduction ─────────────────────────────

def test_competitive_prior_slots_reduces_time_for_players_ahead():
    """Equal-skill squad so prior minutes are the only differentiator: in
    competitive mode, every player behind on minutes must out-slot every player
    ahead. Pins the surplus adjustment in `_competitive_targets`."""
    players = [make_player(f"P{i}", skill_rating=3) for i in range(9)]
    prior = {players[i]: (10 if i < 4 else 0) for i in range(9)}
    targets = compute_target_slots(
        players, 40, [], fairness="competitive", fairness_value=50, prior_slots=prior,
    )
    assert sum(targets.values()) == 40
    ahead_max = max(targets[players[i]] for i in range(4))
    behind_min = min(targets[players[i]] for i in range(4, 9))
    assert ahead_max < behind_min, (
        f"players ahead ({ahead_max}) should each out-slot players behind ({behind_min})")


# ── Dispatch: equal mode must ignore fairness_value ─────────────────────────────

def test_equal_mode_ignores_fairness_value():
    """Even with a high fairness_value, `fairness='equal'` must distribute evenly
    — pins the `and` in `fairness == "competitive" and fairness_value > 15`
    against `or` (which would skew equal mode)."""
    players = [make_player(f"P{i}", skill_rating=i % 5 + 1) for i in range(10)]
    targets = compute_target_slots(players, 40, [], fairness="equal", fairness_value=90)
    assert all(v == 4 for v in targets.values()), sorted(targets.values())


def test_equal_must_play_gets_extra_slot_without_prior_history():
    """First match of a tournament (no prior_slots): a must_play player must be
    first in line for a remainder slot — pins the non-prior priority branch's
    `p in must_play` ordering. 9 players / 40 slots → base 4, so must_play → 5."""
    players = _nine()
    must = players[8]
    targets = compute_target_slots(players, 40, [], fairness="equal", must_play={must})
    assert targets[must] == 5, targets[must]
    assert sum(targets.values()) == 40


# ── Competitive weighting shape ─────────────────────────────────────────────────

def test_competitive_targets_are_monotonic_in_skill():
    """At a fixed fairness_value, target slots must be non-decreasing in skill
    rating, and the top-rated player must out-slot the lowest. Pins the blend
    `equal*(1-w) + skill*w` against sign/again-factor mutations that would
    invert or flatten the skill gradient."""
    graded = [make_player(f"S{r}", skill_rating=r) for r in (1, 2, 3, 4, 5)]
    fillers = [make_player(f"F{i}", skill_rating=3) for i in range(5)]
    targets = compute_target_slots(
        graded + fillers, 40, [], fairness="competitive", fairness_value=80)
    by_skill = [targets[graded[r - 1]] for r in (1, 2, 3, 4, 5)]
    assert by_skill == sorted(by_skill), by_skill          # non-decreasing in skill
    assert by_skill[-1] > by_skill[0], by_skill            # top clearly beats bottom


def test_competitive_single_player_takes_all_slots():
    """Edge case: one available player in competitive mode gets every slot (not
    an empty dict) — pins the `n == 0` guard against `n == 1`."""
    solo = make_player("Solo")
    targets = compute_target_slots([solo], 8, [], fairness="competitive", fairness_value=80)
    assert targets == {solo: 8}
