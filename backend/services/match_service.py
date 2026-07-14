"""Match rotation orchestration (Phase C.5).

The mechanics here are shared by both season matches and tournament matches —
the only difference is the game config and the cross-match inputs (prior slots
and the must-play floor), both keyed off ``db_match.tournament_id``. Tournament
*setup* (period structure, fairness, guests, position overrides) lives in
``tournament_service``; this module is purely about generating, adjusting and
reconstructing a single match's rotation.
"""
from __future__ import annotations

from sqlmodel import Session

from backend.algorithm.rotation_engine import adjust_rotation, generate_rotation
from backend.db.models import MatchDB, PlayerDB
from backend.db.repositories import (
    get_must_play_players,
    get_plan_slots,
    get_prior_tournament_slots,
    match_db_to_domain,
    save_rotation,
    set_available_ids,
)
from backend.models.game_config import (
    Formation,
    GameConfig,
    build_tournament_config,
    get_config,
)
from backend.models.match import Match, Squad
from backend.models.rotation import Position, RotationPlan, SlotAssignment


# ── Game config ────────────────────────────────────────────────────────────────

def season_config(
    team_size: int, formation: str, quarters: int, quarter_length_mins: int,
) -> GameConfig:
    """Build a GameConfig for a season match, honouring the stored period structure."""
    try:
        preset = get_config(team_size, formation)
    except KeyError:
        preset = None

    if preset and quarters == preset.periods:
        return preset  # matches the preset exactly — nothing to override

    # Build a custom config with the user's chosen period count
    period_label = "Half" if quarters == 2 else "Quarter"
    break_subs = None if quarters == 2 else (preset.break_subs if preset else 5)
    mid_subs = preset.mid_period_subs if preset else 2
    return GameConfig(
        team_size=team_size,
        formation=Formation.parse(formation),
        periods=quarters,
        period_length_mins=quarter_length_mins,
        mid_period_subs=mid_subs,
        break_subs=break_subs,
        period_label=period_label,
    )


def build_match_config(m: MatchDB) -> GameConfig:
    """Return the GameConfig for a match — tournament or season.

    May raise ``KeyError``/``ValueError`` for an unknown team-size/formation
    combo; callers translate that to an HTTP 422.
    """
    if m.tournament_id:
        total_duration = m.quarters * m.quarter_length_mins
        return build_tournament_config(m.team_size, m.formation, total_duration, m.quarters > 1)
    return season_config(m.team_size, m.formation, m.quarters, m.quarter_length_mins)


# ── Cross-match (tournament) inputs ──────────────────────────────────────────────

def _prior_slots_map(
    session: Session, m: MatchDB, players_db: list[PlayerDB], squad: Squad,
) -> dict | None:
    """Map cumulative prior-match slot counts onto domain players (tournament only)."""
    prior_by_name = get_prior_tournament_slots(session, m.tournament_id, m.id, players_db)
    if not prior_by_name:
        return None
    player_name_map = {p.name: p for p in squad.available}
    return {
        player_name_map[name]: count
        for name, count in prior_by_name.items()
        if name in player_name_map
    }


def _must_play(
    session: Session, m: MatchDB, players_db: list[PlayerDB], squad: Squad,
) -> set | None:
    """Players who sat out the whole previous tournament match (consecutive sit-out floor)."""
    return get_must_play_players(
        session, m.tournament_id, m.match_number, players_db, squad.available,
    )


# ── Rotation generation / adjustment ─────────────────────────────────────────────

def generate_and_save_rotation(
    session: Session, m: MatchDB, players_db: list[PlayerDB],
) -> None:
    """Generate a fresh rotation for a match and persist it (plan + availability).

    For tournament matches this also feeds cross-match cumulative fairness
    (prior slots) and the consecutive sit-out floor (must-play players).
    """
    match, squad = match_db_to_domain(m, players_db)

    prior_slots = None
    must_play = None
    if m.tournament_id:
        prior_slots = _prior_slots_map(session, m, players_db, squad)
        must_play = _must_play(session, m, players_db, squad)

    plan = generate_rotation(
        squad, match,
        prior_slots=prior_slots,
        previous_match_zero_slot_players=must_play,
    )
    save_rotation(session, m.id, plan, players_db)
    set_available_ids(session, m.id, [p.id for p in players_db])


def reconstruct_plan(
    session: Session,
    match_id: int,
    squad: Squad,
    id_to_player: dict[int, PlayerDB],
    *,
    lock_before: int | None = None,
    extra_locked: list[int] | None = None,
) -> RotationPlan:
    """Rebuild the stored plan as domain objects, marking the right slots locked.

    ``lock_before`` locks every slot with index < the value (used by
    remove/reinstate to freeze already-played slots); ``extra_locked`` locks a
    specific set of slot indices (used by manual adjust).
    """
    extra = set(extra_locked or [])
    player_by_name = {p.name: p for p in squad.available}
    slots = []
    for sd in get_plan_slots(session, match_id):
        slot = SlotAssignment(slot_index=sd["slot_index"])
        for pos_key, pid in sd["lineup"].items():
            db_p = id_to_player.get(pid)
            if db_p and db_p.name in player_by_name:
                slot.lineup[Position(pos_key)] = player_by_name[db_p.name]
        if lock_before is not None and sd["slot_index"] < lock_before:
            slot.locked = True
        if sd["slot_index"] in extra:
            slot.locked = True
        slots.append(slot)
    return RotationPlan(slots=slots)


def adjust_and_save(
    session: Session,
    m: MatchDB,
    current_plan: RotationPlan,
    edits_by_name: dict[int, dict[str, str]],
    players_db: list[PlayerDB],
    squad: Squad,
    match: Match,
) -> tuple[RotationPlan, list[str]]:
    """Apply manual edits, re-generate unlocked slots, and persist the result.

    Returns the new plan and any fairness warnings the adjustment produced.
    """
    must_play = _must_play(session, m, players_db, squad) if m.tournament_id else None
    new_plan, fairness_warnings = adjust_rotation(
        current_plan, edits_by_name, squad, match,
        previous_match_zero_slot_players=must_play,
    )
    save_rotation(session, m.id, new_plan, players_db)
    return new_plan, fairness_warnings
