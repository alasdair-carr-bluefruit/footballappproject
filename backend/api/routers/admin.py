"""Admin router (`/api/admin`) — invite generation, gated by ADMIN_KEY.

Invite-only onboarding: only coaches you send a `/?invite=…` link to can create a
team. Gated by a shared `ADMIN_KEY` sent in the `X-Admin-Key` header — crude but
sufficient for a trial. When no ADMIN_KEY is configured the endpoints are closed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.auth.tokens import hash_token, iso_in, new_token, now_iso
from backend.db.database import get_session
from backend.db.models import InviteDB
from backend.settings import INVITE_TTL_DAYS, admin_key, app_base_url

router = APIRouter()


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    key = admin_key()
    if not key or x_admin_key != key:
        raise HTTPException(status_code=403, detail="Admin access denied")


class InviteCreate(BaseModel):
    note: str = ""


@router.post("/invites", dependencies=[Depends(require_admin)])
def create_invite(body: InviteCreate, session: Session = Depends(get_session)) -> dict:
    """Mint a one-time invite link (raw token shown once; only its hash is stored)."""
    raw = new_token()
    invite = InviteDB(
        token_hash=hash_token(raw),
        created_at=now_iso(),
        expires_at=iso_in(days=INVITE_TTL_DAYS),
        note=body.note.strip(),
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    return {
        "id": invite.id,
        "link": f"{app_base_url()}/?invite={raw}",
        "note": invite.note,
        "expires_at": invite.expires_at,
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
