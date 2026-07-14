from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlmodel import Session, select

from backend.db.database import get_session
from backend.db.models import MatchDB, RotationPlanDB
from backend.db.repositories import (
    build_plan_response,
    create_blank_plan,
    delete_rotation,
    get_available_ids,
    get_goals,
    get_goals_total,
    get_or_create_squad,
    get_players,
    get_removed,
    get_rotation,
    match_db_to_domain,
    set_available_ids,
    set_goals,
    set_removed,
)
from backend.models.game_config import (
    DEFAULT_FORMATIONS,
    PRESET_CONFIGS,
    get_config,
)
from backend.services import analytics, match_service

router = APIRouter()


class MatchCreate(BaseModel):
    date: str  # ISO format e.g. "2026-03-25"
    opponent: str = ""
    quarters: int = 4
    quarter_length_mins: int = 10
    team_size: int = 5
    formation: str = "1-2-1"
    fairness: str = "equal"
    fairness_value: int = 0
    rotation_intensity: int = 50
    home_away: str = "home"


class MatchRead(BaseModel):
    id: int
    date: str
    opponent: str
    quarters: int
    quarter_length_mins: int
    has_rotation: bool
    team_size: int
    formation: str
    fairness: str
    fairness_value: int
    rotation_intensity: int
    home_away: str = "home"
    opponent_goals: int = 0
    status: str = "planned"
    current_slot: int = 0
    our_goals: int = 0  # sum of all player goals (for match list display)


def _match_read(m: MatchDB, has_rotation: bool, our_goals: int = 0) -> MatchRead:
    return MatchRead(
        id=m.id,  # type: ignore[arg-type]
        date=m.date,
        opponent=m.opponent,
        quarters=m.quarters,
        quarter_length_mins=m.quarter_length_mins,
        has_rotation=has_rotation,
        team_size=m.team_size,
        formation=m.formation,
        fairness=m.fairness,
        fairness_value=m.fairness_value,
        rotation_intensity=m.rotation_intensity,
        home_away=m.home_away,
        opponent_goals=m.opponent_goals,
        status=m.status,
        current_slot=m.current_slot,
        our_goals=our_goals,
    )


def _rotation_response(m: MatchDB, slots: list[Any], warnings: list[str]) -> dict[str, Any]:
    try:
        period_label = match_service.build_match_config(m).period_label
    except Exception:
        period_label = "Quarter"
    return {
        "match": {
            "id": m.id,
            "date": m.date,
            "opponent": m.opponent,
            "team_size": m.team_size,
            "formation": m.formation,
            "fairness": m.fairness,
            "rotation_intensity": m.rotation_intensity,
            "period_label": period_label,
            "home_away": m.home_away,
            "opponent_goals": m.opponent_goals,
            "status": m.status,
            "current_slot": m.current_slot,
            "tournament_id": m.tournament_id,
            "tournament_stage": m.tournament_stage or "",
            "match_number": m.match_number,
        },
        "slots": slots,
        "warnings": warnings,
    }


@router.get("/", response_model=list[MatchRead])
def list_matches(session: Session = Depends(get_session)) -> list[MatchRead]:
    squad = get_or_create_squad(session)
    matches = list(
        session.exec(
            select(MatchDB).where(
                MatchDB.squad_id == squad.id,
                MatchDB.tournament_id == None,  # noqa: E711 — season matches only
            ).order_by(MatchDB.date.desc())  # type: ignore[arg-type]
        ).all()
    )
    match_ids = {m.id for m in matches}
    rotations = {
        r.match_id: r
        for r in session.exec(select(RotationPlanDB)).all()
        if r.match_id in match_ids
    }
    result = []
    for m in matches:
        has_rotation = m.id in rotations
        our_goals = get_goals_total(session, m.id) if has_rotation else 0
        result.append(_match_read(m, has_rotation, our_goals))
    return result


@router.post("/", response_model=MatchRead, status_code=201)
def create_match(match: MatchCreate, session: Session = Depends(get_session)) -> MatchRead:
    # Validate team_size + formation combo
    try:
        get_config(match.team_size, match.formation)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=str(e))

    squad = get_or_create_squad(session)
    db_match = MatchDB(squad_id=squad.id, **match.model_dump())
    session.add(db_match)
    session.commit()
    session.refresh(db_match)
    return _match_read(db_match, False)


