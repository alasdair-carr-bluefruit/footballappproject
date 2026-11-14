"""Auth dependencies — the single isolation chokepoint for multi-user (v1.1).

`get_squad_access` replaces the old implicit "the one squad" (`get_or_create_squad`)
with "the authenticated account's active squad, and its role there" (T3.2). Read
routes use `get_current_squad` (any role); write routes use `require(capability)`.
When `AUTH_ENABLED` is off (dev/tests), it falls back to the single default squad
(as head) so today's behaviour is unchanged. The `owned_*` helpers are
defence-in-depth: every id-path route must assert the row belongs to the current
squad, or a coach could read another's data by guessing an id (IDOR).
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import and_
from sqlmodel import Session, select

from backend.auth.session import session_epoch_from, verify_session
from backend.db.database import get_session
from backend.db.memberships import ASSISTANT, HEAD, get_membership, repoint_active_squad
from backend.db.models import (
    AccountDB,
    MatchDB,
    PlayerDB,
    SquadDB,
    SquadMembershipDB,
    TournamentDB,
)
from backend.db.repositories import get_or_create_squad
from backend.services import matchday
from backend.settings import SESSION_COOKIE, auth_enabled


def _load_from_request(
    request: Request, session: Session
) -> tuple[AccountDB, SquadDB | None, SquadMembershipDB | None] | None:
    """Resolve the signed-in account plus its active squad and membership there in a
    SINGLE query (every request pays this; on the live DB each round trip costs
    ~100ms+). None if unauthenticated. The loaded rows land in the session's identity
    map, so later `session.get(SquadDB, ...)` calls for them are free."""
    cookie = request.cookies.get(SESSION_COOKIE)
    account_id = verify_session(cookie)
    if account_id is None:
        return None
    row = session.exec(
        select(AccountDB, SquadDB, SquadMembershipDB)
        .where(AccountDB.id == account_id)
        .join(SquadDB, SquadDB.id == AccountDB.squad_id, isouter=True)  # type: ignore[arg-type]
        .join(
            SquadMembershipDB,
            and_(
                SquadMembershipDB.squad_id == AccountDB.squad_id,  # type: ignore[arg-type]
                SquadMembershipDB.account_id == AccountDB.id,  # type: ignore[arg-type]
            ),
            isouter=True,
        )
    ).first()
    if row is None:
        return None
    account, squad, membership = row
    if account.status != "active":
        return None
    # Session-epoch gate: a token minted before the account's epoch was bumped
    # (via reclaim / sign-out-everywhere) is stale even if its signature is valid.
    if (session_epoch_from(cookie) or 0) != account.session_epoch:
        return None
    return account, squad, membership


def _account_from_request(request: Request, session: Session) -> AccountDB | None:
    """Resolve the active account from the session cookie, or None if unauthenticated."""
    loaded = _load_from_request(request, session)
    return loaded[0] if loaded else None


def get_current_account(
    request: Request, session: Session = Depends(get_session)
) -> AccountDB:
    """The authenticated account, or 401. Used by the auth router (/me, /logout)."""
    account = _account_from_request(request, session)
    if account is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return account


# ── Roles → capabilities (T3.2 assistant coach mode) ───────────────────────────
# Routes require a capability, never a role, so later phases only change this map.
# "view" is implied by any membership (plain `get_current_squad`).
# "author_plan" = create a match / tournament, then edit and run the ones YOU created
# (per-row check: `editable_match` / `editable_tournament`). "edit_plan" and
# "run_matchday" are the unrestricted versions — any plan on the team (head only).
HEAD_CAPS = frozenset(
    {"view", "author_plan", "run_matchday", "comment", "propose", "edit_plan",
     "manage_squad", "manage_team"}
)
ROLE_CAPS: dict[str, frozenset[str]] = {
    HEAD: HEAD_CAPS,
    ASSISTANT: frozenset({"view", "author_plan"}),
}


@dataclass
class SquadAccess:
    """The squad a request operates on, plus the caller's role on it."""

    squad: SquadDB
    role: str
    account: AccountDB | None = None  # None when auth is off (single-user dev)

    def can(self, cap: str) -> bool:
        return cap in ROLE_CAPS.get(self.role, frozenset())

    @property
    def account_id(self) -> int | None:
        return self.account.id if self.account else None

    def can_edit(self, created_by_account_id: int | None) -> bool:
        """May the caller change / run a plan created by `created_by_account_id`?
        The head coach: always. An assistant: only a plan they created themselves."""
        if self.can("edit_plan"):
            return True
        return (
            self.can("author_plan")
            and self.account_id is not None
            and created_by_account_id == self.account_id
        )


