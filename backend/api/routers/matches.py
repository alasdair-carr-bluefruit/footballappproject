import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.algorithm.rotation_engine import generate_rotation
from backend.db.database import get_session
from backend.db.models import MatchDB, RotationPlanDB
from backend.db.repositories import (
    get_or_create_squad,
    get_players,
    match_db_to_domain,
    rotation_plan_from_json,
    save_rotation,
)
from backend.models.game_config import DEFAULT_FORMATIONS, PRESET_CONFIGS, get_config

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


def _match_read(m: MatchDB, has_rotation: bool) -> MatchRead:
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
    )


def _rotation_response(m: MatchDB, slots: list[Any], warnings: list[str]) -> dict[str, Any]:
    try:
        cfg = get_config(m.team_size, m.formation)
        period_label = cfg.period_label
    except KeyError:
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
        },
        "slots": slots,
        "warnings": warnings,
    }


@router.get("/", response_model=list[MatchRead])
def list_matches(session: Session = Depends(get_session)) -> list[MatchRead]:
    squad = get_or_create_squad(session)
    matches = list(
        session.exec(
            select(MatchDB).where(MatchDB.squad_id == squad.id).order_by(MatchDB.date.desc())  # type: ignore[arg-type]
        ).all()
    )
    rotations = {
        r.match_id
        for r in session.exec(select(RotationPlanDB)).all()
        if r.match_id in {m.id for m in matches}
    }
    return [_match_read(m, m.id in rotations) for m in matches]


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

    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if not rotation:
        return _rotation_response(db_match, [], [])

    players = get_players(session, db_match.squad_id)
    id_to_player = {p.id: p for p in players if p.id is not None}
    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)
    return _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])


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

    config = get_config(db_match.team_size, db_match.formation)

    all_players = get_players(session, db_match.squad_id)

    # Filter to available players if specified
    if body and body.available_player_ids is not None:
        available_ids = set(body.available_player_ids)
        players_db = [p for p in all_players if p.id in available_ids]
    else:
        players_db = all_players

    if len(players_db) < config.players_per_slot:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {config.players_per_slot} players for {db_match.team_size}v{db_match.team_size}",
        )

    match, squad = match_db_to_domain(db_match, players_db)
    plan = generate_rotation(squad, match)

    save_rotation(session, match_id, plan, players_db)

    # Store which players were available
    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    assert rotation is not None
    rotation.available_player_ids_json = json.dumps([p.id for p in players_db])
    session.add(rotation)
    session.commit()

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)
    return _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])


class AdjustRequest(BaseModel):
    edits: dict[int, dict[str, int]]  # {slot_index: {position_key: player_id}}
    locked_slots: list[int] = []  # additional slot indices to keep locked


@router.post("/{match_id}/adjust")
def adjust_match_rotation(
    match_id: int, body: AdjustRequest, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Apply manual edits and re-generate unlocked slots."""
    from backend.algorithm.rotation_engine import adjust_rotation

    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if not rotation:
        raise HTTPException(status_code=400, detail="No rotation exists — generate one first")

    all_players = get_players(session, db_match.squad_id)

    # Load available players for this match
    avail_ids = json.loads(rotation.available_player_ids_json)
    if avail_ids:
        avail_set = set(avail_ids)
        players_db = [p for p in all_players if p.id in avail_set]
    else:
        players_db = all_players

    match, squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}

    # Reconstruct current plan as domain objects
    from backend.models.rotation import Position, RotationPlan, SlotAssignment
    slots_data = json.loads(rotation.slots_json)
    domain_players = squad.available
    player_by_name = {p.name: p for p in domain_players}

    current_slots = []
    for sd in slots_data:
        slot = SlotAssignment(slot_index=sd["slot_index"])
        for pos_key, pid in sd["lineup"].items():
            db_p = id_to_player.get(pid)
            if db_p:
                domain_p = player_by_name.get(db_p.name)
                if domain_p:
                    slot.lineup[Position(pos_key)] = domain_p
        # Mark previously locked slots
        if sd["slot_index"] in body.locked_slots:
            slot.locked = True
        current_slots.append(slot)

    current_plan = RotationPlan(slots=current_slots)

    # Convert edits from player IDs to player names
    edits_by_name: dict[int, dict[str, str]] = {}
    for slot_idx_str, pos_map in body.edits.items():
        slot_idx = int(slot_idx_str)
        edits_by_name[slot_idx] = {
            pos_key: id_to_player[pid].name
            for pos_key, pid in pos_map.items()
            if pid in id_to_player
        }

    new_plan, fairness_warnings = adjust_rotation(current_plan, edits_by_name, squad, match)

    # Save updated plan
    save_rotation(session, match_id, new_plan, players_db)

    # Re-read for response
    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    assert rotation is not None
    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)

    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["fairness_warnings"] = fairness_warnings
    # Include locked slot indices in response
    response["locked_slots"] = [s.slot_index for s in new_plan.slots if s.locked]
    return response


class GoalsSave(BaseModel):
    goals: dict[str, int]  # {player_name: goal_count}


@router.post("/{match_id}/goals")
def save_match_goals(
    match_id: int, body: GoalsSave, session: Session = Depends(get_session),
) -> dict[str, str]:
    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if not rotation:
        raise HTTPException(status_code=404, detail="No rotation for this match")

    # Convert player names to IDs for storage
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    players = get_players(session, db_match.squad_id)
    name_to_id = {p.name: p.id for p in players}
    goals_by_id = {
        str(name_to_id[name]): count
        for name, count in body.goals.items()
        if name in name_to_id and count > 0
    }
    rotation.goals_json = json.dumps(goals_by_id)
    session.add(rotation)
    session.commit()
    return {"status": "saved"}


@router.get("/stats/season")
def get_season_stats(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Aggregate stats across all matches: goals, matches available, slots played."""
    squad = get_or_create_squad(session)
    players = get_players(session, squad.id)
    matches = list(
        session.exec(select(MatchDB).where(MatchDB.squad_id == squad.id)).all()
    )
    rotations = {
        r.match_id: r
        for r in session.exec(select(RotationPlanDB)).all()
        if r.match_id in {m.id for m in matches}
    }

    stats: dict[int, dict[str, Any]] = {}
    for p in players:
        stats[p.id] = {  # type: ignore[index]
            "id": p.id,
            "name": p.name,
            "matches_available": 0,
            "slots_played": 0,
            "goals": 0,
        }

    for m in matches:
        r = rotations.get(m.id)
        if not r:
            continue

        # Count available players
        available_ids = json.loads(r.available_player_ids_json) if r.available_player_ids_json != "[]" else []
        if not available_ids:
            # Legacy: assume all players were available
            available_ids = [p.id for p in players]
        for pid in available_ids:
            if pid in stats:
                stats[pid]["matches_available"] += 1

        # Count slots played per player
        slots_data = json.loads(r.slots_json)
        for slot in slots_data:
            for pos, pid in slot["lineup"].items():
                if pid in stats:
                    stats[pid]["slots_played"] += 1

        # Count goals
        goals = json.loads(r.goals_json) if r.goals_json != "{}" else {}
        for pid_str, count in goals.items():
            pid = int(pid_str)
            if pid in stats:
                stats[pid]["goals"] += count

    return sorted(stats.values(), key=lambda s: s["name"])


@router.delete("/{match_id}", status_code=204)
def delete_match(match_id: int, session: Session = Depends(get_session)) -> None:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if rotation:
        session.delete(rotation)
    session.delete(db_match)
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
