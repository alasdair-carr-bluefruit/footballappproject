"""Direct unit tests for gk_selector internals (C.4 mutation hardening).

The existing ``test_gk_selector.py`` asserts warnings only loosely
(``any("emergency" in w.lower())``) and never exercises the no-GK edge case or
the per-player GK time budget, so message-text and budget-math mutants
survived. These tests pin the exact warning strings and the
``max_gk_quarters = max(1, fair_share // 2)`` budget.

Known equivalent-mutant tail (deliberately not chased):
- ``fair_share = total // squad`` -> ``/``: only feeds ``max(1, fair_share // 2)``
  and the floor-division there collapses the float back, so it's equivalent.
- ``q_counts.get(id(p), 0)`` default 0 -> 1 and the ``id(None)`` / ``get(None)``
  variants in ``_pick_gk_for_quarter``: reachable only via the all-budget-
  exhausted fallback with an already-populated counter, where the substituted
  default never changes the least-used pick. Combined with the intentional
  ``random.shuffle`` tiebreak these have no stable oracle.
"""
from __future__ import annotations

from backend.algorithm.gk_selector import select_gk_for_slots
from backend.models.player import GKTier
from tests.conftest import make_player


class TestNoGkCapable:
    def test_empty_pool_warns_and_returns_all_none(self):
        # No players at all -> no GK-capable pool.
        assignments, warnings = select_gk_for_slots([], num_slots=8, squad_size=8)
        assert assignments == [None] * 8
        assert warnings == ["No GK-capable player available. Manual assignment required."]


class TestEmergencyWarningText:
    def test_exact_emergency_warning_string(self):
        eve = make_player("Eve", GKTier.EMERGENCY_ONLY)
        sam = make_player("Sam", GKTier.EMERGENCY_ONLY)
        _, warnings = select_gk_for_slots([eve, sam], num_slots=8, squad_size=9)
        assert warnings == [
            "Warning: Only emergency GK players available (Eve, Sam). "
            "Please review the rotation plan."
        ]


class TestGkTimeBudget:
    def test_preferred_capped_at_floor_fair_share_over_two(self):
        # squad 8, 8 slots, 5 per slot -> fair_share = 40 // 8 = 5,
        # max_gk_quarters = max(1, 5 // 2) = 2. A lone preferred GK may cover at
        # most 2 quarters (4 slots); emergency covers the rest. Kills the
        # players_per_slot default (5->6) and the "// 2 -> / 2" mutants, both of
        # which would loosen the cap and let the preferred play a 3rd quarter.
        preferred = make_player("Keeper", GKTier.PREFERRED)
        others = [make_player(f"P{i}", GKTier.EMERGENCY_ONLY) for i in range(7)]
        assignments, _ = select_gk_for_slots(
            [preferred] + others, num_slots=8, squad_size=8
        )
        preferred_quarters = {i // 2 for i, a in enumerate(assignments) if a is preferred}
        assert len(preferred_quarters) == 2
        # and an emergency player must cover the remaining quarters
        assert any(a is not preferred for a in assignments)

    def test_budget_floor_is_at_least_one_quarter(self):
        # Huge squad: fair_share = 40 // 40 = 1, fair_share // 2 = 0, so the
        # max(1, ...) floor keeps it at 1 quarter. Kills the "max(1,..)->max(2,..)"
        # mutant, which would let the preferred play 2 quarters instead of 1.
        preferred = make_player("Keeper", GKTier.PREFERRED)
        others = [make_player(f"P{i}", GKTier.EMERGENCY_ONLY) for i in range(39)]
        assignments, _ = select_gk_for_slots(
            [preferred] + others, num_slots=8, squad_size=40
        )
        preferred_quarters = {i // 2 for i, a in enumerate(assignments) if a is preferred}
        assert len(preferred_quarters) == 1

    def test_non_specialist_quarters_use_distinct_keepers(self):
        # squad >= 10: specialist covers Q1/Q3, two preferred keepers share Q2/Q4.
        # The per-quarter usage counter must be incremented so the least-used
        # keeper is chosen for Q4 — kills the "+ 1 -> - 1" counter mutant, which
        # would drive the count negative and re-pick the same keeper both times.
        specialist = make_player("Spec", GKTier.SPECIALIST)
        pref1 = make_player("Keep1", GKTier.PREFERRED)
        pref2 = make_player("Keep2", GKTier.PREFERRED)
        others = [make_player(f"P{i}", GKTier.EMERGENCY_ONLY) for i in range(7)]
        assignments, _ = select_gk_for_slots(
            [specialist, pref1, pref2] + others, num_slots=8, squad_size=10
        )
        # slot 2 = Q2, slot 6 = Q4 (both non-specialist)
        assert assignments[2] is not specialist
        assert assignments[6] is not specialist
        assert assignments[2] is not assignments[6]


class TestSpecialistBudget:
    """Cross-match goal-slot budget for a specialist (tournament fairness).

    When GK sharing is on, ``specialist_max_slots`` caps how many goal slots the
    specialist takes this match; a backup covers the rest so a specialist keeper
    doesn't play every match of a tournament. Ignored when sharing is off.
    """

    def test_budget_zero_rests_specialist_backup_covers(self):
        spec = make_player("Kai", GKTier.SPECIALIST)
        backup = make_player("Bo", GKTier.PREFERRED)
        others = [make_player(f"P{i}") for i in range(8)]
        assignments, _ = select_gk_for_slots(
            [spec, backup] + others, num_slots=2, squad_size=10,
            players_per_slot=5, share_gk=True, specialist_max_slots=0,
        )
        assert all(a is backup for a in assignments)
        assert spec not in assignments

    def test_budget_covers_period_keeps_specialist(self):
        spec = make_player("Kai", GKTier.SPECIALIST)
        backup = make_player("Bo", GKTier.PREFERRED)
        others = [make_player(f"P{i}") for i in range(8)]
        assignments, _ = select_gk_for_slots(
            [spec, backup] + others, num_slots=2, squad_size=10,
            players_per_slot=5, share_gk=True, specialist_max_slots=2,
        )
        assert all(a is spec for a in assignments)

    def test_zero_budget_but_no_backup_specialist_still_covers(self):
        spec = make_player("Kai", GKTier.SPECIALIST)
        outfield = [make_player(f"P{i}") for i in range(9)]
        assignments, _ = select_gk_for_slots(
            [spec] + outfield, num_slots=2, squad_size=10,
            players_per_slot=5, share_gk=True, specialist_max_slots=0,
        )
        assert all(a is not None for a in assignments)

    def test_share_off_ignores_budget_keeper_plays_all(self):
        # Coach explicitly turned sharing off → keeper stays in goal every period,
        # regardless of the budget.
        spec = make_player("Kai", GKTier.SPECIALIST)
        backup = make_player("Bo", GKTier.PREFERRED)
        others = [make_player(f"P{i}") for i in range(8)]
        assignments, _ = select_gk_for_slots(
            [spec, backup] + others, num_slots=2, squad_size=10,
            players_per_slot=5, share_gk=False, specialist_max_slots=0,
        )
        assert all(a is spec for a in assignments)
