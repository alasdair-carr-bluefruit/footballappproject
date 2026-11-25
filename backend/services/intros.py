"""Walkthrough + first-use intros: which ones a coach has already seen.

Stored on the account (`AccountDB.intros_seen`, JSON `{intro_id: ISO date}`) so a
coach who sets up on a laptop isn't shown the same tour again on their phone. The
frontend owns the intro ids and copy; the server only remembers ids.

`intros_seen == ""` marks an account from before intros existed. `backfill` marks
the intros for things that coach already uses (players → the squad intro, a match →
the planning intros…) so a live coach never gets a "first time" card for a screen
they've used every Saturday. New accounts start at "{}" (see `/redeem`).
"""
from __future__ import annotations

import json
import re

from sqlmodel import Session, select

from backend.auth.tokens import now_iso
from backend.db.memberships import ASSISTANT, HEAD
from backend.db.models import AccountDB, MatchDB, PlayerDB, SquadMembershipDB, TournamentDB

INTRO_ID = re.compile(r"^[a-z_][a-z0-9_:-]{0,47}$")
MAX_INTROS = 64  # a handful of real ids; caps what a client can store

# Intros for each kind of existing data (ids mirror frontend/intros.js).
PLANNING = ("first-setup", "first-review", "first-tinker", "first-live")


def read_seen(account: AccountDB) -> dict[str, str]:
    try:
        seen = json.loads(account.intros_seen or "{}")
    except ValueError:
        return {}
    return seen if isinstance(seen, dict) else {}


def _write(account: AccountDB, seen: dict[str, str]) -> None:
    account.intros_seen = json.dumps(seen, separators=(",", ":"), sort_keys=True)


def needs_backfill(account: AccountDB) -> bool:
    return not account.intros_seen


def backfill(session: Session, account: AccountDB) -> None:
    """Mark as seen what a pre-intros account already uses. Does not commit."""
    today = now_iso()
    memberships = session.exec(
        select(SquadMembershipDB).where(SquadMembershipDB.account_id == account.id)
    ).all()
    all_squads = {m.squad_id for m in memberships} | {account.squad_id}
    head_squads = {m.squad_id for m in memberships if m.role == HEAD}
    seen: dict[str, str] = {"welcome": today}  # already set up — no welcome tour
    if any(m.role == ASSISTANT for m in memberships):
        seen["assistant-welcome"] = today
    if head_squads and session.exec(
        select(PlayerDB.id).where(
            PlayerDB.squad_id.in_(head_squads),  # type: ignore[attr-defined]
            PlayerDB.source_tournament_id.is_(None),  # type: ignore[union-attr]
        )
    ).first() is not None:
        seen["first-squad"] = today
    has_match = session.exec(
        select(MatchDB.id).where(MatchDB.squad_id.in_(all_squads))  # type: ignore[attr-defined]
    ).first() is not None
    has_tournament = session.exec(
        select(TournamentDB.id).where(TournamentDB.squad_id.in_(all_squads))  # type: ignore[attr-defined]
    ).first() is not None
    if has_match or has_tournament:
        seen.update({i: today for i in PLANNING})
    if has_match:
        seen["first-rested"] = today
    if has_tournament:
        seen["first-tournament"] = today
    seen.update(read_seen(account))
    _write(account, seen)
    session.add(account)


def mark(account: AccountDB, intro_id: str, on: bool = True) -> bool:
    """Mark (or un-mark) one intro. Returns False for an id we won't store."""
    if not INTRO_ID.match(intro_id):
        return False
    seen = read_seen(account)
    if on:
        if intro_id not in seen and len(seen) >= MAX_INTROS:
            return False
        seen.setdefault(intro_id, now_iso())
    else:
        seen.pop(intro_id, None)
    _write(account, seen)
    return True
