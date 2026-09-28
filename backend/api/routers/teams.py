"""Teams router (`/api/teams`) — multi-team management (T1.1) + assistant coaches (T3.2).

One account can belong to many squads, each with a role (`head` | `assistant`, see
`backend/db/memberships.py`). The session cookie carries only account_id and
`get_squad_access` resolves `account.squad_id` fresh per request, so "the active
team" is just that single column and switching = updating it.

Assistant coaches: the head coach mints a one-time `?assist=` link for the active
team and shares it (WhatsApp etc., like invite-a-friend). A signed-in coach accepts
it with POST /join; a brand-new person redeems it via /api/auth/redeem instead,
which creates their account without a team of their own.

All endpoints require an authenticated account (except the invite preview) — the
feature is a no-op in auth-off dev mode (single implicit squad), where the frontend
hides the switcher.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, func, select

from backend.api.deps import get_current_account, headed_squad, owned_squad, require
from backend.auth.tokens import hash_token, is_expired, iso_in, new_token, now_iso
from backend.db.database import get_session
from backend.db.memberships import (
    ASSISTANT,
    HEAD,
    add_membership,
    assistants_of,
    get_membership,
    head_account,
    head_count,
    memberships_for,
    repoint_active_squad,
)
from backend.db.models import AccountDB, InviteDB, PlayerDB, SquadDB, SquadMembershipDB
from backend.db.repositories import delete_squad_data
from backend.settings import INVITE_TTL_DAYS, app_base_url

router = APIRouter()


class TeamRow(BaseModel):
    id: int
    team_name: str
    team_logo: str
    is_active: bool
    player_count: int
    role: str = HEAD  # the caller's role on this team
    head_name: str = ""  # head coach's display name (shown on teams you assist)


class CreateTeamBody(BaseModel):
    team_name: str = ""
    team_logo: str = ""


def _team_row(
    session: Session, squad: SquadDB, active_id: int | None, role: str = HEAD
) -> TeamRow:
    head_name = ""
    if role != HEAD:
        head = head_account(session, squad.id)  # type: ignore[arg-type]
        head_name = head.display_name if head else ""
    return TeamRow(
        id=squad.id,  # type: ignore[arg-type]
        team_name=squad.team_name,
        team_logo=squad.team_logo,
        is_active=(squad.id == active_id),
        player_count=_player_count(session, squad.id),  # type: ignore[arg-type]
        role=role,
        head_name=head_name,
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
    """List every team the account can access (active one flagged, role on each).
    Guarantees at least the active squad even for legacy accounts whose squad
    predates ownership — adopt an unowned active squad as head, so the list is
    never empty."""
    active = session.get(SquadDB, account.squad_id)
    if active is not None and active.account_id is None:
        add_membership(session, active, account.id, HEAD)  # type: ignore[arg-type]  # legacy adoption
    get_membership(session, account.squad_id, account.id)  # type: ignore[arg-type]  # adopts owner rows
    session.commit()

    rows = []
    for m in memberships_for(session, account.id):  # type: ignore[arg-type]
        squad = session.get(SquadDB, m.squad_id)
        if squad is not None:
            rows.append(_team_row(session, squad, account.squad_id, m.role))
    return rows


@router.post("", response_model=TeamRow)
@router.post("/", response_model=TeamRow)
def create_team(
    body: CreateTeamBody,
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> TeamRow:
    """Create a new squad headed by the account and make it the active team."""
    squad = SquadDB(
        name="My Squad",
        team_name=(body.team_name or "").strip(),
        team_logo=body.team_logo or "",
    )
    session.add(squad)
    session.flush()
    add_membership(session, squad, account.id, HEAD)  # type: ignore[arg-type]
    account.squad_id = squad.id  # type: ignore[assignment]
    session.add(account)
    session.commit()
    session.refresh(squad)
    return _team_row(session, squad, account.squad_id)


@router.post("/{squad_id}/activate")
def activate_team(
    squad_id: int,
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> dict:
    """Switch the active team (update account.squad_id). Any role may switch."""
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
    """Remove a team and all its football data (head coach only). Refuses to delete
    the account's only headed team. Assistants simply lose access; anyone whose
    active team it was is re-pointed to another team they can access."""
    squad = headed_squad(squad_id, account, session)
    if head_count(session, account.id) <= 1:  # type: ignore[arg-type]
        raise HTTPException(status_code=409, detail="Can't remove your only team")

    affected_ids = [
        m.account_id
        for m in session.exec(
            select(SquadMembershipDB).where(SquadMembershipDB.squad_id == squad.id)
        ).all()
    ]
    delete_squad_data(session, squad.id, drop_squad_row=True)  # type: ignore[arg-type]
    for acc_id in affected_ids:
        acc = session.get(AccountDB, acc_id)
        if acc is not None and acc.squad_id == squad_id:
            repoint_active_squad(session, acc, exclude_squad_id=squad_id)
    session.commit()
    session.refresh(account)
    return {"ok": True, "active_squad_id": account.squad_id}


# ── Assistant coaches (T3.2) ────────────────────────────────────────────────────


class AssistantRow(BaseModel):
    account_id: int
    display_name: str
    email: str
    since: str


@router.get("/assistants", response_model=list[AssistantRow])
def list_assistants(
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(require("manage_team")),
) -> list[AssistantRow]:
    """The active team's assistant coaches (head coach only)."""
    rows = []
    for m in assistants_of(session, squad.id):  # type: ignore[arg-type]
        acc = session.get(AccountDB, m.account_id)
        if acc is not None:
            rows.append(
                AssistantRow(
                    account_id=acc.id,  # type: ignore[arg-type]
                    display_name=acc.display_name,
                    email=acc.email,
                    since=m.created_at,
                )
            )
    return rows


