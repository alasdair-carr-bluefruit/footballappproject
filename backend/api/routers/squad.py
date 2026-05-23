import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.db.database import get_session
from backend.db.models import PlayerDB, SquadDB
from backend.db.repositories import get_or_create_squad

router = APIRouter()


# ── Team info ─────────────────────────────────────────────────────────────────

class TeamInfo(BaseModel):
    team_name: str = "My Team"
    team_logo: str = ""  # base64 DataURL


@router.get("/info", response_model=TeamInfo)
def get_team_info(session: Session = Depends(get_session)) -> TeamInfo:
    squad = get_or_create_squad(session)
    return TeamInfo(team_name=squad.team_name, team_logo=squad.team_logo)


@router.put("/info", response_model=TeamInfo)
def update_team_info(info: TeamInfo, session: Session = Depends(get_session)) -> TeamInfo:
    squad = get_or_create_squad(session)
    squad.team_name = info.team_name
    squad.team_logo = info.team_logo
    session.add(squad)
    session.commit()
    session.refresh(squad)
    return TeamInfo(team_name=squad.team_name, team_logo=squad.team_logo)


# ── Players ───────────────────────────────────────────────────────────────────

class PlayerCreate(BaseModel):
    name: str
    gk_status: str
    def_restricted: bool = False
    skill_rating: int = 3
    preferred_positions: list[str] = []
    best_position: str = ""
    shirt_number: int | None = None


class PlayerRead(BaseModel):
    id: int
    name: str
    gk_status: str
    def_restricted: bool
    skill_rating: int
    preferred_positions: list[str] = []
    best_position: str = ""
    shirt_number: int | None = None


def _player_to_read(p: PlayerDB) -> PlayerRead:
    positions = json.loads(p.preferred_positions) if p.preferred_positions else []
    return PlayerRead(
        id=p.id,  # type: ignore[arg-type]
        name=p.name,
        gk_status=p.gk_status,
        def_restricted=p.def_restricted,
        skill_rating=p.skill_rating,
        preferred_positions=positions,
        best_position=p.best_position,
        shirt_number=p.shirt_number,
    )


@router.get("/players", response_model=list[PlayerRead])
def list_players(session: Session = Depends(get_session)) -> list[PlayerRead]:
    squad = get_or_create_squad(session)
    players = list(session.exec(select(PlayerDB).where(PlayerDB.squad_id == squad.id)).all())
    return [_player_to_read(p) for p in players]


@router.post("/players", response_model=PlayerRead, status_code=201)
def add_player(player: PlayerCreate, session: Session = Depends(get_session)) -> PlayerRead:
    squad = get_or_create_squad(session)
    data = player.model_dump()
    data["preferred_positions"] = json.dumps(data["preferred_positions"])
    db_player = PlayerDB(squad_id=squad.id, **data)
    session.add(db_player)
    session.commit()
    session.refresh(db_player)
    return _player_to_read(db_player)


@router.put("/players/{player_id}", response_model=PlayerRead)
def update_player(
    player_id: int, player: PlayerCreate, session: Session = Depends(get_session)
) -> PlayerRead:
    db_player = session.get(PlayerDB, player_id)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")
    data = player.model_dump()
    data["preferred_positions"] = json.dumps(data["preferred_positions"])
    for key, val in data.items():
        setattr(db_player, key, val)
    session.add(db_player)
    session.commit()
    session.refresh(db_player)
    return _player_to_read(db_player)


@router.delete("/players/{player_id}", status_code=204)
def delete_player(player_id: int, session: Session = Depends(get_session)) -> None:
    db_player = session.get(PlayerDB, player_id)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")
    session.delete(db_player)
    session.commit()