@router.get("/{match_id}")
def get_match(match_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    if not get_rotation(session, match_id):
        return _rotation_response(db_match, [], [])

    players = get_players(session, db_match.squad_id)
    available_ids = set(get_available_ids(session, match_id))
    if available_ids:
        players = [p for p in players if p.id in available_ids]
    id_to_player = {p.id: p for p in players if p.id is not None}
    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = get_removed(session, match_id)
    # Stored goals keyed by player name so the frontend can restore its goalCounts
    # (without this, reopening a match shows no scorers and a subsequent save
    # would overwrite the real goals with an empty tally).
    response["goals"] = {
        id_to_player[int(pid)].name: count
        for pid, count in get_goals(session, match_id).items()
        if int(pid) in id_to_player and count > 0
    }
    return response


class RotationRequest(BaseModel):
    available_player_ids: list[int] | None = None  # None = all players


@router.post("/{match_id}/rotation")
def generate_match_rotation(
    match_id: int,
    body: RotationRequest | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    try:
        config = match_service.build_match_config(db_match)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    all_players = get_players(session, db_match.squad_id)

    # Filter to available players if specified; fall back to stored list if no body provided
    if body and body.available_player_ids is not None:
        players_db = [p for p in all_players if p.id in set(body.available_player_ids)]
    else:
        stored_ids = get_available_ids(session, match_id)
        if stored_ids:
            players_db = [p for p in all_players if p.id in set(stored_ids)]
        else:
            players_db = all_players

    if len(players_db) < config.players_per_slot:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {config.players_per_slot} players for {db_match.team_size}v{db_match.team_size}",
        )

    match_service.generate_and_save_rotation(session, db_match, players_db)

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = {}
    return response


@router.post("/{match_id}/blank-rotation")
def create_blank_rotation(
    match_id: int,
    body: RotationRequest | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create an empty rotation (all positions unfilled) for manual slot assignment."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    config = match_service.build_match_config(db_match)

    all_players = get_players(session, db_match.squad_id)
    if body and body.available_player_ids is not None:
        avail_set = set(body.available_player_ids)
        players_db = [p for p in all_players if p.id in avail_set]
    else:
        # Re-use previously stored available players (e.g. when switching to manual from pitch view)
        stored_ids = get_available_ids(session, match_id)
        if stored_ids:
            avail_set = set(stored_ids)
            players_db = [p for p in all_players if p.id in avail_set]
        else:
            players_db = all_players

    num_slots = config.total_slots
    create_blank_plan(session, match_id, num_slots, [p.id for p in players_db])

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], [])
    response["removed_players"] = {}
    # All slots locked so adjust_rotation never auto-fills empty slots
    response["locked_slots"] = list(range(num_slots))
    response["manual_mode"] = True
    return response


class AdjustRequest(BaseModel):
    edits: dict[int, dict[str, int]]  # {slot_index: {position_key: player_id}}
    locked_slots: list[int] = []  # additional slot indices to keep locked


@router.post("/{match_id}/adjust")
def adjust_match_rotation(
    match_id: int, body: AdjustRequest, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Apply manual edits and re-generate unlocked slots."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    if not get_rotation(session, match_id):
        raise HTTPException(status_code=400, detail="No rotation exists — generate one first")

    all_players = get_players(session, db_match.squad_id)

    # Load available players for this match
    avail_ids = get_available_ids(session, match_id)
    if avail_ids:
        avail_set = set(avail_ids)
        players_db = [p for p in all_players if p.id in avail_set]
    else:
        players_db = all_players

    match, squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}

    current_plan = match_service.reconstruct_plan(
        session, match_id, squad, id_to_player, extra_locked=body.locked_slots,
    )

    # Convert edits from player IDs to player names
    edits_by_name: dict[int, dict[str, str]] = {}
    for slot_idx_str, pos_map in body.edits.items():
        slot_idx = int(slot_idx_str)
        edits_by_name[slot_idx] = {
            pos_key: id_to_player[pid].name
            for pos_key, pid in pos_map.items()
            if pid in id_to_player
        }

    new_plan, fairness_warnings = match_service.adjust_and_save(
        session, db_match, current_plan, edits_by_name, players_db, squad, match,
    )

    # Re-read for response
    plan_data = build_plan_response(session, match_id, id_to_player)

    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["fairness_warnings"] = fairness_warnings
    # Include locked slot indices in response
    response["locked_slots"] = [s.slot_index for s in new_plan.slots if s.locked]
    return response


class GoalsSave(BaseModel):
    goals: dict[str, int]  # {player_name: goal_count}
    opponent_goals: int = 0


@router.post("/{match_id}/goals")
def save_match_goals(
    match_id: int, body: GoalsSave, session: Session = Depends(get_session),
) -> dict[str, str]:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    if not get_rotation(session, match_id):
        raise HTTPException(status_code=404, detail="No rotation for this match")

    # Convert player names to IDs for storage
    players = get_players(session, db_match.squad_id)
    name_to_id = {p.name: p.id for p in players}
    goals_by_id = {
        str(name_to_id[name]): count
        for name, count in body.goals.items()
        if name in name_to_id and count > 0
    }
    set_goals(session, match_id, goals_by_id)

    # Save opponent goals on the match
    db_match.opponent_goals = body.opponent_goals
    session.add(db_match)
    session.commit()
    return {"status": "saved"}


