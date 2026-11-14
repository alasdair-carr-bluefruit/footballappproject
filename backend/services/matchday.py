"""Matchday control + the server-side match clock (assistant coach mode, phase 2).

Two people can now run the same match (the head coach and the assistant who owns the
plan), so a live match has ONE controlling device. Anyone else who opens it watches
read-only and can take control — deliberately open to everyone allowed to run the
match, so a dead phone never locks a team out mid-game.

Compatibility rule: control is only enforced between requests that carry an
`X-Device-Id` header. A request without one (a not-yet-updated cached frontend, a
script) behaves exactly as before, so a deploy can never strand a coach mid-match.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session

from backend.db.models import AccountDB, MatchDB


def _now() -> datetime:
    return datetime.now(UTC)


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


# ── Control ──────────────────────────────────────────────────────────────────────
def has_controller(m: MatchDB) -> bool:
    return m.status == "in_progress" and bool(m.controller_device_id)


def controls(m: MatchDB, account_id: int | None, device_id: str) -> bool:
    return (
        bool(device_id)
        and m.controller_device_id == device_id
        and m.controller_account_id == account_id
    )


def claim(m: MatchDB, account_id: int | None, device_id: str) -> None:
    m.controller_account_id = account_id
    m.controller_device_id = device_id
    m.controller_since = _now().isoformat()


def release(m: MatchDB) -> None:
    m.controller_account_id = None
    m.controller_device_id = ""
    m.controller_since = None


def controller_name(session: Session, m: MatchDB) -> str:
    if m.controller_account_id is None:
        return ""
    account = session.get(AccountDB, m.controller_account_id)
    return (account.display_name if account else "") or "another coach"


def controller_info(
    session: Session, m: MatchDB, account_id: int | None, device_id: str
) -> dict[str, Any] | None:
    """Who is running this live match, from the caller's point of view (None = nobody)."""
    if not has_controller(m):
        return None
    return {
        "name": controller_name(session, m),
        "is_me": controls(m, account_id, device_id),
        "same_account": m.controller_account_id == account_id,
        "since": m.controller_since,
    }


# ── Clock ────────────────────────────────────────────────────────────────────────
def timer_elapsed_ms(m: MatchDB) -> int:
    elapsed = m.timer_elapsed_ms or 0
    anchor = _parse(m.timer_anchor_at)
    if m.timer_running and anchor is not None:
        elapsed += int((_now() - anchor).total_seconds() * 1000)
    return max(0, elapsed)


def timer_info(m: MatchDB) -> dict[str, Any] | None:
    if m.timer_anchor_at is None:
        return None
    return {"running": bool(m.timer_running), "elapsed_ms": timer_elapsed_ms(m)}


def set_timer(m: MatchDB, *, running: bool, elapsed_ms: int) -> None:
    """Record the clock as the controlling device reports it. Stored as "elapsed at a
    server instant", so devices never compare their own wall clocks."""
    m.timer_running = 1 if running else 0
    m.timer_elapsed_ms = max(0, int(elapsed_ms))
    m.timer_anchor_at = _now().isoformat()


def clear_timer(m: MatchDB) -> None:
    m.timer_running = 0
    m.timer_elapsed_ms = 0
    m.timer_anchor_at = None
