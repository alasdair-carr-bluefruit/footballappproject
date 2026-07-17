"""One-time tokens (invites + magic links) and small time helpers.

Raw tokens are high-entropy and shown to the user exactly once; only their
SHA-256 hash is stored, so a database leak never yields a usable token.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta


def new_token() -> str:
    """A fresh high-entropy URL-safe token (the raw value handed to the user)."""
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> str:
    """The stored form of a token — a hex SHA-256 digest. Never store the raw token."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def tokens_match(raw: str, stored_hash: str) -> bool:
    """Constant-time comparison of a presented raw token against a stored hash."""
    return secrets.compare_digest(hash_token(raw), stored_hash)


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string (matches how other models store dates)."""
    return datetime.now(UTC).isoformat()


def iso_in(*, minutes: int = 0, days: int = 0) -> str:
    """An ISO-8601 UTC timestamp `minutes`/`days` from now (for expiries)."""
    return (datetime.now(UTC) + timedelta(minutes=minutes, days=days)).isoformat()


def is_expired(expires_at_iso: str) -> bool:
    """Whether an ISO expiry timestamp is in the past (treats unparseable as expired)."""
    try:
        expires = datetime.fromisoformat(expires_at_iso)
    except (ValueError, TypeError):
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return datetime.now(UTC) >= expires