def get_squad_access(
    request: Request, session: Session = Depends(get_session)
) -> SquadAccess:
    """The entire data-isolation seam: the account's active squad and its role there.

    Auth off → the single default squad as head (single-user behaviour). Auth on →
    the authenticated account's active squad, else 401. If the account has lost access
    to its active squad (removed as an assistant, team deleted), it is re-pointed to
    another team it can access rather than locked out.
    """
    if not auth_enabled():
        return SquadAccess(squad=get_or_create_squad(session), role=HEAD)
    loaded = _load_from_request(request, session)
    if loaded is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    account, squad, membership = loaded
    if membership is not None and squad is not None:
        return SquadAccess(squad=squad, role=membership.role, account=account)  # fast path

    # Slow path (rare): a legacy owner without a membership row yet, or an account
    # that lost access to its active team. Adopt / re-point, then resolve again.
    membership = get_membership(session, account.squad_id, account.id)  # type: ignore[arg-type]
    if membership is None:
        repoint_active_squad(session, account, exclude_squad_id=account.squad_id)
        session.commit()
        membership = get_membership(session, account.squad_id, account.id)  # type: ignore[arg-type]
    elif session.info.pop("memberships_changed", False):
        session.commit()  # persist a lazily-adopted legacy head membership
    squad = session.get(SquadDB, account.squad_id)
    if squad is None or membership is None:
        raise HTTPException(status_code=401, detail="Account has no squad")
    return SquadAccess(squad=squad, role=membership.role, account=account)


def get_current_squad(access: SquadAccess = Depends(get_squad_access)) -> SquadDB:
    """The active squad for read-only ("view") routes — any role may call these."""
    return access.squad


def require(cap: str) -> Callable[..., SquadDB]:
    """Dependency factory for write routes: the active squad, or 403 if the caller's
    role on it lacks `cap`. Tagged with `_capability` so the route-coverage test can
    prove every write route declares one (deny by default)."""

    def _dep(access: SquadAccess = Depends(get_squad_access)) -> SquadDB:
        if not access.can(cap):
            raise HTTPException(status_code=403, detail="Only the head coach can do that")
        return access.squad

    _dep._capability = cap  # type: ignore[attr-defined]
    _dep.__name__ = f"require_{cap}"
    return _dep


def plan_access(access: SquadAccess = Depends(get_squad_access)) -> SquadAccess:
    """Dependency for plan write routes (matches / tournaments). Passing it only means
    the caller may author plans at all — every route touching an EXISTING row must
    ALSO depend on `editable_match` / `editable_tournament`, which is what stops one
    assistant changing another coach's plan (enforced by the route-coverage test)."""
    if not access.can("author_plan"):
        raise HTTPException(status_code=403, detail="Only the head coach can do that")
    return access


plan_access._capability = "author_plan"  # type: ignore[attr-defined]


# ── Ownership guards (IDOR defence) ─────────────────────────────────────────────
def owned_squad(squad_id: int, account: AccountDB, session: Session) -> SquadDB:
    """The squad iff the account is a member of it (any role) — the single access
    check for the teams router."""
    squad = session.get(SquadDB, squad_id)
    if not squad or get_membership(session, squad_id, account.id) is None:  # type: ignore[arg-type]
        raise HTTPException(status_code=404, detail="Team not found")
    return squad


def headed_squad(squad_id: int, account: AccountDB, session: Session) -> SquadDB:
    """The squad iff the account is its head coach (404 if not a member, 403 if an
    assistant) — for team-level actions like delete."""
    squad = owned_squad(squad_id, account, session)
    membership = get_membership(session, squad_id, account.id)  # type: ignore[arg-type]
    if membership is None or membership.role != HEAD:
        raise HTTPException(status_code=403, detail="Only the head coach can do that")
    return squad


def owned_match(match_id: int, squad: SquadDB, session: Session) -> MatchDB:
    match = session.get(MatchDB, match_id)
    if not match or match.squad_id != squad.id:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


