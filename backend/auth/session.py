"""Stateless signed session cookies.

A session is `"<account_id>.<issued_unix>"` plus an HMAC-SHA256 signature over
that payload, all base64url-encoded — the same construction as itsdangerous, but
stdlib-only (no extra dependency). Verification recomputes the signature with a
constant-time compare and rejects anything older than SESSION_MAX_AGE_DAYS.

The signing key is credential-agnostic: whether the account authenticated via an
invite redeem or a magic link, the issued session is identical, so adding new
credential types later never touches this module (V1_MULTIUSER_PLAN.md §2).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time

from starlette.responses import Response

from backend.settings import (
    SESSION_COOKIE,
    SESSION_MAX_AGE_DAYS,
    cookie_secure,
    secret_key,
)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload: str) -> str:
    sig = hmac.new(secret_key().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return _b64e(sig)


def sign_session(account_id: int, epoch: int = 0) -> str:
    """Issue a signed session token for `account_id` (goes in the session cookie).

    `epoch` is the account's session generation (AccountDB.session_epoch): bumping
    it server-side invalidates every previously-issued token, which is how "sign
    out of all devices" (account reclaim) works. Legacy tokens carried no epoch;
    they parse as epoch 0, matching the default, so a deploy never mass-logs-out."""
    payload = f"{account_id}.{int(time.time())}.{epoch}"
    return f"{_b64e(payload.encode('utf-8'))}.{_sign(payload)}"


def _parse(token: str | None) -> tuple[int, int, int] | None:
    """Return (account_id, issued_unix, epoch) from a valid, unexpired token, else None."""
    if not token or token.count(".") != 1:
        return None
    payload_b64, sig = token.split(".", 1)
    try:
        payload = _b64d(payload_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    parts = payload.split(".")
    if len(parts) not in (2, 3):  # 2 = legacy (no epoch), 3 = current
        return None
    try:
        account_id = int(parts[0])
        issued = int(parts[1])
        epoch = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        return None
    if time.time() - issued > SESSION_MAX_AGE_DAYS * 86400:
        return None
    return account_id, issued, epoch


def verify_session(token: str | None) -> int | None:
    """Return the account_id from a valid, unexpired session token, else None.

    Only checks signature + expiry — the epoch is validated against the account's
    current session_epoch by the callers that load the account (deps + /me)."""
    parsed = _parse(token)
    return parsed[0] if parsed else None


def session_epoch_from(token: str | None) -> int | None:
    """The epoch embedded in a valid token (0 for legacy tokens), else None."""
    parsed = _parse(token)
    return parsed[2] if parsed else None


def set_session_cookie(response: Response, account_id: int, epoch: int = 0) -> None:
    """Write a freshly-signed session cookie. Shared by login/verify and the
    rolling-refresh middleware so cookie attributes stay in one place. Because the
    token is re-signed with the current time, calling this on each authenticated
    request turns the 30-day expiry into a *sliding* window (30 days of inactivity)."""
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(account_id, epoch),
        max_age=SESSION_MAX_AGE_DAYS * 86400,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )
