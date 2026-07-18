import json
from collections import defaultdict
from datetime import date as date_type
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlmodel import Session, select

from backend.db.models import (
    GoalRecordDB,
    MatchAvailabilityDB,
    MatchDB,
    PlayerDB,
    RemovedPlayerDB,
    RotationPlanDB,
    SlotAssignmentDB,
    SlotDB,
    SquadDB,
    TournamentDB,
)
from backend.models.game_config import build_tournament_config, season_config
from backend.models.match import Match, Squad
from backend.models.player import GKTier, Player
from backend.models.rotation import RotationPlan


def get_or_create_squad(session: Session) -> SquadDB:
    squad = session.exec(select(SquadDB)).first()
    if not squad:
        squad = SquadDB(name="My Squad")
        session.add(squad)
        session.commit()
        session.refresh(squad)
    return squad


def get_players(session: Session, squad_id: int) -> list[PlayerDB]:
    return list(session.exec(select(PlayerDB).where(PlayerDB.squad_id == squad_id)).all())


def player_db_to_domain(p: PlayerDB) -> Player:
    positions = json.loads(p.preferred_positions) if p.preferred_positions else []
    return Player(
        name=p.name,
        gk_status=GKTier(p.gk_status),
        def_restricted=p.def_restricted,
        skill_rating=p.skill_rating,
        preferred_positions=positions,
        best_position=p.best_position or None,
    )


def match_db_to_domain(m: MatchDB, players: list[PlayerDB]) -> tuple[Match, Squad]:
    if m.tournament_id:
        # Tournament matches use a custom config derived from stored period structure
        total_duration = m.quarters * m.quarter_length_mins
        has_halftime = m.quarters > 1
        try:
            config = build_tournament_config(m.team_size, m.formation, total_duration, has_halftime)
        except (ValueError, KeyError):
            config = None
    else:
        # Honour the coach's chosen period count (halves vs quarters) — the same
        # source of truth the API response uses, so generation and metadata agree
        # on total_slots / period_label.
        try:
            config = season_config(
                m.team_size, m.formation, m.quarters, m.quarter_length_mins
            )
        except (KeyError, ValueError):
            config = None
    match = Match(
        date=date_type.fromisoformat(m.date),
        opponent=m.opponent,
        quarters=m.quarters,
        quarter_length_mins=m.quarter_length_mins,
        game_config=config,
        fairness=m.fairness,
        fairness_value=m.fairness_value,
        rotation_intensity=m.rotation_intensity,
        share_gk=bool(m.share_gk),
    )
    squad = Squad(players=[player_db_to_domain(p) for p in players])
    return match, squad


# ── Rotation-plan persistence ──────────────────────────────────────────────────
#
# All access to the RotationPlanDB JSON columns (slots_json, warnings_json,
# goals_json, available_player_ids_json, removed_players_json) goes through the
# helpers below. Routers never touch the JSON directly — this isolates the
# storage format so it can migrate to relational tables without touching callers.


def get_rotation(session: Session, match_id: int) -> RotationPlanDB | None:
    return session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()


def _clear_slots(session: Session, match_id: int) -> None:
    """Delete a match's slot rows and their assignments (assignments first, FK order)."""
    slot_ids = [s.id for s in session.exec(select(SlotDB).where(SlotDB.match_id == match_id)).all()]
    if slot_ids:
        session.execute(sql_delete(SlotAssignmentDB).where(SlotAssignmentDB.slot_id.in_(slot_ids)))
        session.execute(sql_delete(SlotDB).where(SlotDB.match_id == match_id))


def _upsert_anchor(session: Session, match_id: int, warnings: list[str]) -> None:
    """Ensure the RotationPlanDB anchor row exists and holds the plan warnings.

    The relational tables are the source of truth for slots/goals/availability/
    removed players; RotationPlanDB now only anchors existence and stores
    warnings (its JSON blob columns are dormant).
    """
    r = get_rotation(session, match_id)
    if r:
        r.warnings_json = json.dumps(warnings)
        session.add(r)
    else:
        session.add(RotationPlanDB(match_id=match_id, slots_json="[]", warnings_json=json.dumps(warnings)))


def get_plan_slots(session: Session, match_id: int) -> list[dict[str, Any]]:
    """Return the stored slots as [{slot_index, lineup: {pos: player_id}}] (or [])."""
    slots = session.exec(
        select(SlotDB).where(SlotDB.match_id == match_id).order_by(SlotDB.slot_index)  # type: ignore[arg-type]
    ).all()
    if not slots:
        return []
    slot_ids = [s.id for s in slots]
    assignments = session.exec(
        select(SlotAssignmentDB).where(SlotAssignmentDB.slot_id.in_(slot_ids))
    ).all()
    lineups: dict[int, dict[str, int]] = defaultdict(dict)
    for a in assignments:
        lineups[a.slot_id][a.position] = a.player_id
    return [{"slot_index": s.slot_index, "lineup": lineups.get(s.id, {})} for s in slots]


