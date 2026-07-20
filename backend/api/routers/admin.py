"""Admin router (`/api/admin`) — invite generation, gated by ADMIN_KEY.

Invite-only onboarding: only coaches you send a `/?invite=…` link to can create a
team. Gated by a shared `ADMIN_KEY` sent in the `X-Admin-Key` header — crude but
sufficient for a trial. When no ADMIN_KEY is configured the endpoints are closed.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.auth.email import send_login_link
from backend.auth.session import set_session_cookie
from backend.auth.tokens import hash_token, iso_in, new_token, now_iso
from backend.db.database import get_session
from backend.db.models import AccountDB, InviteDB, MatchDB, PlayerDB, SquadDB, TournamentDB
from backend.settings import INVITE_TTL_DAYS, admin_key, app_base_url, resend_api_key

router = APIRouter()


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    key = admin_key()
    if not key or x_admin_key != key:
        raise HTTPException(status_code=403, detail="Admin access denied")


class InviteCreate(BaseModel):
    note: str = ""
    email: str = ""  # if set, email the invite link to this coach (invite variant)


@router.post("/invites", dependencies=[Depends(require_admin)])
def create_invite(body: InviteCreate, session: Session = Depends(get_session)) -> dict:
    """Mint a one-time invite link (raw token shown once; only its hash is stored).

    If `email` is supplied, also send the coach the invite link via the invite
    email variant. The raw `link` is always returned so you can copy/share it
    manually — important when no email provider is configured (`email_configured`
    is False), since the send is then only a dev-stub log.
    """
    raw = new_token()
    email = body.email.strip()
    invite = InviteDB(
        token_hash=hash_token(raw),
        created_at=now_iso(),
        expires_at=iso_in(days=INVITE_TTL_DAYS),
        note=body.note.strip() or (f"invited {email}" if email else ""),
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    link = f"{app_base_url()}/?invite={raw}"
    email_configured = bool(resend_api_key())
    if email:
        send_login_link(email, link, is_invite=True)
    return {
        "id": invite.id,
        "link": link,
        "note": invite.note,
        "expires_at": invite.expires_at,
        "emailed_to": email or None,
        "email_configured": email_configured,
    }


@router.get("/invites", dependencies=[Depends(require_admin)])
def list_invites(session: Session = Depends(get_session)) -> list[dict]:
    """List invites (status only — never the token) so you can see who's outstanding."""
    invites = session.exec(select(InviteDB).order_by(InviteDB.id.desc())).all()  # type: ignore[attr-defined]
    return [
        {
            "id": inv.id,
            "note": inv.note,
            "created_at": inv.created_at,
            "expires_at": inv.expires_at,
            "redeemed": inv.redeemed_at is not None,
            "redeemed_at": inv.redeemed_at,
            "account_id": inv.account_id,
        }
        for inv in invites
    ]


# ── Account support tooling (investigate / impersonate) ─────────────────────────
@router.get("/accounts", dependencies=[Depends(require_admin)])
def list_accounts(session: Session = Depends(get_session)) -> list[dict]:
    """List all coach accounts so you can find the one to investigate."""
    accounts = session.exec(select(AccountDB).order_by(AccountDB.id.desc())).all()  # type: ignore[attr-defined]
    return [
        {
            "id": a.id,
            "email": a.email,
            "display_name": a.display_name,
            "status": a.status,
            "squad_id": a.squad_id,
            "created_at": a.created_at,
            "last_login_at": a.last_login_at,
        }
        for a in accounts
    ]


@router.get("/accounts/{account_id}/dump", dependencies=[Depends(require_admin)])
def dump_account(account_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Read-only snapshot of an account's squad, players, matches and tournaments —
    for investigating "something looks weird" without touching anything."""
    account = session.get(AccountDB, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    squad = session.get(SquadDB, account.squad_id)
    players = session.exec(select(PlayerDB).where(PlayerDB.squad_id == account.squad_id)).all()
    matches = session.exec(select(MatchDB).where(MatchDB.squad_id == account.squad_id)).all()
    tournaments = session.exec(
        select(TournamentDB).where(TournamentDB.squad_id == account.squad_id)
    ).all()
    return {
        "account": {
            "id": account.id, "email": account.email, "display_name": account.display_name,
            "status": account.status, "created_at": account.created_at,
            "last_login_at": account.last_login_at,
        },
        "squad": {"id": squad.id, "team_name": squad.team_name} if squad else None,
        "counts": {
            "players": len(players), "matches": len(matches), "tournaments": len(tournaments),
        },
        "players": [{"id": p.id, "name": p.name, "shirt_number": p.shirt_number,
                     "is_guest": p.source_tournament_id is not None} for p in players],
        "matches": [{"id": m.id, "date": m.date, "opponent": m.opponent, "status": m.status,
                     "tournament_id": m.tournament_id} for m in matches],
        "tournaments": [{"id": t.id, "name": t.name, "date": t.date} for t in tournaments],
    }


@router.post("/accounts/{account_id}/impersonate", dependencies=[Depends(require_admin)])
def impersonate_account(
    account_id: int, response: Response, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """Issue a session cookie for this account so you (the dev) can log in AS the
    coach and see/fix exactly what they see through the normal UI. Use sparingly."""
    account = session.get(AccountDB, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    set_session_cookie(response, account.id, account.session_epoch)  # type: ignore[arg-type]
    return {"impersonating": account.id, "email": account.email, "squad_id": account.squad_id}
