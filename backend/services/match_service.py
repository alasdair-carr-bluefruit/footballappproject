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
    GameConfig,
    build_tournament_config,
    season_config,
)
from backend.models.match import Match, Squad
from backend.models.player import GKTier
from backend.models.rotation import Position, RotationPlan, SlotAssignment

# ── Game config ────────────────────────────────────────────────────────────────
#
# ``season_config`` / ``build_tournament_config`` live in ``models.game_config`` so
# both this service and ``db.repositories.match_db_to_domain`` resolve a match's
# period structure through the same code (the generation path and the response
# path must never disagree on ``total_slots``/``period_label``).


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


def _specialist_gk_max_slots(
    m: MatchDB, squad: Squad, prior_slots: dict | None, this_match_player_slots: int,
) -> int | None:
    """Cross-match goal-slot budget for a specialist keeper (tournament only).

    A specialist never plays outfield, so without a cap they'd be in goal for
    every match of the day and pile up far more time than the rest of the squad.
    This spreads their goal time so their running total tracks everyone's fair
    share: at each match we top the keeper up to the squad's fair share *so far*
    (slots played by everyone through this match ÷ squad size). A partial deficit
    rounds up to one full goal period (goal is assigned in 2-slot periods), so the
    keeper always gets at least their share and never sits two matches running.
    The GK selector spends this budget, then a backup covers and the keeper rests.

    Returns ``None`` when this isn't a tournament match or there's no specialist.
    Reactive (looks only at matches already played), so it's correct even though
    tournament matches are generated one at a time as they're added.
    """
    if not m.tournament_id:
        return None
    specialist = next(
        (p for p in squad.available if p.gk_status == GKTier.SPECIALIST), None
    )
    if specialist is None:
        return None
    num_players = len(squad.available)
    if num_players == 0:
        return None
    prior_total = int(sum(prior_slots.values())) if prior_slots else 0
    fair_share_so_far = (prior_total + this_match_player_slots) // num_players
    spec_prior = int(prior_slots.get(specialist, 0)) if prior_slots else 0
    deficit = max(0, fair_share_so_far - spec_prior)
    # Goal is assigned in 2-slot periods; round a partial deficit up to a full one.
    spec_periods = (deficit + 1) // 2
    return spec_periods * 2


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
    specialist_gk_max = None
    if m.tournament_id:
        prior_slots = _prior_slots_map(session, m, players_db, squad)
        must_play = _must_play(session, m, players_db, squad)
        cfg = build_match_config(m)
        specialist_gk_max = _specialist_gk_max_slots(
            m, squad, prior_slots, cfg.total_slots * cfg.players_per_slot,
        )

    plan = generate_rotation(
        squad, match,
        prior_slots=prior_slots,
        previous_match_zero_slot_players=must_play,
        specialist_gk_max_slots=specialist_gk_max,
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
