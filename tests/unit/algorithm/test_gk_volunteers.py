"""Who ends up in goal — the volunteers, not whoever happens to be spare.

Reported by a coach testing an 11-player 5-a-side squad: three of his players had
picked GK, yet the plan kept putting a child who hadn't picked it in goal. Two
causes, both pinned here:

* the per-player GK budget is ``floor(fair_share / 2)`` periods, which rounds an
  11-player squad's 3-slot fair share down to ONE period each — three volunteers
  could only cover three of four quarters, so the fourth fell to an emergency-tier
  player. A willing keeper may now take one period over that budget, but only to
  keep a non-volunteer out of goal, and only within the guards below.
* the alternation preference ("not the same keeper as last period") was applied
  across the whole pool, so it outranked tier: a squad with one willing keeper put
  a non-keeper in goal every other period. It now applies within a tier only.
"""
from __future__ import annotations

import random

import pytest

from backend.algorithm.gk_selector import _spread_gk_quarters, select_gk_for_slots
from backend.models.player import GKTier, Player

pytestmark = pytest.mark.unit


def _squad(n_keepers: int, n_others: int, tier: GKTier = GKTier.CAN_PLAY) -> list:
    return [
        *[Player(name=f"K{i}", gk_status=tier) for i in range(n_keepers)],
        *[Player(name=f"P{i}", gk_status=GKTier.EMERGENCY_ONLY) for i in range(n_others)],
    ]


def _tiers(assignments: list) -> list:
    return [p.gk_status for p in assignments if p is not None]


class TestVolunteersCoverGoal:
    @pytest.mark.parametrize("seed", range(10))
    def test_three_volunteers_cover_all_four_quarters(self, seed):
        """The reported case: 11 players, 5v5, three players who picked GK."""
        random.seed(seed)
        players = _squad(3, 8)
        assignments, _ = select_gk_for_slots(players, num_slots=8, squad_size=11)

        assert GKTier.EMERGENCY_ONLY not in _tiers(assignments)

    @pytest.mark.parametrize("seed", range(10))
    def test_one_volunteer_is_not_passed_over_every_other_period(self, seed):
        """A single willing keeper used to lose alternate periods to a non-volunteer
        purely because of the "don't repeat last period's keeper" preference."""
        random.seed(seed)
        players = _squad(1, 10)
        assignments, _ = select_gk_for_slots(players, num_slots=8, squad_size=11)

        keeper_slots = sum(1 for p in assignments if p is not None and p.name == "K0")
        assert keeper_slots >= 4, "the only volunteer should keep at least half the match"

    @pytest.mark.parametrize("seed", range(10))
    def test_no_keeper_is_stretched_past_half_the_match(self, seed):
        """The extra period is a guard against non-volunteers in goal, not licence
        for one child to keep goal all afternoon. With a squad of 8 the lone
        keeper's fair share is 5 slots, so a third period (6 slots) would be
        three-quarters of the match — an emergency-tier player covers instead."""
        random.seed(seed)
        players = [Player(name="Keeper", gk_status=GKTier.PREFERRED), *_squad(0, 7)]
        assignments, _ = select_gk_for_slots(players, num_slots=8, squad_size=8)

        keeper_slots = sum(1 for p in assignments if p is not None and p.name == "Keeper")
        assert keeper_slots <= 4

    @pytest.mark.parametrize("seed", range(10))
    def test_stretch_keeps_playing_time_within_one_slot(self, seed):
        """A stretched keeper takes 4 of 8 slots against a fair share of 3 — one
        over, which is the tolerance equal time already allows."""
        random.seed(seed)
        players = _squad(3, 8)
        assignments, _ = select_gk_for_slots(players, num_slots=8, squad_size=11)

        fair_share = (8 * 5) // 11
        for keeper in players[:3]:
            slots = sum(1 for p in assignments if p is keeper)
            assert slots <= fair_share + 1


class TestGoalPeriodsAreSpread:
    def test_two_periods_for_one_keeper_alternate(self):
        """A keeper holding two of four periods has spent their whole fair share in
        goal, so the periods they don't keep, they sit. Q1+Q4 leaves them benched
        through the whole middle of the match; only the alternating patterns keep
        their bench spells short."""
        a, b = Player(name="A", gk_status=GKTier.CAN_PLAY), Player(name="B", gk_status=GKTier.CAN_PLAY)

        assert _spread_gk_quarters([a, b, b, a]) == [a, b, a, b]

    def test_already_spread_order_is_left_alone(self):
        a, b = Player(name="A", gk_status=GKTier.CAN_PLAY), Player(name="B", gk_status=GKTier.CAN_PLAY)

        assert _spread_gk_quarters([a, b, a, b]) == [a, b, a, b]

    def test_better_tier_still_keeps_goal_first(self):
        """Spreading must not quietly reorder tier priority: where two arrangements
        bench people equally well, the better-tier keeper takes the earlier period."""
        pref = Player(name="Pref", gk_status=GKTier.PREFERRED)
        emerg = Player(name="Emerg", gk_status=GKTier.EMERGENCY_ONLY)

        assert _spread_gk_quarters([emerg, pref, emerg, pref]) == [pref, emerg, pref, emerg]
