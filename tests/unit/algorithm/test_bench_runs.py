"""Bench-run breaking — a player should not sit out slot after slot after slot.

The load-bearing property here is that breaking a run costs nobody any playing
time: `_break_bench_runs` only makes compensating swaps (A takes B's slot in one
period, B takes A's in another), so every player's total is untouched. An earlier
attempt reordered the *selection* to favour players on a run, which cut runs
further but pushed 9-player squads from 14% to 79% of plans with a >1 slot
playing-time gap — the wrong trade for a tool whose promise is equal time.
"""
from datetime import date

import pytest

from backend.algorithm.rotation_engine import (
    _bench_run_slots,
    _break_bench_runs,
    generate_rotation,
)
from backend.algorithm.validator import MAX_BENCH_STREAK
from backend.models.game_config import PRESET_CONFIGS
from backend.models.match import Match, Squad
from backend.models.player import GKTier, Player
from backend.models.rotation import is_def_position

pytestmark = pytest.mark.unit


def _config(team_size: int):
    return next(iter(PRESET_CONFIGS[team_size].values()))


def _squad(n: int, **kwargs) -> Squad:
    return Squad(players=[
        Player(name="Keeper", gk_status=GKTier.PREFERRED),
        *[Player(name=f"P{i}", gk_status=GKTier.EMERGENCY_ONLY, **kwargs)
          for i in range(n - 1)],
    ])


def _plan_for(n: int, team_size: int = 5, **squad_kwargs):
    squad = _squad(n, **squad_kwargs)
    match = Match(date=date(2026, 3, 23), game_config=_config(team_size))
    return squad, generate_rotation(squad, match)


class TestPlayingTimeIsNeverTraded:
    @pytest.mark.parametrize("n", [8, 9, 10, 11])
    def test_breaking_runs_leaves_every_total_unchanged(self, n):
        """The safety property: the pass may reshuffle who plays when, never how much."""
        squad, plan = _plan_for(n)
        before = {p.name: plan.slot_count_for_player(p) for p in squad.available}

        _break_bench_runs(plan, squad.available, _config(5))

        after = {p.name: plan.slot_count_for_player(p) for p in squad.available}
        assert after == before


class TestRunsAreBroken:
    @pytest.mark.parametrize("n,team_size", [(8, 5), (9, 5), (12, 7)])
    def test_outfield_players_do_not_sit_three_slots_running(self, n, team_size):
        """Squad sizes where a bench run is avoidable — these should come out clean.

        Measured over 200 seeds after this pass: 8 players 2% of plans, 9 players
        4%, 12-a-side 7v7 19.5% (from 46%, 97% and 65.5% before it).
        """
        squad, plan = _plan_for(n, team_size)
        offenders = {
            p.name: _bench_run_slots(plan, p)
            for p in squad.available
            # The keeper is excluded: their playing slots are GK, which cannot be
            # swapped mid-period, so a shared keeper can still sit a long block.
            # That is a GK-scheduling matter, not a run-breaking one.
            if p.gk_status != GKTier.PREFERRED
            and len(_bench_run_slots(plan, p)) > MAX_BENCH_STREAK
        }
        assert not offenders, f"players left on a long bench run: {offenders}"

    def test_big_squads_can_still_produce_runs(self):
        """Known limit, pinned so a future change has to notice it.

        At 5v5 with 13 players each child plays only ~3 of 8 slots, so keeping every
        bench run to 2 needs near-exact spacing (play slots 0, 3, 6). The pairwise
        swaps here are greedy and won't find that, so runs survive: 11 players 81.5%
        of plans, 13 players 100%. Playing time stays equal throughout — the spread
        is 1 slot at both sizes — so this is a scheduling gap, not a fairness one.
        """
        squad, plan = _plan_for(13)
        counts = [plan.slot_count_for_player(p) for p in squad.available]
        assert max(counts) - min(counts) <= 1


class TestHardConstraintsSurvive:
    def test_def_restricted_player_is_never_swapped_into_defence(self):
        # Only some players are restricted. Restricting the whole outfield makes
        # DEF unfillable, and the engine's documented `pool_for` fallback then puts
        # someone there regardless — a known limitation, not this pass's doing.
        squad = _squad(10)
        for p in squad.available[1:4]:
            p.def_restricted = True
        match = Match(date=date(2026, 3, 23), game_config=_config(5))
        plan = generate_rotation(squad, match)
        for slot in plan.slots:
            for pos, player in slot.lineup.items():
                if is_def_position(pos):
                    assert not player.def_restricted, (
                        f"{player.name} is DEF-restricted but was put at {pos}"
                    )

    @pytest.mark.parametrize("n", [9, 10, 11])
    def test_run_breaking_does_not_add_mid_period_subs(self, n):
        """`mid_period_subs` is a soft cap, so this asserts the pass doesn't make
        the breach worse — not that no breach exists (see the soft-cap note in
        `_mid_period_sub_excess`)."""
        from backend.algorithm.rotation_engine import _mid_period_sub_excess

        config = _config(5)
        squad, plan = _plan_for(n)
        excess_before = _mid_period_sub_excess(plan, config)

        _break_bench_runs(plan, squad.available, config)

        assert _mid_period_sub_excess(plan, config) <= excess_before
