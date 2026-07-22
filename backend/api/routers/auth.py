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

from backend.api.deps import get_current_account
from backend.auth.email import (
    send_email_change_link,
    send_email_changed_notice,
    send_login_link,
)
from backend.auth.session import set_session_cookie
from backend.auth.tokens import (
    hash_token,
    is_expired,
    iso_in,
    new_token,
    now_iso,
    tokens_match,
)
from backend.db.database import get_session
from backend.db.models import (
    AccountDB,
    EmailChangeTokenDB,
    InviteDB,
    LoginTokenDB,
    ReclaimTokenDB,
    SquadDB,
)
from backend.db.repositories import delete_squad_data, get_or_create_squad
from backend.settings import (
    INVITE_TTL_DAYS,
    LOGIN_TOKEN_TTL_MINUTES,
    RECLAIM_TOKEN_TTL_DAYS,
    SESSION_COOKIE,
    app_base_url,
    auth_enabled,
    resend_api_key,
)

router = APIRouter()


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


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
    session.commit()  # assign account.id so we can set the squad owner
    session.refresh(account)

    squad.account_id = account.id  # every squad created from now on has an owner
    session.add(squad)
    invite.account_id = account.id
    invite.redeemed_at = now_iso()
    session.add(invite)
    session.commit()
    session.refresh(account)

    set_session_cookie(response, account.id, account.session_epoch)  # type: ignore[arg-type]
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

    set_session_cookie(response, account.id, account.session_epoch)  # type: ignore[arg-type]
    return _account_public(account)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


# ── Account self-service (Settings screen) ──────────────────────────────────────


class RequestEmailChangeBody(BaseModel):
    new_email: str


