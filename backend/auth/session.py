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


def sign_session(account_id: int) -> str:
    """Issue a signed session token for `account_id` (goes in the session cookie)."""
    payload = f"{account_id}.{int(time.time())}"
    return f"{_b64e(payload.encode('utf-8'))}.{_sign(payload)}"


def verify_session(token: str | None) -> int | None:
    """Return the account_id from a valid, unexpired session token, else None."""
    if not token or token.count(".") != 1:
        return None
    payload_b64, sig = token.split(".", 1)
    try:
        payload = _b64d(payload_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    account_part, _, issued_part = payload.partition(".")
    try:
        account_id = int(account_part)
        issued = int(issued_part)
    except ValueError:
        return None
    if time.time() - issued > SESSION_MAX_AGE_DAYS * 86400:
        return None
    return account_id


def set_session_cookie(response: Response, account_id: int) -> None:
    """Write a freshly-signed session cookie. Shared by login/verify and the
    rolling-refresh middleware so cookie attributes stay in one place. Because the
    token is re-signed with the current time, calling this on each authenticated
    request turns the 30-day expiry into a *sliding* window (30 days of inactivity)."""
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(account_id),
        max_age=SESSION_MAX_AGE_DAYS * 86400,
        httponly=True,
        secure=cookie_secure(),
        samesite="lax",
        path="/",
    )