def get_plan_warnings(session: Session, match_id: int) -> list[str]:
    r = get_rotation(session, match_id)
    if not r or not r.warnings_json:
        return []
    return json.loads(r.warnings_json)


def get_available_ids(session: Session, match_id: int) -> list[int]:
    return [
        a.player_id
        for a in session.exec(
            select(MatchAvailabilityDB)
            .where(MatchAvailabilityDB.match_id == match_id)
            .order_by(MatchAvailabilityDB.id)  # type: ignore[arg-type]
        ).all()
    ]


def get_goals(session: Session, match_id: int) -> dict[str, int]:
    """Return {player_id_str: goal_count} (or {})."""
    return {
        str(g.player_id): g.goals
        for g in session.exec(
            select(GoalRecordDB).where(GoalRecordDB.match_id == match_id)
        ).all()
    }


def get_goals_total(session: Session, match_id: int) -> int:
    return sum(get_goals(session, match_id).values())


def get_removed(session: Session, match_id: int) -> dict[str, int]:
    """Return {player_id_str: from_slot_index} of removed players (or {})."""
    return {
        str(r.player_id): r.from_slot
        for r in session.exec(
            select(RemovedPlayerDB).where(RemovedPlayerDB.match_id == match_id)
        ).all()
    }


def set_available_ids(session: Session, match_id: int, ids: list[int]) -> None:
    if not get_rotation(session, match_id):
        return
    session.execute(sql_delete(MatchAvailabilityDB).where(MatchAvailabilityDB.match_id == match_id))
    for pid in dict.fromkeys(ids):  # de-dup, preserve order
        session.add(MatchAvailabilityDB(match_id=match_id, player_id=pid))
    session.commit()


def set_goals(session: Session, match_id: int, goals_by_id: dict[str, int]) -> None:
    if not get_rotation(session, match_id):
        return
    session.execute(sql_delete(GoalRecordDB).where(GoalRecordDB.match_id == match_id))
    for pid_str, count in goals_by_id.items():
        session.add(GoalRecordDB(match_id=match_id, player_id=int(pid_str), goals=count))
    session.commit()


def set_removed(session: Session, match_id: int, removed: dict[str, int]) -> None:
    if not get_rotation(session, match_id):
        return
    session.execute(sql_delete(RemovedPlayerDB).where(RemovedPlayerDB.match_id == match_id))
    for pid_str, from_slot in removed.items():
        session.add(RemovedPlayerDB(match_id=match_id, player_id=int(pid_str), from_slot=from_slot))
    session.commit()


def create_blank_plan(
    session: Session, match_id: int, num_slots: int, available_ids: list[int],
) -> None:
    """Create/replace a rotation plan with empty lineups for manual assignment."""
    _upsert_anchor(session, match_id, [])
    _clear_slots(session, match_id)
    session.flush()  # apply deletes before inserting fresh slot rows
    for i in range(num_slots):
        session.add(SlotDB(match_id=match_id, slot_index=i))
    session.commit()
    set_available_ids(session, match_id, available_ids)


def delete_rotation(session: Session, match_id: int) -> None:
    """Delete all rotation data for a match (slots, assignments, goals, availability,
    removed players, and the anchor row). Does not commit — the caller owns the
    surrounding transaction (matches the routers' explicit ordered-delete pattern)."""
    _clear_slots(session, match_id)
    session.execute(sql_delete(GoalRecordDB).where(GoalRecordDB.match_id == match_id))
    session.execute(sql_delete(MatchAvailabilityDB).where(MatchAvailabilityDB.match_id == match_id))
    session.execute(sql_delete(RemovedPlayerDB).where(RemovedPlayerDB.match_id == match_id))
    session.execute(sql_delete(RotationPlanDB).where(RotationPlanDB.match_id == match_id))


def get_prior_tournament_slots(
    session: Session, tournament_id: int, exclude_match_id: int, players_db: list[PlayerDB],
) -> dict[str, int]:
    """Return {player_name: slots_played} across all OTHER matches in the tournament.

    Feeds cross-match cumulative fairness (prior_slots in the rotation engine).
    """
    id_to_name = {p.id: p.name for p in players_db if p.id is not None}
    prior_counts: dict = defaultdict(int)

    prev_matches = session.exec(
        select(MatchDB).where(
            MatchDB.tournament_id == tournament_id,
            MatchDB.id != exclude_match_id,
        )
    ).all()

    for prev_m in prev_matches:
        for slot_data in get_plan_slots(session, prev_m.id):
            for pid in slot_data["lineup"].values():
                if pid in id_to_name:
                    prior_counts[id_to_name[pid]] += 1

    return dict(prior_counts)


