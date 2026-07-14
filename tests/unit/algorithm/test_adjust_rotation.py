"""Unit tests for adjust_rotation's locking contract.

These pin the two behaviours the Plan-Review tinker relies on:

  * **Local swap** — when every slot is locked, an edit changes ONLY the edited
    slot and leaves every other slot byte-identical. This is what the tinker
    default now does (the frontend sends all slot indices as locked), so a plain
    edit never silently rewrites slots the coach didn't touch.
  * **Following-only recalc** — when slots 0..pivot are locked, the prefix is
    preserved exactly and only the later slots are regenerated. This is what the
    explicit "Recalculate rest of match" button relies on.

adjust_rotation itself was previously uncovered (see the mutation-testing notes);
these guard the lock semantics the feature depends on.
"""

from datetime import date

import pytest

from backend.algorithm.rotation_engine import adjust_rotation, generate_rotation
from backend.models.game_config import get_config
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from tests.conftest import make_player

pytestmark = pytest.mark.unit


def _squad(n: int) -> Squad:
    players = [make_player("Specialist", GKTier.SPECIALIST)]
    for i in range(2, n + 1):
        players.append(make_player(f"P{i}", GKTier.EMERGENCY_ONLY, skill_rating=(i % 5) + 1))
    return Squad(players=players)


def _match() -> Match:
    return Match(date=date(2026, 6, 1), game_config=get_config(5, "1-2-1"))


def _lineup_names(plan):
    return [{k.value: p.name for k, p in s.lineup.items()} for s in plan.slots]


def test_all_locked_edit_changes_only_that_slot():
    match, squad = _match(), _squad(10)
    plan = generate_rotation(squad, match)

    # The "local swap" contract: every slot locked.
    for s in plan.slots:
        s.locked = True
    before = _lineup_names(plan)

    edit_slot = 1
    target_pos = next(k for k in plan.slots[edit_slot].lineup if k.value != "GK")
    on_pitch = {p.name for p in plan.slots[edit_slot].lineup.values()}
    new_player = next(p.name for p in squad.available if p.name not in on_pitch)

    new_plan, _ = adjust_rotation(
        plan, {edit_slot: {target_pos.value: new_player}}, squad, match,
    )
    after = _lineup_names(new_plan)

    for i in range(len(after)):
        if i == edit_slot:
            continue
        assert after[i] == before[i], f"slot {i} changed but should have been untouched"
    assert after[edit_slot][target_pos.value] == new_player


def test_lock_prefix_preserves_prefix_and_regenerates_following():
    match, squad = _match(), _squad(10)
    plan = generate_rotation(squad, match)

    pivot = 3
    for s in plan.slots:
        s.locked = s.slot_index <= pivot
    before = _lineup_names(plan)

    # No edits — this mirrors the "Recalculate rest of match" button (empty edits,
    # prefix locked). Following slots may reflow; the prefix must not.
    new_plan, _ = adjust_rotation(plan, {}, squad, match)
    after = _lineup_names(new_plan)

    for i in range(pivot + 1):
        assert after[i] == before[i], f"locked prefix slot {i} changed"
    # Following slots remain complete, valid lineups.
    for i in range(pivot + 1, len(after)):
        assert len(after[i]) == match.game_config.formation.team_size