@router.post("/assistant-invite")
def create_assistant_invite(
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(require("manage_team")),
    account: AccountDB = Depends(get_current_account),
) -> dict:
    """Mint a one-time link that adds whoever opens it as an assistant coach of the
    active team. Only the hash is stored; the raw link is returned to share.
    Needs the head coach's name first — it's what the invitee sees."""
    if not (account.display_name or "").strip():
        raise HTTPException(
            status_code=409, detail="Add your name first — your assistant will see it"
        )
    raw = new_token()
    invite = InviteDB(
        token_hash=hash_token(raw),
        created_at=now_iso(),
        expires_at=iso_in(days=INVITE_TTL_DAYS),
        note=f"assistant invite from {account.email} for squad {squad.id}",
        invited_by_account_id=account.id,
        squad_id=squad.id,
        role=ASSISTANT,
    )
    session.add(invite)
    session.commit()
    return {
        "link": f"{app_base_url()}/?assist={raw}",
        "expires_at": invite.expires_at,
        "expires_in_days": INVITE_TTL_DAYS,
    }


@router.delete("/assistants/{account_id}")
def remove_assistant(
    account_id: int,
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(require("manage_team")),
) -> dict:
    """Remove an assistant from the active team (head coach only)."""
    membership = get_membership(session, squad.id, account_id)  # type: ignore[arg-type]
    if membership is None or membership.role != ASSISTANT:
        raise HTTPException(status_code=404, detail="Assistant not found")
    _drop_membership(session, membership)
    session.commit()
    return {"ok": True}


@router.post("/{squad_id}/leave")
def leave_team(
    squad_id: int,
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> dict:
    """An assistant leaves a team they help with. The head coach can't leave their
    own team (remove it, or — later — hand it over)."""
    owned_squad(squad_id, account, session)
    membership = get_membership(session, squad_id, account.id)  # type: ignore[arg-type]
    if membership is None or membership.role != ASSISTANT:
        raise HTTPException(status_code=409, detail="The head coach can't leave their own team")
    _drop_membership(session, membership)
    session.commit()
    session.refresh(account)
    return {"ok": True, "active_squad_id": account.squad_id}


def _drop_membership(session: Session, membership: SquadMembershipDB) -> None:
    """Delete an assistant membership and re-point the account if it was active."""
    squad_id = membership.squad_id
    acc = session.get(AccountDB, membership.account_id)
    session.delete(membership)
    session.flush()
    if acc is not None and acc.squad_id == squad_id:
        repoint_active_squad(session, acc, exclude_squad_id=squad_id)


class AssistTokenBody(BaseModel):
    token: str


def _live_assistant_invite(session: Session, token: str) -> tuple[InviteDB, SquadDB]:
    invite = session.exec(select(InviteDB).where(InviteDB.token_hash == hash_token(token))).first()
    if (
        not invite
        or invite.role != ASSISTANT
        or invite.redeemed_at is not None
        or is_expired(invite.expires_at)
    ):
        raise HTTPException(status_code=400, detail="This invite link is invalid or expired")
    squad = session.get(SquadDB, invite.squad_id) if invite.squad_id else None
    if squad is None:
        raise HTTPException(status_code=400, detail="This invite link is invalid or expired")
    return invite, squad


@router.post("/assist-preview")
def preview_assistant_invite(
    body: AssistTokenBody, session: Session = Depends(get_session)
) -> dict:
    """Unauthenticated: which team an assistant link is for, so the join screen can
    say "Join U10 Tigers as Sam's assistant coach". Reveals nothing without a live
    token."""
    _invite, squad = _live_assistant_invite(session, body.token)
    head = head_account(session, squad.id)  # type: ignore[arg-type]
    return {
        "team_name": (squad.team_name or "").strip(),
        "head_name": head.display_name if head else "",
    }


@router.post("/join")
def join_as_assistant(
    body: AssistTokenBody,
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> dict:
    """A signed-in coach accepts an assistant invite: join that team and switch to it."""
    invite, squad = _live_assistant_invite(session, body.token)
    existing = get_membership(session, squad.id, account.id)  # type: ignore[arg-type]
    if existing is not None and existing.role == HEAD:
        raise HTTPException(status_code=409, detail="You're already the head coach of this team")
    if existing is None:
        add_membership(
            session, squad, account.id, ASSISTANT,  # type: ignore[arg-type]
            invited_by_account_id=invite.invited_by_account_id,
        )
    invite.account_id = account.id
    invite.redeemed_at = now_iso()
    account.squad_id = squad.id  # type: ignore[assignment]
    session.add(invite)
    session.add(account)
    session.commit()
    return {"ok": True, "active_squad_id": squad.id, "team_name": squad.team_name}