@router.get("/stats/season")
def get_season_stats(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Aggregate stats across all season matches (excludes tournament matches)."""
    return analytics.season_stats(session)


@router.get("/stats/player/{player_id}")
def get_player_history(player_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Return per-match history for a single player: slots, positions, goals per match."""
    squad = get_or_create_squad(session)
    player_db = next((p for p in get_players(session, squad.id) if p.id == player_id), None)
    if not player_db:
        raise HTTPException(status_code=404, detail="Player not found")
    return analytics.player_history(session, player_db)


@router.post("/{match_id}/start")
def start_match(match_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Mark match as in_progress. Idempotent if already started."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    if db_match.status == "planned":
        db_match.status = "in_progress"
        db_match.current_slot = 0
        session.add(db_match)
        session.commit()
    return {"status": db_match.status, "current_slot": db_match.current_slot}


@router.post("/{match_id}/unstart")
def unstart_match(match_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Revert an accidentally-started match back to planned. Only allowed when current_slot == 0."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    if db_match.status != "in_progress":
        raise HTTPException(status_code=400, detail="Match is not in progress")
    if db_match.current_slot != 0:
        raise HTTPException(status_code=400, detail="Cannot revert — match has already progressed")
    db_match.status = "planned"
    session.add(db_match)
    session.commit()
    return {"status": db_match.status, "current_slot": db_match.current_slot}


class ProgressUpdate(BaseModel):
    current_slot: int
    status: str | None = None  # "in_progress" or "completed"


@router.post("/{match_id}/progress")
def update_progress(
    match_id: int, body: ProgressUpdate, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Persist current slot position and optionally update match status."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    db_match.current_slot = body.current_slot
    if body.status and body.status in ("in_progress", "completed"):
        db_match.status = body.status
    session.add(db_match)
    session.commit()
    return {"status": db_match.status, "current_slot": db_match.current_slot}


class RemovePlayerRequest(BaseModel):
    player_id: int
    from_slot: int  # first slot where player should no longer appear


@router.post("/{match_id}/remove-player")
def remove_player_from_match(
    match_id: int, body: RemovePlayerRequest, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Mark a player unavailable from a given slot onward and re-generate remaining slots."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    if not get_rotation(session, match_id):
        raise HTTPException(status_code=400, detail="No rotation exists")

    # Track removed player
    removed = get_removed(session, match_id)
    removed[str(body.player_id)] = body.from_slot
    set_removed(session, match_id, removed)

    # Remove player from available set
    avail_ids = get_available_ids(session, match_id)
    avail_ids = [pid for pid in avail_ids if pid != body.player_id]
    set_available_ids(session, match_id, avail_ids)

    all_players = get_players(session, db_match.squad_id)
    players_db = [p for p in all_players if p.id in set(avail_ids)]

    match, squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}

    # Reconstruct current plan; lock all slots before from_slot, then re-generate
    current_plan = match_service.reconstruct_plan(
        session, match_id, squad, id_to_player, lock_before=body.from_slot,
    )
    new_plan, fairness_warnings = match_service.adjust_and_save(
        session, db_match, current_plan, {}, players_db, squad, match,
    )

    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = removed
    response["fairness_warnings"] = fairness_warnings
    return response


class ReinstatePlayerRequest(BaseModel):
    player_id: int


@router.post("/{match_id}/reinstate-player")
def reinstate_player_in_match(
    match_id: int, body: ReinstatePlayerRequest, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Restore a removed player and re-generate slots from current match position."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    if not get_rotation(session, match_id):
        raise HTTPException(status_code=400, detail="No rotation exists")

    # Remove from removed list and restore to available
    removed = get_removed(session, match_id)
    removed.pop(str(body.player_id), None)
    set_removed(session, match_id, removed)

    avail_ids = get_available_ids(session, match_id)
    if body.player_id not in avail_ids:
        avail_ids.append(body.player_id)
    set_available_ids(session, match_id, avail_ids)

    all_players = get_players(session, db_match.squad_id)
    players_db = [p for p in all_players if p.id in set(avail_ids)]

    match, squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}

    # Lock all slots up to current_slot, then re-generate the rest
    current_plan = match_service.reconstruct_plan(
        session, match_id, squad, id_to_player, lock_before=db_match.current_slot,
    )
    new_plan, fairness_warnings = match_service.adjust_and_save(
        session, db_match, current_plan, {}, players_db, squad, match,
    )

    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = removed
    response["fairness_warnings"] = fairness_warnings
    return response


@router.delete("/{match_id}", status_code=204)
def delete_match(match_id: int, session: Session = Depends(get_session)) -> None:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    # Explicit ordered DELETEs — bypasses ORM flush ordering issues with PostgreSQL FKs
    delete_rotation(session, match_id)
    session.execute(sql_delete(MatchDB).where(MatchDB.id == match_id))
    session.commit()


# ── Game config reference endpoint ────────────────────────────────────────────

@router.get("/config/game-configs")
def get_game_configs() -> dict[str, Any]:
    """Return available team sizes, formations, and rules for the frontend."""
    configs = {}
    for team_size, formation_map in PRESET_CONFIGS.items():
        default_formation = DEFAULT_FORMATIONS[team_size]
        sample = formation_map[default_formation]
        formations = []
        for notation, cfg in formation_map.items():
            formations.append({
                "notation": notation,
                "positions": cfg.all_positions(),
            })
        configs[str(team_size)] = {
            "team_size": team_size,
            "label": f"{team_size}v{team_size}",
            "default_formation": default_formation,
            "formations": formations,
            "periods": sample.periods,
            "period_label": sample.period_label,
            "mid_period_subs": sample.mid_period_subs,
            "break_subs": sample.break_subs,
        }
    return configs
