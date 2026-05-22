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


@router.post("/{match_id}/rotation")
def generate_match_rotation(
    match_id: int, session: Session = Depends(get_session)
) -> dict[str, Any]:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    config = get_config(db_match.team_size, db_match.formation)

    players_db = get_players(session, db_match.squad_id)
    if len(players_db) < config.players_per_slot:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {config.players_per_slot} players for {db_match.team_size}v{db_match.team_size}",
        )

    match, squad = match_db_to_domain(db_match, players_db)
    plan = generate_rotation(squad, match)

    save_rotation(session, match_id, plan, players_db)

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    assert rotation is not None
    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)
    return _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])


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
