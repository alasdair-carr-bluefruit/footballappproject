"""Auth router (`/api/auth`) — invite redeem + magic-link login.

Auth is magic-link only. Sign-up = redeem a one-time invite (which also captures
the email and logs the coach straight in). Returning login on a new device =
request a link to that email, then verify it. Every path issues the *same* signed
session cookie against the same AccountDB (V1_MULTIUSER_PLAN.md §2).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.auth.email import send_login_link
from backend.auth.session import sign_session
from backend.auth.tokens import (
    hash_token,
    is_expired,
    iso_in,
    new_token,
    now_iso,
    tokens_match,
)
from backend.db.database import get_session
from backend.db.models import AccountDB, InviteDB, LoginTokenDB, SquadDB
from backend.db.repositories import get_or_create_squad
from backend.settings import (
    LOGIN_TOKEN_TTL_MINUTES,
    SESSION_COOKIE,
    SESSION_MAX_AGE_DAYS,
    app_base_url,
    auth_enabled,
    cookie_secure,
    resend_api_key,
)

router = APIRouter()


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _set_session_cookie(response: Response, account_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(account_id),
        max_age=SESSION_MAX_AGE_DAYS * 86400,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )


def _account_public(account: AccountDB) -> dict:
    return {
        "authenticated": True,
        "auth_enabled": auth_enabled(),
        "display_name": account.display_name,
        "email": account.email,
        "squad_id": account.squad_id,
        "seen_tutorial": bool(account.seen_tutorial),
    }


class RedeemBody(BaseModel):
    token: str
    email: str
    display_name: str = ""


@router.post("/redeem")
def redeem_invite(
    body: RedeemBody, response: Response, session: Session = Depends(get_session)
) -> dict:
    """Redeem a one-time invite: create the account + its empty squad, log in."""
    invite = session.exec(
        select(InviteDB).where(InviteDB.token_hash == hash_token(body.token))
    ).first()
    if not invite or invite.redeemed_at is not None or is_expired(invite.expires_at):
        raise HTTPException(status_code=400, detail="This invite link is invalid or expired")

    email = _norm_email(body.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="A valid email is required")
    if session.exec(select(AccountDB).where(AccountDB.email == email)).first():
        raise HTTPException(
            status_code=409,
            detail="An account already exists for that email — request a sign-in link instead",
        )

    squad = SquadDB(name="My Squad")
    session.add(squad)
    session.commit()
    session.refresh(squad)

    account = AccountDB(
        squad_id=squad.id,  # type: ignore[arg-type]
        email=email,
        display_name=body.display_name.strip(),
        status="active",
        created_at=now_iso(),
        last_login_at=now_iso(),
    )
    session.add(account)
    invite.account_id = account.id
    invite.redeemed_at = now_iso()
    session.add(invite)
    session.commit()
    session.refresh(account)

    _set_session_cookie(response, account.id)  # type: ignore[arg-type]
    return _account_public(account)


class RequestLinkBody(BaseModel):
    email: str


@router.post("/request-link")
def request_login_link(body: RequestLinkBody, session: Session = Depends(get_session)) -> dict:
    """Email a one-time sign-in link to an existing account. Always 200 (no enumeration)."""
    email = _norm_email(body.email)
    account = session.exec(
        select(AccountDB).where(AccountDB.email == email, AccountDB.status == "active")
    ).first()

    result: dict = {"ok": True}
    if account:
        raw = new_token()
        session.add(
            LoginTokenDB(
                account_id=account.id,  # type: ignore[arg-type]
                token_hash=hash_token(raw),
                created_at=now_iso(),
                expires_at=iso_in(minutes=LOGIN_TOKEN_TTL_MINUTES),
            )
        )
        session.commit()
        link = f"{app_base_url()}/?login={raw}"
        send_login_link(email, link)
        # In dev (no email provider) surface the link so the flow is testable.
        if not resend_api_key():
            result["dev_link"] = link
    return result


class VerifyBody(BaseModel):
    token: str


@router.post("/verify")
def verify_login(
    body: VerifyBody, response: Response, session: Session = Depends(get_session)
) -> dict:
    """Consume a magic-link token and issue a session."""
    presented = hash_token(body.token)
    token_row = session.exec(
        select(LoginTokenDB).where(LoginTokenDB.token_hash == presented)
    ).first()
    if not token_row or token_row.consumed_at is not None or is_expired(token_row.expires_at):
        raise HTTPException(status_code=400, detail="This sign-in link is invalid or expired")
    # Defence in depth: constant-time re-check of the raw token against the stored hash.
    if not tokens_match(body.token, token_row.token_hash):
        raise HTTPException(status_code=400, detail="This sign-in link is invalid or expired")

    account = session.get(AccountDB, token_row.account_id)
    if not account or account.status != "active":
        raise HTTPException(status_code=400, detail="This account is not active")

    token_row.consumed_at = now_iso()
    account.last_login_at = now_iso()
    session.add(token_row)
    session.add(account)
    session.commit()
    session.refresh(account)

    _set_session_cookie(response, account.id)  # type: ignore[arg-type]
    return _account_public(account)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(request: Request, session: Session = Depends(get_session)) -> dict:
    """Boot-time identity probe. 401 when auth is on and the caller isn't signed in."""
    if not auth_enabled():
        # Single-user mode: report the implicit default squad so the app just loads.
        squad = get_or_create_squad(session)
        return {
            "authenticated": True,
            "auth_enabled": False,
            "display_name": "",
            "email": "",
            "squad_id": squad.id,
            "seen_tutorial": True,
        }
    from backend.auth.session import verify_session

    account_id = verify_session(request.cookies.get(SESSION_COOKIE))
    account = session.get(AccountDB, account_id) if account_id is not None else None
    if not account or account.status != "active":
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _account_public(account)
