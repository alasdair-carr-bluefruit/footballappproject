import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.api.deps import (
    SquadAccess,
    get_current_squad,
    get_squad_access,
    owned_player,
    require,
)
from backend.db.database import get_session
from backend.db.models import PlayerDB, SquadDB
from backend.db.repositories import name_clash_message, player_name_clash

router = APIRouter()


# ── Team info ─────────────────────────────────────────────────────────────────

class TeamInfo(BaseModel):
    team_name: str = ""
    team_logo: str = ""  # base64 DataURL


@router.get("/info", response_model=TeamInfo)
def get_team_info(squad: SquadDB = Depends(get_current_squad)) -> TeamInfo:
    return TeamInfo(team_name=squad.team_name, team_logo=squad.team_logo)


@router.put("/info", response_model=TeamInfo)
def update_team_info(
    info: TeamInfo,
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(require("manage_team")),
) -> TeamInfo:
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
    skill_rating: int | None  # None when redacted for an assistant coach (T3.2)
    preferred_positions: list[str] = []
    best_position: str = ""
    shirt_number: int | None = None


def _player_to_read(p: PlayerDB, show_skill: bool = True) -> PlayerRead:
    positions = json.loads(p.preferred_positions) if p.preferred_positions else []
    return PlayerRead(
        id=p.id,  # type: ignore[arg-type]
        name=p.name,
        gk_status=p.gk_status,
        def_restricted=p.def_restricted,
        skill_rating=p.skill_rating if show_skill else None,
        preferred_positions=positions,
        best_position=p.best_position,
        shirt_number=p.shirt_number,
    )


@router.get("/players", response_model=list[PlayerRead])
def list_players(
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(get_squad_access),
) -> list[PlayerRead]:
    squad = access.squad
    # Exclude tournament guest players (source_tournament_id IS NOT NULL)
    players = list(
        session.exec(
            select(PlayerDB).where(
                PlayerDB.squad_id == squad.id,
                PlayerDB.source_tournament_id == None,  # noqa: E711
            )
        ).all()
    )
    # Individual skill ratings are the head coach's private judgement — assistants
    # get null (per-slot pooled totals in the plan stay visible).
    show_skill = access.can("manage_squad")
    return [_player_to_read(p, show_skill) for p in players]


@router.post("/players", response_model=PlayerRead, status_code=201)
def add_player(
    player: PlayerCreate,
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(require("manage_squad")),
) -> PlayerRead:
    player.name = player.name.strip()
    clash = player_name_clash(session, squad.id, player.name)  # type: ignore[arg-type]
    if clash:
        raise HTTPException(status_code=422, detail=name_clash_message(clash, player.name))
    data = player.model_dump()
    data["preferred_positions"] = json.dumps(data["preferred_positions"])
    db_player = PlayerDB(squad_id=squad.id, **data)
    session.add(db_player)
    session.commit()
    session.refresh(db_player)
    return _player_to_read(db_player)


@router.put("/players/{player_id}", response_model=PlayerRead)
def update_player(
    player_id: int,
    player: PlayerCreate,
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(require("manage_squad")),
) -> PlayerRead:
    db_player = owned_player(player_id, squad, session)
    player.name = player.name.strip()
    # Only a *changed* name is checked, so an older squad that already has e.g.
    # "Sam" and "sam" can still edit either player's positions or number.
    if player.name.lower() != db_player.name.strip().lower():
        clash = player_name_clash(session, squad.id, player.name, exclude_id=db_player.id)  # type: ignore[arg-type]
        if clash:
            raise HTTPException(status_code=422, detail=name_clash_message(clash, player.name))
    data = player.model_dump()
    data["preferred_positions"] = json.dumps(data["preferred_positions"])
    for key, val in data.items():
        setattr(db_player, key, val)
    session.add(db_player)
    session.commit()
    session.refresh(db_player)
    return _player_to_read(db_player)


@router.delete("/players/{player_id}", status_code=204)
def delete_player(
    player_id: int,
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(require("manage_squad")),
) -> None:
    db_player = owned_player(player_id, squad, session)
    session.delete(db_player)
    session.commit()
