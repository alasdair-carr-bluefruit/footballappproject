"""Behavioural tests for the stable `generate_rotation` guarantees.

`test_rotation_engine.py` only checks plan *shape* (slot/GK counts). These pin
coach-facing behaviours that mutation testing showed were unasserted: the
squad-size threshold, the competitive-fairness skew (and its 0→60 derivation),
and how rotation intensity widens each player's positional spread.

Each comparison test re-seeds `random` to the same value before both runs, so
the compared setting (fairness / intensity) is the only variable — the result
is a deterministic, RNG-independent contrast rather than a lucky draw.

NB: `preferred_positions` is deliberately NOT asserted as a hard constraint —
despite the CLAUDE.md wording, the position assigner falls back to ignoring it
when the preferred pool empties, so a strict assertion would (correctly) fail.
"""

import random
from datetime import date

from backend.algorithm.rotation_engine import generate_rotation
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import Position, normalize_position
from tests.conftest import make_player


def _match(fairness: str = "equal", fairness_value: int = 0, intensity: int = 50) -> Match:
    m = Match(date=date(2026, 3, 23))
    m.fairness = fairness
    m.fairness_value = fairness_value
    m.rotation_intensity = intensity
    return m


# ── Squad-size threshold ────────────────────────────────────────────────────────

def test_squad_of_exactly_players_per_slot_generates():
    """A squad equal to the on-pitch count (5 for 5v5) is the smallest legal
    squad — it must generate, not raise. Pins `n < players_per_slot` against
    `<=` (which would reject the exact-fit squad)."""
    squad = Squad(players=[make_player("GK", GKTier.PREFERRED),
                           *[make_player(f"P{i}") for i in range(4)]])
    plan = generate_rotation(squad, _match())
    assert len(plan.slots) == 8


# ── Fairness mode & its 0→60 derivation ─────────────────────────────────────────

def _star_weak_squad() -> tuple[Squad, object, object]:
    star = make_player("Star", skill_rating=5)
    weak = make_player("Weak", skill_rating=1)
    squad = Squad(players=[make_player("GK", GKTier.PREFERRED), star, weak,
                           *[make_player(f"P{i}", skill_rating=3) for i in range(8)]])
    return squad, star, weak


def test_equal_fairness_gives_star_and_weak_the_same_time():
    squad, star, weak = _star_weak_squad()
    random.seed(0)
    plan = generate_rotation(squad, _match("equal"))
    assert plan.slot_count_for_player(star) == plan.slot_count_for_player(weak)


def test_competitive_fairness_favours_the_higher_skilled_player():
    """With fairness='competitive' and fairness_value left at 0, the engine must
    derive a competitive weighting (0→60) so the 5-skill player outplays the
    1-skill player. If the derivation didn't fire the value would stay 0 and the
    distribution would be equal — so this pins that branch and the whole
    competitive path."""
    squad, star, weak = _star_weak_squad()
    random.seed(0)
    plan = generate_rotation(squad, _match("competitive", fairness_value=0))
    assert plan.slot_count_for_player(star) > plan.slot_count_for_player(weak)


# ── Rotation intensity widens positional spread ─────────────────────────────────

def _total_position_spread(intensity: int, seed: int = 0) -> int:
    """Sum over players of the number of distinct outfield position types each
    plays. Higher intensity should spread players across more position types."""
    squad = Squad(players=[make_player("GK", GKTier.PREFERRED),
                           *[make_player(f"P{i}", skill_rating=(i % 5) + 1) for i in range(9)]])
    random.seed(seed)
    plan = generate_rotation(squad, _match(intensity=intensity))
    total = 0
    for p in squad.available:
        types = {
            normalize_position(pos)
            for s in plan.slots for pos, pl in s.lineup.items()
            if pl is p and pos != Position.GK
        }
        total += len(types)
    return total


_SPREAD_SEEDS = range(20)


def test_all_rounder_spreads_positions_more_than_specialist():
    """rotation_intensity 100 (all-rounder) must give players more positional
    variety than intensity 0 (specialist). Pins the
    `max_pos_types = max(1, round(1 + (types-1) * intensity / 100))` formula —
    a sign flip, a dropped scaling, or the `max(1→2)` floor collapses this gap.

    Averaged over seeds rather than asserted on one: the gap is large (about 19 vs
    15 on this squad) but not strict on every individual draw, so a single-seed
    assertion passes or fails on the luck of the shuffle rather than on the
    formula. It flipped on seed 0 when GK alternation changed which outfield
    players were available per quarter, while the underlying gap was untouched.
    """
    at_100 = [_total_position_spread(100, s) for s in _SPREAD_SEEDS]
    at_0 = [_total_position_spread(0, s) for s in _SPREAD_SEEDS]
    assert sum(at_100) / len(at_100) > sum(at_0) / len(at_0) + 1


def test_position_spread_ordering_is_seed_independent():
    """The intensity→spread ordering must hold on the large majority of draws —
    the honest form of "independent of the RNG" for a shuffling algorithm."""
    wins = sum(
        _total_position_spread(100, s) > _total_position_spread(0, s)
        for s in _SPREAD_SEEDS
    )
    assert wins >= 0.8 * len(_SPREAD_SEEDS), (
        f"intensity 100 beat intensity 0 in only {wins}/{len(_SPREAD_SEEDS)} draws"
    )
