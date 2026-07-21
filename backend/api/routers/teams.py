"""Teams router (`/api/teams`) — multi-team management (T1.1).

One account can own many squads. The session cookie carries only account_id and
`get_current_squad` resolves `account.squad_id` fresh per request, so "the active
team" is just that single column and switching = updating it. These endpoints add
the only genuinely new concept: squad *ownership* (SquadDB.account_id), so we can
list "my teams" and refuse to touch a squad that isn't the caller's.

All endpoints require an authenticated account — the feature is a no-op in auth-off
dev mode (single implicit squad, no owner), where the frontend hides the switcher.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, func, select

from backend.api.deps import get_current_account, owned_squad
from backend.db.database import get_session
from backend.db.models import AccountDB, PlayerDB, SquadDB
from backend.db.repositories import delete_squad_data

router = APIRouter()


class TeamRow(BaseModel):
    id: int
    team_name: str
    team_logo: str
    is_active: bool
    player_count: int


class CreateTeamBody(BaseModel):
    team_name: str = ""
    team_logo: str = ""


def _team_row(squad: SquadDB, active_id: int | None, player_count: int) -> TeamRow:
    return TeamRow(
        id=squad.id,  # type: ignore[arg-type]
        team_name=squad.team_name,
        team_logo=squad.team_logo,
        is_active=(squad.id == active_id),
        player_count=player_count,
    )


def _player_count(session: Session, squad_id: int) -> int:
    return int(
        session.exec(select(func.count(PlayerDB.id)).where(PlayerDB.squad_id == squad_id)).one()
    )


@router.get("", response_model=list[TeamRow])
@router.get("/", response_model=list[TeamRow])
def list_teams(
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> list[TeamRow]:
    """List the account's squads (active one flagged). Guarantees at least the
    active squad even for legacy accounts whose squad predates account_id — adopt
    it if it isn't owned yet, so the list is never empty."""
    squads = list(
        session.exec(
            select(SquadDB).where(SquadDB.account_id == account.id).order_by(SquadDB.id)  # type: ignore[arg-type]
        ).all()
    )
    if account.squad_id not in {s.id for s in squads}:
        active = session.get(SquadDB, account.squad_id)
        if active is not None:
            active.account_id = account.id  # belt-and-braces adoption
            session.add(active)
            session.commit()
            session.refresh(active)
            squads.append(active)
            squads.sort(key=lambda s: s.id or 0)
    return [_team_row(s, account.squad_id, _player_count(session, s.id)) for s in squads]  # type: ignore[arg-type]


@router.post("", response_model=TeamRow)
@router.post("/", response_model=TeamRow)
def create_team(
    body: CreateTeamBody,
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> TeamRow:
    """Create a new squad owned by the account and make it the active team."""
    squad = SquadDB(
        account_id=account.id,
        name="My Squad",
        team_name=(body.team_name or "").strip(),
        team_logo=body.team_logo or "",
    )
    session.add(squad)
    session.commit()
    session.refresh(squad)

    account.squad_id = squad.id  # type: ignore[assignment]
    session.add(account)
    session.commit()
    return _team_row(squad, account.squad_id, 0)


@router.post("/{squad_id}/activate")
def activate_team(
    squad_id: int,
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> dict:
    """Switch the active team (update account.squad_id)."""
    squad = owned_squad(squad_id, account, session)
    account.squad_id = squad.id  # type: ignore[assignment]
    session.add(account)
    session.commit()
    return {"ok": True, "active_squad_id": squad.id}


@router.delete("/{squad_id}")
def delete_team(
    squad_id: int,
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> dict:
    """Remove a team and all its football data. Refuses to delete the account's
    only team. If the removed team was active, re-points to another owned squad."""
    squad = owned_squad(squad_id, account, session)

    owned_count = int(
        session.exec(
            select(func.count(SquadDB.id)).where(SquadDB.account_id == account.id)
        ).one()
    )
    if owned_count <= 1:
        raise HTTPException(status_code=409, detail="Can't remove your only team")

    delete_squad_data(session, squad.id, drop_squad_row=True)  # type: ignore[arg-type]

    if account.squad_id == squad.id:
        next_squad = session.exec(
            select(SquadDB)
            .where(SquadDB.account_id == account.id, SquadDB.id != squad.id)
            .order_by(SquadDB.id)  # type: ignore[arg-type]
        ).first()
        account.squad_id = next_squad.id  # type: ignore[assignment]
        session.add(account)
    session.commit()
    return {"ok": True, "active_squad_id": account.squad_id}