@router.post("/account/request-email-change")
def request_email_change(
    body: RequestEmailChangeBody,
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> dict:
    """Start an email change: email a one-time confirm link to the NEW address.

    The address only switches once that link is confirmed (see /confirm-email-change),
    so a typo or a hijack attempt can't take over the login handle.
    """
    new_email = _norm_email(body.new_email)
    if not new_email or "@" not in new_email:
        raise HTTPException(status_code=422, detail="A valid email is required")
    if new_email == _norm_email(account.email):
        raise HTTPException(status_code=422, detail="That's already your email address")
    if session.exec(select(AccountDB).where(AccountDB.email == new_email)).first():
        raise HTTPException(status_code=409, detail="That email is already in use")

    raw = new_token()
    session.add(
        EmailChangeTokenDB(
            account_id=account.id,  # type: ignore[arg-type]
            new_email=new_email,
            token_hash=hash_token(raw),
            created_at=now_iso(),
            expires_at=iso_in(minutes=LOGIN_TOKEN_TTL_MINUTES),
        )
    )
    session.commit()
    link = f"{app_base_url()}/?email_change={raw}"
    send_email_change_link(new_email, link)
    result: dict = {"ok": True}
    if not resend_api_key():
        result["dev_link"] = link  # dev convenience (no email provider)
    return result


class ConfirmEmailChangeBody(BaseModel):
    token: str


@router.post("/account/confirm-email-change")
def confirm_email_change(
    body: ConfirmEmailChangeBody,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    """Consume an email-change token (from the link) and swap the account's email.

    Deliberately does NOT require the existing session — the token was emailed to
    the new address and is bound to the account, which is the authorisation. A
    fresh session cookie is issued so the coach stays signed in.
    """
    presented = hash_token(body.token)
    row = session.exec(
        select(EmailChangeTokenDB).where(EmailChangeTokenDB.token_hash == presented)
    ).first()
    if not row or row.consumed_at is not None or is_expired(row.expires_at):
        raise HTTPException(status_code=400, detail="This confirmation link is invalid or expired")
    if not tokens_match(body.token, row.token_hash):
        raise HTTPException(status_code=400, detail="This confirmation link is invalid or expired")

    account = session.get(AccountDB, row.account_id)
    if not account or account.status != "active":
        raise HTTPException(status_code=400, detail="This account is not active")
    # Re-check the address is still free (a rival account may have taken it since).
    clash = session.exec(select(AccountDB).where(AccountDB.email == row.new_email)).first()
    if clash and clash.id != account.id:
        raise HTTPException(status_code=409, detail="That email is already in use")

    prior_email = account.email  # notify the old address, and let it reclaim
    account.email = row.new_email
    row.consumed_at = now_iso()

    # Mint a "reclaim your squad" token so the previous owner can undo an
    # unauthorised change (revert email + sign out everywhere). Longer-lived than a
    # login token — they may not read the notice email straight away.
    reclaim_raw = new_token()
    session.add(
        ReclaimTokenDB(
            account_id=account.id,  # type: ignore[arg-type]
            prior_email=prior_email,
            token_hash=hash_token(reclaim_raw),
            created_at=now_iso(),
            expires_at=iso_in(days=RECLAIM_TOKEN_TTL_DAYS),
        )
    )
    session.add(account)
    session.add(row)
    session.commit()
    session.refresh(account)

    squad = session.get(SquadDB, account.squad_id)
    team_name = (squad.team_name or squad.name) if squad else "your squad"
    send_email_changed_notice(
        prior_email,
        new_email=account.email,
        team_name=team_name,
        reclaim_link=f"{app_base_url()}/?reclaim={reclaim_raw}",
    )

    set_session_cookie(response, account.id, account.session_epoch)  # type: ignore[arg-type]
    return _account_public(account)


class ReclaimBody(BaseModel):
    token: str


@router.post("/account/reclaim")
def reclaim_account(
    body: ReclaimBody, response: Response, session: Session = Depends(get_session)
) -> dict:
    """Undo an email change from the notice sent to the OLD address: restore that
    address and bump session_epoch (signing out every device, incl. an attacker's).

    No session required — the reclaim token IS the authorisation. Does NOT sign the
    caller in; they re-request a magic link with the restored address.
    """
    presented = hash_token(body.token)
    row = session.exec(
        select(ReclaimTokenDB).where(ReclaimTokenDB.token_hash == presented)
    ).first()
    if not row or row.consumed_at is not None or is_expired(row.expires_at):
        raise HTTPException(status_code=400, detail="This reclaim link is invalid or expired")
    if not tokens_match(body.token, row.token_hash):
        raise HTTPException(status_code=400, detail="This reclaim link is invalid or expired")

    account = session.get(AccountDB, row.account_id)
    if not account:
        raise HTTPException(status_code=400, detail="This account no longer exists")
    # The address must still be free to restore (normally it is — nobody else can
    # claim it while it's the pending prior handle, but re-check defensively).
    clash = session.exec(select(AccountDB).where(AccountDB.email == row.prior_email)).first()
    if clash and clash.id != account.id:
        raise HTTPException(status_code=409, detail="That email is no longer available")

    account.email = row.prior_email
    account.session_epoch += 1  # invalidate every issued session (all devices)
    row.consumed_at = now_iso()
    session.add(account)
    session.add(row)
    session.commit()

    # Drop the caller's own cookie too, for good measure (they'll sign in fresh).
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True, "email": row.prior_email}


@router.post("/invite-a-friend")
def invite_a_friend(
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> dict:
    """Mint a one-time invite link a signed-in coach can share with another coach.

    The non-admin counterpart of admin `create_invite`: same `InviteDB` one-time
    token (only its hash is stored), but self-service and attributed to the
    inviting account in the note. The raw link is returned so the coach can share
    it however they like (WhatsApp, text, etc.) — the growth loop.
    """
    raw = new_token()
    invite = InviteDB(
        token_hash=hash_token(raw),
        created_at=now_iso(),
        expires_at=iso_in(days=INVITE_TTL_DAYS),
        note=f"friend invite from {account.email}",
        invited_by_account_id=account.id,
    )
    session.add(invite)
    session.commit()
    return {
        "link": f"{app_base_url()}/?invite={raw}",
        "expires_at": invite.expires_at,
        "expires_in_days": INVITE_TTL_DAYS,
    }


@router.post("/account/clear-data")
def clear_account_data(
    session: Session = Depends(get_session),
    account: AccountDB = Depends(get_current_account),
) -> dict:
    """Delete all of the account's football data — players, matches and tournaments
    (guest players included) — while keeping the account, its login and the squad
    shell. Backs the self-service deletion promise in the Privacy Policy.
    """
    # Keep the squad shell (and its owner link) — clear only the football data.
    delete_squad_data(session, account.squad_id, drop_squad_row=False)
    session.commit()
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
    from backend.auth.session import session_epoch_from, verify_session

    cookie = request.cookies.get(SESSION_COOKIE)
    account_id = verify_session(cookie)
    account = session.get(AccountDB, account_id) if account_id is not None else None
    if not account or account.status != "active":
        raise HTTPException(status_code=401, detail="Not authenticated")
    if (session_epoch_from(cookie) or 0) != account.session_epoch:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _account_public(account)