def owned_tournament(tournament_id: int, squad: SquadDB, session: Session) -> TournamentDB:
    tournament = session.get(TournamentDB, tournament_id)
    if not tournament or tournament.squad_id != squad.id:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return tournament


def owned_player(player_id: int, squad: SquadDB, session: Session) -> PlayerDB:
    player = session.get(PlayerDB, player_id)
    if not player or player.squad_id != squad.id:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


# ── Plan authorship (assistant-created plans) ───────────────────────────────────
_NOT_YOUR_PLAN = "Only the head coach or the coach who created this plan can change it"


def editable_match(
    match_id: int,
    access: SquadAccess = Depends(plan_access),
    session: Session = Depends(get_session),
) -> MatchDB:
    """DEPENDENCY for every write route addressing a match: the match iff it is on the
    caller's squad (404) AND the caller may change it (403) — the head coach, or the
    assistant who created it. A dependency (not an in-route call) so it runs before
    body validation and the route-coverage test can prove each route has it."""
    match = owned_match(match_id, access.squad, session)
    if not access.can_edit(match.created_by_account_id):
        raise HTTPException(status_code=403, detail=_NOT_YOUR_PLAN)
    return match


def editable_tournament(
    tournament_id: int,
    access: SquadAccess = Depends(plan_access),
    session: Session = Depends(get_session),
) -> TournamentDB:
    """DEPENDENCY for every write route addressing a tournament — see `editable_match`."""
    tournament = owned_tournament(tournament_id, access.squad, session)
    if not access.can_edit(tournament.created_by_account_id):
        raise HTTPException(status_code=403, detail=_NOT_YOUR_PLAN)
    return tournament


editable_match._row_guard = True  # type: ignore[attr-defined]
editable_tournament._row_guard = True  # type: ignore[attr-defined]


# ── Matchday control (one device runs a live match) ─────────────────────────────
def device_id(x_device_id: str | None = Header(default=None)) -> str:
    """The caller's per-device id (frontend `gaffer_device_id`), or "" if the client
    doesn't send one — see the compatibility rule in services/matchday.py."""
    return (x_device_id or "").strip()[:64]


def controlled_match(
    match: MatchDB = Depends(editable_match),
    access: SquadAccess = Depends(plan_access),
    device: str = Depends(device_id),
    session: Session = Depends(get_session),
) -> MatchDB:
    """DEPENDENCY for every route that changes a match: `editable_match`, plus — while
    the match is LIVE and another device holds control — 409 `not_controller` (the
    frontend drops to the live read-only view and offers Take control).

    A live match nobody controls yet (started before this shipped, or by a client
    with no device id) is claimed by the first device-carrying write, so control
    heals itself without anyone having to do anything."""
    if match.status == "in_progress" and device:
        if not match.controller_device_id:
            matchday.claim(match, access.account_id, device)
            session.add(match)  # committed with the route's own write
        elif not matchday.controls(match, access.account_id, device):
            same = match.controller_account_id == access.account_id
            name = matchday.controller_name(session, match)
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "not_controller",
                    "message": (
                        "This match is being run on your other device"
                        if same else f"{name} is running this match"
                    ),
                    "controller_name": name,
                    "same_account": same,
                },
            )
    return match


def authorship(
    session: Session, access: SquadAccess, creator_ids: Iterable[int | None]
) -> Callable[[int | None], dict[str, Any]]:
    """Build a `created_by_account_id -> {can_edit, created_by_name, created_by_me}`
    mapper for list/detail payloads. A name is only reported for plans made by someone
    other than the head coach (so a solo coach's lists stay unannotated, and it costs
    no query)."""
    head_id = access.squad.account_id
    wanted = {i for i in creator_ids if i is not None and i != head_id}
    names: dict[int, str] = {}
    if wanted:
        rows = session.exec(select(AccountDB).where(AccountDB.id.in_(wanted))).all()  # type: ignore[union-attr]
        names = {a.id: (a.display_name or "an assistant") for a in rows if a.id is not None}

    def describe(created_by: int | None) -> dict[str, Any]:
        return {
            "can_edit": access.can_edit(created_by),
            "created_by_name": names.get(created_by, "") if created_by is not None else "",
            "created_by_me": created_by is not None and created_by == access.account_id,
        }

    return describe
