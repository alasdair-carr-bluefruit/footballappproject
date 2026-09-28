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

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from backend.auth.session import session_epoch_from, verify_session
from backend.db.database import get_session
from backend.db.memberships import ASSISTANT, HEAD, get_membership, repoint_active_squad
from backend.db.models import AccountDB, MatchDB, PlayerDB, SquadDB, TournamentDB
from backend.db.repositories import get_or_create_squad
from backend.settings import SESSION_COOKIE, auth_enabled


def _account_from_request(request: Request, session: Session) -> AccountDB | None:
    """Resolve the active account from the session cookie, or None if unauthenticated."""
    cookie = request.cookies.get(SESSION_COOKIE)
    account_id = verify_session(cookie)
    if account_id is None:
        return None
    account = session.get(AccountDB, account_id)
    if not account or account.status != "active":
        return None
    # Session-epoch gate: a token minted before the account's epoch was bumped
    # (via reclaim / sign-out-everywhere) is stale even if its signature is valid.
    if (session_epoch_from(cookie) or 0) != account.session_epoch:
        return None
    return account


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
HEAD_CAPS = frozenset(
    {"view", "run_matchday", "comment", "propose", "edit_plan", "manage_squad", "manage_team"}
)
ROLE_CAPS: dict[str, frozenset[str]] = {
    HEAD: HEAD_CAPS,
    ASSISTANT: frozenset({"view"}),
}


@dataclass
class SquadAccess:
    """The squad a request operates on, plus the caller's role on it."""

    squad: SquadDB
    role: str
    account: AccountDB | None = None  # None when auth is off (single-user dev)

    def can(self, cap: str) -> bool:
        return cap in ROLE_CAPS.get(self.role, frozenset())


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
    account = _account_from_request(request, session)
    if account is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
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
