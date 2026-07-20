"""Auth dependencies — the single isolation chokepoint for multi-user (v1.1).

`get_current_squad` replaces the old implicit "the one squad" (`get_or_create_squad`)
with "the squad belonging to the authenticated account". When `AUTH_ENABLED` is
off (dev/tests), it falls back to the single default squad so today's behaviour is
unchanged. The `owned_*` helpers are defence-in-depth: every id-path route must
assert the row belongs to the current squad, or a coach could read another's data
by guessing an id (IDOR).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from backend.auth.session import verify_session
from backend.db.database import get_session
from backend.db.models import AccountDB, MatchDB, PlayerDB, SquadDB, TournamentDB
from backend.db.repositories import get_or_create_squad
from backend.settings import SESSION_COOKIE, auth_enabled


def _account_from_request(request: Request, session: Session) -> AccountDB | None:
    """Resolve the active account from the session cookie, or None if unauthenticated."""
    account_id = verify_session(request.cookies.get(SESSION_COOKIE))
    if account_id is None:
        return None
    account = session.get(AccountDB, account_id)
    if not account or account.status != "active":
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


def get_current_squad(
    request: Request, session: Session = Depends(get_session)
) -> SquadDB:
    """The squad the request operates on — the entire data-isolation seam.

    Auth off → the single default squad (single-user behaviour). Auth on → the
    authenticated account's squad, else 401.
    """
    if not auth_enabled():
        return get_or_create_squad(session)
    account = _account_from_request(request, session)
    if account is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    squad = session.get(SquadDB, account.squad_id)
    if squad is None:
        raise HTTPException(status_code=401, detail="Account has no squad")
    return squad


# ── Ownership guards (IDOR defence) ─────────────────────────────────────────────
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
