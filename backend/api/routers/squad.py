from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.db.database import get_session
from backend.db.models import PlayerDB
from backend.db.repositories import get_or_create_squad

router = APIRouter()


class PlayerCreate(BaseModel):
    name: str
    gk_status: str
    def_restricted: bool = False
    skill_rating: int = 3


class PlayerRead(BaseModel):
    id: int
    name: str
    gk_status: str
    def_restricted: bool
    skill_rating: int


@router.get("/players", response_model=list[PlayerRead])
def list_players(session: Session = Depends(get_session)) -> list[PlayerDB]:
    squad = get_or_create_squad(session)
    return list(session.exec(select(PlayerDB).where(PlayerDB.squad_id == squad.id)).all())


@router.post("/players", response_model=PlayerRead, status_code=201)
def add_player(player: PlayerCreate, session: Session = Depends(get_session)) -> PlayerDB:
    squad = get_or_create_squad(session)
    db_player = PlayerDB(squad_id=squad.id, **player.model_dump())
    session.add(db_player)
    session.commit()
    session.refresh(db_player)
    return db_player


@router.put("/players/{player_id}", response_model=PlayerRead)
def update_player(
    player_id: int, player: PlayerCreate, session: Session = Depends(get_session)
) -> PlayerDB:
    db_player = session.get(PlayerDB, player_id)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")
    for key, val in player.model_dump().items():
        setattr(db_player, key, val)
    session.add(db_player)
    session.commit()
    session.refresh(db_player)
    return db_player


@router.delete("/players/{player_id}", status_code=204)
def delete_player(player_id: int, session: Session = Depends(get_session)) -> None:
    db_player = session.get(PlayerDB, player_id)
    if not db_player:
        raise HTTPException(status_code=404, detail="Player not found")
    session.delete(db_player)
    session.commit()
