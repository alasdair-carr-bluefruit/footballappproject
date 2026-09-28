"""Squad memberships (T3.2 assistant coach mode) — who can access a squad, and as what.

Roles are per team: one account can be `head` of its own squad and `assistant` on
someone else's. Exactly one `head` per squad; `SquadDB.account_id` mirrors it during
the transition (kept in step by `add_membership`). `AccountDB.squad_id` stays the
account's *active* squad, which may be one it assists.

Nothing here commits — callers own the transaction (repositories' convention).
"""
from __future__ import annotations

from sqlmodel import Session, select

from backend.auth.tokens import now_iso
from backend.db.models import AccountDB, SquadDB, SquadMembershipDB

HEAD = "head"
ASSISTANT = "assistant"


def get_membership(session: Session, squad_id: int, account_id: int) -> SquadMembershipDB | None:
    """The account's membership of the squad, adopting a legacy owner on the fly.

    A squad whose `account_id` is this account but which has no membership row (made
    before the backfill, or by code paths that only set the owner) is treated as —
    and lazily recorded as — a head membership, so no owner is ever locked out.
    """
    row = session.exec(
        select(SquadMembershipDB).where(
            SquadMembershipDB.squad_id == squad_id, SquadMembershipDB.account_id == account_id
        )
    ).first()
    if row is not None:
        return row
    squad = session.get(SquadDB, squad_id)
    if squad is not None and squad.account_id == account_id:
        return add_membership(session, squad, account_id, HEAD)
    return None


def add_membership(
    session: Session,
    squad: SquadDB,
    account_id: int,
    role: str,
    invited_by_account_id: int | None = None,
) -> SquadMembershipDB:
    """Create a membership (or return the existing one unchanged). A head membership
    also sets `SquadDB.account_id`, keeping the transitional owner column in step."""
    existing = session.exec(
        select(SquadMembershipDB).where(
            SquadMembershipDB.squad_id == squad.id, SquadMembershipDB.account_id == account_id
        )
    ).first()
    if existing is not None:
        return existing
    row = SquadMembershipDB(
        squad_id=squad.id,  # type: ignore[arg-type]
        account_id=account_id,
        role=role,
        created_at=now_iso(),
        invited_by_account_id=invited_by_account_id,
    )
    session.add(row)
    session.info["memberships_changed"] = True  # lets read paths commit only when needed
    if role == HEAD:
        squad.account_id = account_id
        session.add(squad)
    session.flush()
    return row


def memberships_for(session: Session, account_id: int) -> list[SquadMembershipDB]:
    return list(
        session.exec(
            select(SquadMembershipDB)
            .where(SquadMembershipDB.account_id == account_id)
            .order_by(SquadMembershipDB.squad_id)  # type: ignore[arg-type]
        ).all()
    )


def assistants_of(session: Session, squad_id: int) -> list[SquadMembershipDB]:
    return list(
        session.exec(
            select(SquadMembershipDB)
            .where(SquadMembershipDB.squad_id == squad_id, SquadMembershipDB.role == ASSISTANT)
            .order_by(SquadMembershipDB.id)  # type: ignore[arg-type]
        ).all()
    )


def head_account(session: Session, squad_id: int) -> AccountDB | None:
    row = session.exec(
        select(SquadMembershipDB).where(
            SquadMembershipDB.squad_id == squad_id, SquadMembershipDB.role == HEAD
        )
    ).first()
    if row is not None:
        return session.get(AccountDB, row.account_id)
    squad = session.get(SquadDB, squad_id)
    return session.get(AccountDB, squad.account_id) if squad and squad.account_id else None


def head_count(session: Session, account_id: int) -> int:
    """How many squads the account is head coach of."""
    return sum(1 for m in memberships_for(session, account_id) if m.role == HEAD)


def repoint_active_squad(
    session: Session, account: AccountDB, exclude_squad_id: int | None = None
) -> int:
    """Point the account's active squad at another squad it can access — preferring
    one it heads — after it lost access to `exclude_squad_id` (removed, left, or the
    team was deleted). An account left with no team at all gets a fresh empty one it
    heads, so `AccountDB.squad_id` always resolves and they land on the normal
    "set up your team" flow. Returns the new active squad id."""
    candidates = [m for m in memberships_for(session, account.id) if m.squad_id != exclude_squad_id]  # type: ignore[arg-type]
    candidates.sort(key=lambda m: (m.role != HEAD, m.squad_id))
    if candidates:
        account.squad_id = candidates[0].squad_id
    else:
        squad = SquadDB(name="My Squad")
        session.add(squad)
        session.flush()
        add_membership(session, squad, account.id, HEAD)  # type: ignore[arg-type]
        account.squad_id = squad.id  # type: ignore[assignment]
    session.add(account)
    session.flush()
    return account.squad_id