def get_previous_match_zero_slot_players(
    session: Session,
    tournament_id: int,
    current_match_number: int | None,
    players_db: list[PlayerDB],
) -> set[str]:
    """Return names of players who were available but got zero slots in the
    immediately preceding tournament match (consecutive sit-out constraint input)."""
    if not current_match_number or current_match_number <= 1:
        return set()

    prev_m = session.exec(
        select(MatchDB).where(
            MatchDB.tournament_id == tournament_id,
            MatchDB.match_number == current_match_number - 1,
        )
    ).first()
    if not prev_m:
        return set()

    id_to_name = {p.id: p.name for p in players_db if p.id is not None}
    available_ids = get_available_ids(session, prev_m.id)
    played_ids: set = set()
    for slot_data in get_plan_slots(session, prev_m.id):
        played_ids.update(slot_data["lineup"].values())

    return {
        id_to_name[pid] for pid in available_ids
        if pid in id_to_name and pid not in played_ids
    }


def get_must_play_players(
    session: Session,
    tournament_id: int,
    current_match_number: int | None,
    players_db: list[PlayerDB],
    domain_players: list[Player],
) -> set[Player] | None:
    """Domain-level set of players who sat out the entire previous tournament match.

    Returns None (not an empty set) when there are none, matching the rotation
    engine's optional-parameter convention.
    """
    names = get_previous_match_zero_slot_players(
        session, tournament_id, current_match_number, players_db,
    )
    by_name = {p.name: p for p in domain_players}
    result = {by_name[n] for n in names if n in by_name}
    return result or None


def _plan_response_from_data(
    slots_data: list[dict[str, Any]],
    warnings: list[str],
    id_to_player: dict[int, PlayerDB],
) -> dict[str, Any]:
    """Build the API response shape the frontend expects from parsed plan data."""
    all_ids = set(id_to_player.keys())

    def player_dict(p: PlayerDB) -> dict[str, Any]:
        return {
            "id": p.id,
            "name": p.name,
            "gk_status": p.gk_status,
            "def_restricted": p.def_restricted,
        }

    slots = []
    for slot_data in slots_data:
        lineup_ids = set(slot_data["lineup"].values())
        bench_ids = sorted(all_ids - lineup_ids, key=lambda pid: id_to_player[pid].name)

        lineup = {pos: player_dict(id_to_player[pid]) for pos, pid in slot_data["lineup"].items()}
        bench = [player_dict(id_to_player[pid]) for pid in bench_ids]
        skill_total = sum(
            id_to_player[pid].skill_rating
            for pos, pid in slot_data["lineup"].items()
            if pos != "GK"
        )

        slots.append({
            "slot_index": slot_data["slot_index"],
            "lineup": lineup,
            "bench": bench,
            "skill_total": skill_total,
        })

    return {"slots": slots, "warnings": warnings}


def build_plan_response(
    session: Session, match_id: int, id_to_player: dict[int, PlayerDB],
) -> dict[str, Any]:
    """Load the stored plan and render it into the frontend response shape."""
    return _plan_response_from_data(
        get_plan_slots(session, match_id),
        get_plan_warnings(session, match_id),
        id_to_player,
    )


def save_rotation(
    session: Session,
    match_id: int,
    plan: RotationPlan,
    players_db: list[PlayerDB],
) -> None:
    """Persist a generated plan: anchor + warnings on RotationPlanDB, slots and
    lineups in the relational tables (fully replacing any existing plan)."""
    name_to_id = {p.name: p.id for p in players_db if p.id is not None}

    _upsert_anchor(session, match_id, plan.warnings)
    _clear_slots(session, match_id)
    session.flush()  # apply deletes before inserting fresh rows (unique constraints)

    for slot in plan.slots:
        slot_row = SlotDB(match_id=match_id, slot_index=slot.slot_index)
        session.add(slot_row)
        session.flush()  # obtain slot_row.id for its assignments
        for position, player in slot.lineup.items():
            session.add(SlotAssignmentDB(
                slot_id=slot_row.id, position=position.value, player_id=name_to_id[player.name],
            ))
    session.commit()


# ── Tournament position overrides ───────────────────────────────────────────────

def get_position_overrides(t: TournamentDB) -> dict[str, Any]:
    return json.loads(getattr(t, "player_position_overrides_json", None) or "{}")


def set_position_overrides(session: Session, t: TournamentDB, overrides: dict) -> None:
    t.player_position_overrides_json = json.dumps(overrides)
    session.add(t)
    session.commit()
