from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlmodel import Session, select

from backend.api.deps import (
    SquadAccess,
    authorship,
    controlled_match,
    device_id,
    editable_match,
    get_current_squad,
    get_squad_access,
    owned_match,
    owned_player,
    plan_access,
    require,
)
from backend.db.database import get_session
from backend.db.memberships import ASSISTANT, get_membership
from backend.db.models import AccountDB, MatchDB, SquadDB, TournamentDB
from backend.db.repositories import (
    build_plan_response,
    create_blank_plan,
    delete_rotation,
    get_available_ids,
    get_goals,
    get_players,
    get_removed,
    get_rotation,
    goal_totals_by_match,
    match_db_to_domain,
    rotations_by_match,
    set_available_ids,
    set_goals,
    set_removed,
    set_rested_ids,
)
from backend.models.game_config import (
    DEFAULT_FORMATIONS,
    PRESET_CONFIGS,
    get_config,
)
from backend.services import (
    analytics,
    match_service,
    matchday,
    notifications,
    spreadsheet_export,
)

router = APIRouter()


class MatchCreate(BaseModel):
    date: str  # ISO format e.g. "2026-03-25"
    opponent: str = ""
    quarters: int = 4
    quarter_length_mins: float = 10  # float to allow e.g. 12.5
    team_size: int = 5
    formation: str = "1-2-1"
    fairness: str = "equal"
    fairness_value: int = 0
    rotation_intensity: int = 50
    share_gk: int = 1  # 1=specialist keeper rotates for equal time, 0=in goal all match
    home_away: str = "home"
    show_timer: int = 1  # 0=hide the match clock, 1=show


class MatchRead(BaseModel):
    id: int
    date: str
    opponent: str
    quarters: int
    quarter_length_mins: float
    has_rotation: bool
    team_size: int
    formation: str
    fairness: str
    fairness_value: int
    rotation_intensity: int
    share_gk: int = 1
    home_away: str = "home"
    opponent_goals: int = 0
    own_goals: int = 0  # opposition own goals (count for us, no named scorer)
    hide_score: int = 0
    status: str = "planned"
    current_slot: int = 0
    our_goals: int = 0  # team total: player goals + opposition own goals (for match list display)
    show_timer: int = 1
    # Authorship (assistant-created plans): may the caller edit/run this match, and
    # who made it (name only set when it wasn't the head coach).
    can_edit: bool = True
    created_by_name: str = ""
    created_by_me: bool = False
    created_by_account_id: int | None = None  # the plan owner (for the head's hand-over picker)
    reviewed: bool = False  # head coach's "Reviewed ✓" mark on an assistant's plan


def plan_changed(session: Session, m: MatchDB, access: SquadAccess) -> None:
    """An assistant changed a plan the head coach had marked reviewed → the mark no
    longer describes what's there, so drop it (the head's own edits keep it). For a
    tournament match the mark lives on the tournament. Caller commits."""
    if access.can("edit_plan"):
        return
    if m.reviewed_at:
        m.reviewed_at = None
        session.add(m)
    if m.tournament_id:
        t = session.get(TournamentDB, m.tournament_id)
        if t is not None and t.reviewed_at:
            t.reviewed_at = None
            session.add(t)


def _pretty_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%-d %b")
    except ValueError:
        return iso


def _match_read(
    m: MatchDB, has_rotation: bool, our_goals: int = 0, author: dict[str, Any] | None = None,
) -> MatchRead:
    return MatchRead(
        **(author or {}),
        created_by_account_id=m.created_by_account_id,
        reviewed=bool(m.reviewed_at),
        id=m.id,  # type: ignore[arg-type]
        date=m.date,
        opponent=m.opponent,
        quarters=m.quarters,
        quarter_length_mins=m.quarter_length_mins,
        has_rotation=has_rotation,
        team_size=m.team_size,
        formation=m.formation,
        fairness=m.fairness,
        fairness_value=m.fairness_value,
        rotation_intensity=m.rotation_intensity,
        share_gk=m.share_gk,
        home_away=m.home_away,
        opponent_goals=m.opponent_goals,
        own_goals=m.own_goals,
        hide_score=m.hide_score,
        status=m.status,
        current_slot=m.current_slot,
        our_goals=our_goals,
        show_timer=m.show_timer,
    )


_rotation_response = match_service.rotation_response


@router.get("/", response_model=list[MatchRead])
def list_matches(
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(get_squad_access),
) -> list[MatchRead]:
    squad = access.squad
    matches = list(
        session.exec(
            select(MatchDB).where(
                MatchDB.squad_id == squad.id,
                MatchDB.tournament_id == None,  # noqa: E711 — season matches only
            ).order_by(MatchDB.date.desc())  # type: ignore[arg-type]
        ).all()
    )
    match_ids = {m.id for m in matches if m.id is not None}
    rotations = rotations_by_match(session, match_ids)
    goals = goal_totals_by_match(session, match_ids)
    author = authorship(session, access, (m.created_by_account_id for m in matches))
    result = []
    for m in matches:
        has_rotation = m.id in rotations
        # Team total = player goals + opposition own goals (both score for us).
        our_goals = (goals.get(m.id, 0) + m.own_goals) if has_rotation and m.id is not None else 0
        result.append(_match_read(m, has_rotation, our_goals, author(m.created_by_account_id)))
    return result


@router.post("/", response_model=MatchRead, status_code=201)
def create_match(
    match: MatchCreate,
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(plan_access),
) -> MatchRead:
    squad = access.squad
    # Validate team_size + formation combo
    try:
        get_config(match.team_size, match.formation)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    db_match = MatchDB(
        squad_id=squad.id, created_by_account_id=access.account_id, **match.model_dump()
    )
    session.add(db_match)
    session.commit()
    session.refresh(db_match)
    author = authorship(session, access, [db_match.created_by_account_id])
    return _match_read(db_match, False, author=author(db_match.created_by_account_id))


class MatchUpdate(BaseModel):
    date: str | None = None
    opponent: str | None = None
    quarters: int | None = None
    quarter_length_mins: float | None = None
    team_size: int | None = None
    formation: str | None = None
    fairness: str | None = None
    fairness_value: int | None = None
    rotation_intensity: int | None = None
    share_gk: int | None = None
    home_away: str | None = None
    show_timer: int | None = None


@router.put("/{match_id}", response_model=MatchRead)
def update_match(
    match_id: int,
    body: MatchUpdate,
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(plan_access),
    db_match: MatchDB = Depends(controlled_match),
) -> MatchRead:
    """Edit a *planned* season match's settings (the caller re-generates after)."""
    if db_match.tournament_id is not None:
        raise HTTPException(status_code=400, detail="Edit tournament matches from the tournament")
    if db_match.status != "planned":
        raise HTTPException(status_code=400, detail="Only a planned match can be edited")

    data = body.model_dump(exclude_unset=True)
    team_size = data.get("team_size", db_match.team_size)
    formation = data.get("formation", db_match.formation)
    try:
        get_config(team_size, formation)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    for key, value in data.items():
        setattr(db_match, key, value)
    plan_changed(session, db_match, access)
    session.add(db_match)
    session.commit()
    session.refresh(db_match)
    author = authorship(session, access, [db_match.created_by_account_id])
    return _match_read(
        db_match, get_rotation(session, match_id) is not None,
        author=author(db_match.created_by_account_id),
    )


@router.get("/{match_id}")
def get_match(
    match_id: int,
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(get_squad_access),
    device: str = Depends(device_id),
) -> dict[str, Any]:
    db_match = owned_match(match_id, access.squad, session)
    return _match_payload(session, db_match, access, device)


def _match_payload(
    session: Session, db_match: MatchDB, access: SquadAccess, device: str,
) -> dict[str, Any]:
    """The full match as the caller sees it: plan, goals, and — for a live match —
    who is running it (`match.controller`, None = nobody)."""
    response = _plan_payload(session, db_match, access.can_edit(db_match.created_by_account_id))
    response["match"]["controller"] = matchday.controller_info(
        session, db_match, access.account_id, device
    )
    author = authorship(session, access, [db_match.created_by_account_id])
    response["match"].update(
        {k: v for k, v in author(db_match.created_by_account_id).items() if k != "can_edit"}
    )
    return response


def _plan_payload(session: Session, db_match: MatchDB, can_edit: bool) -> dict[str, Any]:
    match_id: int = db_match.id  # type: ignore[assignment]

    if not get_rotation(session, match_id):
        return _rotation_response(db_match, [], [], can_edit)

    players = get_players(session, db_match.squad_id)
    available_ids = set(get_available_ids(session, match_id))
    if available_ids:
        players = [p for p in players if p.id in available_ids]
    id_to_player = {p.id: p for p in players if p.id is not None}
    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"], can_edit)
    response["removed_players"] = get_removed(session, match_id)
    # Stored goals keyed by player name so the frontend can restore its goalCounts
    # (without this, reopening a match shows no scorers and a subsequent save
    # would overwrite the real goals with an empty tally).
    response["goals"] = {
        id_to_player[int(pid)].name: count
        for pid, count in get_goals(session, match_id).items()
        if int(pid) in id_to_player and count > 0
    }
    return response


class RotationRequest(BaseModel):
    available_player_ids: list[int] | None = None  # None = all players
    # Not picked because the coach RESTED them (owed time later); everyone else not
    # picked is unavailable. None = leave what's stored.
    rested_player_ids: list[int] | None = None


def _save_rested(session: Session, match_id: int, body: "RotationRequest | None") -> None:
    if body is None or body.rested_player_ids is None:
        return
    picked = set(body.available_player_ids or [])
    set_rested_ids(session, match_id, [p for p in body.rested_player_ids if p not in picked])


@router.post("/{match_id}/rotation")
def generate_match_rotation(
    match_id: int,
    background: BackgroundTasks,
    body: RotationRequest | None = None,
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(plan_access),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, Any]:
    first_plan = get_rotation(session, match_id) is None

    try:
        config = match_service.build_match_config(db_match)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    all_players = get_players(session, db_match.squad_id)

    # Filter to available players if specified; fall back to stored list if no body provided
    if body and body.available_player_ids is not None:
        players_db = [p for p in all_players if p.id in set(body.available_player_ids)]
    else:
        stored_ids = get_available_ids(session, match_id)
        if stored_ids:
            players_db = [p for p in all_players if p.id in set(stored_ids)]
        else:
            players_db = all_players

    if len(players_db) < config.players_per_slot:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Need at least {config.players_per_slot} players "
                f"for {db_match.team_size}v{db_match.team_size}"
            ),
        )

    match_service.generate_and_save_rotation(session, db_match, players_db)
    _save_rested(session, match_id, body)
    plan_changed(session, db_match, access)
    session.commit()
    # An assistant's first plan for a season match → let the head coach know (a
    # tournament notifies once, when its matches are first generated).
    if first_plan and db_match.tournament_id is None and not access.can("edit_plan"):
        opponent = f"vs {db_match.opponent} " if db_match.opponent else ""
        notifications.assistant_made_plan(
            background, session, access.squad, access.account,
            what=f"{opponent}on {_pretty_date(db_match.date)}",
        )

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = {}
    return response


@router.post("/{match_id}/blank-rotation")
def create_blank_rotation(
    match_id: int,
    body: RotationRequest | None = None,
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(plan_access),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, Any]:
    """Create an empty rotation (all positions unfilled) for manual slot assignment."""

    config = match_service.build_match_config(db_match)

    all_players = get_players(session, db_match.squad_id)
    if body and body.available_player_ids is not None:
        avail_set = set(body.available_player_ids)
        players_db = [p for p in all_players if p.id in avail_set]
    else:
        # Re-use previously stored available players (e.g. when switching to manual from pitch view)
        stored_ids = get_available_ids(session, match_id)
        if stored_ids:
            avail_set = set(stored_ids)
            players_db = [p for p in all_players if p.id in avail_set]
        else:
            players_db = all_players

    num_slots = config.total_slots
    create_blank_plan(session, match_id, num_slots, [p.id for p in players_db])
    _save_rested(session, match_id, body)
    plan_changed(session, db_match, access)
    session.commit()

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], [])
    response["removed_players"] = {}
    # All slots locked so adjust_rotation never auto-fills empty slots
    response["locked_slots"] = list(range(num_slots))
    response["manual_mode"] = True
    return response


class AdjustRequest(BaseModel):
    edits: dict[int, dict[str, int]]  # {slot_index: {position_key: player_id}}
    locked_slots: list[int] = []  # additional slot indices to keep locked


@router.post("/{match_id}/adjust")
def adjust_match_rotation(
    match_id: int,
    body: AdjustRequest,
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(plan_access),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, Any]:
    """Apply manual edits and re-generate unlocked slots."""

    if not get_rotation(session, match_id):
        raise HTTPException(status_code=400, detail="No rotation exists — generate one first")

    all_players = get_players(session, db_match.squad_id)

    # Load available players for this match
    avail_ids = get_available_ids(session, match_id)
    if avail_ids:
        avail_set = set(avail_ids)
        players_db = [p for p in all_players if p.id in avail_set]
    else:
        players_db = all_players

    match, squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}

    current_plan = match_service.reconstruct_plan(
        session, match_id, squad, id_to_player, extra_locked=body.locked_slots,
    )

    # Convert edits from player IDs to player names
    edits_by_name: dict[int, dict[str, str]] = {}
    for slot_idx_str, pos_map in body.edits.items():
        slot_idx = int(slot_idx_str)
        edits_by_name[slot_idx] = {
            pos_key: id_to_player[pid].name
            for pos_key, pid in pos_map.items()
            if pid in id_to_player
        }

    new_plan, fairness_warnings = match_service.adjust_and_save(
        session, db_match, current_plan, edits_by_name, players_db, squad, match,
    )
    if body.edits:  # a no-op re-save isn't a change to the plan
        plan_changed(session, db_match, access)
        session.commit()

    # Re-read for response
    plan_data = build_plan_response(session, match_id, id_to_player)

    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["fairness_warnings"] = fairness_warnings
    # Include locked slot indices in response
    response["locked_slots"] = [s.slot_index for s in new_plan.slots if s.locked]
    return response


class GoalsSave(BaseModel):
    goals: dict[str, int]  # {player_name: goal_count}
    opponent_goals: int = 0
    # Opposition own goals (count for us, no named scorer). None = leave unchanged, so
    # a client that doesn't send it (an older cached app) can't wipe recorded ones.
    own_goals: int | None = None
    hide_score: int | None = None  # None = leave unchanged; 0/1 = set FA score-mask flag


@router.post("/{match_id}/goals")
def save_match_goals(
    match_id: int,
    body: GoalsSave,
    session: Session = Depends(get_session),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, str]:

    if not get_rotation(session, match_id):
        raise HTTPException(status_code=404, detail="No rotation for this match")

    # Convert player names to IDs for storage
    players = get_players(session, db_match.squad_id)
    name_to_id = {p.name: p.id for p in players}
    goals_by_id = {
        str(name_to_id[name]): count
        for name, count in body.goals.items()
        if name in name_to_id and count > 0
    }
    set_goals(session, match_id, goals_by_id)

    # Save opponent goals + opposition own goals on the match
    db_match.opponent_goals = body.opponent_goals
    if body.own_goals is not None:
        db_match.own_goals = max(0, body.own_goals)
    if body.hide_score is not None:
        db_match.hide_score = 1 if body.hide_score else 0
    session.add(db_match)
    session.commit()
    return {"status": "saved"}


@router.get("/stats/owed")
def get_owed_time(
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(get_current_squad),
) -> list[dict[str, Any]]:
    """Advisory season fairness: minutes each player is behind their fair share
    across finished season matches (rested counts; unavailable doesn't)."""
    return analytics.owed_minutes(session, squad.id)


@router.get("/stats/season")
def get_season_stats(
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(get_current_squad),
) -> list[dict[str, Any]]:
    """Aggregate stats across all season matches (excludes tournament matches)."""
    return analytics.season_stats(session, squad.id)


@router.get("/export/season.xlsx")
def export_season_xlsx(
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(get_current_squad),
) -> Response:
    """Season stats as a formatted .xlsx (parent/investigation-facing; no skill data)."""
    data, filename = spreadsheet_export.season_workbook(session, squad.id)
    return Response(
        content=data,
        media_type=spreadsheet_export.XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/stats/player/{player_id}")
def get_player_history(
    player_id: int,
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(get_current_squad),
) -> dict[str, Any]:
    """Return per-match history for a single player: slots, positions, goals per match."""
    player_db = owned_player(player_id, squad, session)
    return analytics.player_history(session, player_db)


@router.post("/{match_id}/start")
def start_match(
    match_id: int,
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(plan_access),
    device: str = Depends(device_id),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, Any]:
    """Mark match as in_progress. Idempotent if already started. The device that
    starts the match takes control of it, and the server clock starts with it."""
    if db_match.status == "planned":
        db_match.status = "in_progress"
        db_match.current_slot = 0
        if device:
            matchday.claim(db_match, access.account_id, device)
        matchday.set_timer(db_match, running=True, elapsed_ms=0)
        session.add(db_match)
        session.commit()
    return _live_state(session, db_match, access, device)


@router.post("/{match_id}/unstart")
def unstart_match(
    match_id: int,
    session: Session = Depends(get_session),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, Any]:
    """Revert an accidentally-started match back to planned. Only allowed when current_slot == 0."""
    if db_match.status != "in_progress":
        raise HTTPException(status_code=400, detail="Match is not in progress")
    if db_match.current_slot != 0:
        raise HTTPException(status_code=400, detail="Cannot revert — match has already progressed")
    db_match.status = "planned"
    matchday.release(db_match)
    matchday.clear_timer(db_match)
    session.add(db_match)
    session.commit()
    return {"status": db_match.status, "current_slot": db_match.current_slot}


class ProgressUpdate(BaseModel):
    current_slot: int
    status: str | None = None  # "in_progress" or "completed"


@router.post("/{match_id}/progress")
def update_progress(
    match_id: int,
    body: ProgressUpdate,
    session: Session = Depends(get_session),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, Any]:
    """Persist current slot position and optionally update match status."""
    db_match.current_slot = body.current_slot
    if body.status and body.status in ("in_progress", "completed"):
        db_match.status = body.status
    if db_match.status == "completed":
        # Full time: nobody "holds" a finished match — anyone allowed to can edit
        # the report — and the clock stops where it was.
        matchday.release(db_match)
        if db_match.timer_anchor_at is not None:
            matchday.set_timer(
                db_match, running=False, elapsed_ms=matchday.timer_elapsed_ms(db_match)
            )
    session.add(db_match)
    session.commit()
    return {"status": db_match.status, "current_slot": db_match.current_slot}


def _live_state(
    session: Session, m: MatchDB, access: SquadAccess, device: str,
) -> dict[str, Any]:
    return {
        "status": m.status,
        "current_slot": m.current_slot,
        "controller": matchday.controller_info(session, m, access.account_id, device),
        "timer": matchday.timer_info(m),
    }


class TimerUpdate(BaseModel):
    running: bool
    elapsed_ms: int


@router.put("/{match_id}/timer")
def set_match_timer(
    match_id: int,
    body: TimerUpdate,
    session: Session = Depends(get_session),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, Any]:
    """The controlling device reports the match clock (pause / resume / reset), so
    viewers and a device taking over show the same time."""
    if db_match.status != "in_progress":
        raise HTTPException(status_code=400, detail="Match is not in progress")
    matchday.set_timer(db_match, running=body.running, elapsed_ms=body.elapsed_ms)
    session.add(db_match)
    session.commit()
    return {"timer": matchday.timer_info(db_match)}


@router.post("/{match_id}/take-control")
def take_control(
    match_id: int,
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(plan_access),
    device: str = Depends(device_id),
    db_match: MatchDB = Depends(editable_match),
) -> dict[str, Any]:
    """Make THIS device the one running a live match. Open to anyone allowed to run
    it (the head coach, or the assistant whose plan it is) — on purpose, so a dead
    phone never locks the team out mid-match. The previous device's next write gets
    a 409 and drops to the live read-only view."""
    if not device:
        raise HTTPException(status_code=400, detail="Reload the app, then try again")
    if db_match.status != "in_progress":
        raise HTTPException(status_code=400, detail="Match is not in progress")
    matchday.claim(db_match, access.account_id, device)
    session.add(db_match)
    session.commit()
    return _match_payload(session, db_match, access, device)


# ── Head-coach actions on a plan: review mark + hand-over ────────────────────────
class ReviewBody(BaseModel):
    reviewed: bool = True


@router.post("/{match_id}/review")
def review_match(
    match_id: int,
    body: ReviewBody,
    session: Session = Depends(get_session),
    squad: SquadDB = Depends(require("edit_plan")),
) -> dict[str, Any]:
    """The head coach's "Reviewed ✓" mark on a plan. A mark, not a gate: an
    unreviewed plan can still be started."""
    db_match = owned_match(match_id, squad, session)
    db_match.reviewed_at = datetime.now(UTC).isoformat() if body.reviewed else None
    session.add(db_match)
    session.commit()
    return {"reviewed": bool(db_match.reviewed_at)}


class OwnerBody(BaseModel):
    account_id: int | None = None  # None = back to the head coach


def resolve_new_owner(
    session: Session, squad: SquadDB, account_id: int | None
) -> AccountDB | None:
    """The assistant a plan is being handed to (None = the head coach keeps it), or
    404 if that account isn't an assistant on this team."""
    if account_id is None or account_id == squad.account_id:
        return None
    membership = get_membership(session, squad.id, account_id)  # type: ignore[arg-type]
    if membership is None or membership.role != ASSISTANT:
        raise HTTPException(status_code=404, detail="That coach isn't an assistant on this team")
    return session.get(AccountDB, account_id)


@router.put("/{match_id}/owner", response_model=MatchRead)
def set_match_owner(
    match_id: int,
    body: OwnerBody,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
    access: SquadAccess = Depends(get_squad_access),
    squad: SquadDB = Depends(require("edit_plan")),
) -> MatchRead:
    """The head coach hands a match to an assistant (who can then plan, tinker and
    run it), or takes it back."""
    db_match = owned_match(match_id, squad, session)
    if db_match.tournament_id is not None:
        raise HTTPException(status_code=400, detail="Hand over the whole tournament instead")
    if db_match.status != "planned":
        raise HTTPException(status_code=400, detail="Only a planned match can be handed over")
    owner = resolve_new_owner(session, squad, body.account_id)
    new_id = owner.id if owner else None
    changed = new_id != db_match.created_by_account_id
    db_match.created_by_account_id = new_id
    if changed:
        db_match.reviewed_at = None
    session.add(db_match)
    session.commit()
    if changed and owner is not None:
        opponent = f"vs {db_match.opponent} " if db_match.opponent else ""
        notifications.plan_handed_over(
            background, squad, access.account, owner,
            what=f"{opponent}on {_pretty_date(db_match.date)}",
        )
    author = authorship(session, access, [db_match.created_by_account_id])
    return _match_read(
        db_match, get_rotation(session, match_id) is not None,
        author=author(db_match.created_by_account_id),
    )


class RemovePlayerRequest(BaseModel):
    player_id: int
    from_slot: int  # first slot where player should no longer appear


@router.post("/{match_id}/remove-player")
def remove_player_from_match(
    match_id: int,
    body: RemovePlayerRequest,
    session: Session = Depends(get_session),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, Any]:
    """Mark a player unavailable from a given slot onward and re-generate remaining slots."""

    if not get_rotation(session, match_id):
        raise HTTPException(status_code=400, detail="No rotation exists")

    # Track removed player
    removed = get_removed(session, match_id)
    removed[str(body.player_id)] = body.from_slot
    set_removed(session, match_id, removed)

    # Remove player from available set
    avail_ids = get_available_ids(session, match_id)
    avail_ids = [pid for pid in avail_ids if pid != body.player_id]
    set_available_ids(session, match_id, avail_ids)

    all_players = get_players(session, db_match.squad_id)
    players_db = [p for p in all_players if p.id in set(avail_ids)]

    match, domain_squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}

    # Reconstruct current plan; lock all slots before from_slot, then re-generate
    current_plan = match_service.reconstruct_plan(
        session, match_id, domain_squad, id_to_player, lock_before=body.from_slot,
    )
    new_plan, fairness_warnings = match_service.adjust_and_save(
        session, db_match, current_plan, {}, players_db, domain_squad, match,
    )

    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = removed
    response["fairness_warnings"] = fairness_warnings
    return response


class ReinstatePlayerRequest(BaseModel):
    player_id: int


@router.post("/{match_id}/reinstate-player")
def reinstate_player_in_match(
    match_id: int,
    body: ReinstatePlayerRequest,
    session: Session = Depends(get_session),
    db_match: MatchDB = Depends(controlled_match),
) -> dict[str, Any]:
    """Restore a removed player and re-generate slots from current match position."""

    if not get_rotation(session, match_id):
        raise HTTPException(status_code=400, detail="No rotation exists")

    # Remove from removed list and restore to available
    removed = get_removed(session, match_id)
    removed.pop(str(body.player_id), None)
    set_removed(session, match_id, removed)

    avail_ids = get_available_ids(session, match_id)
    if body.player_id not in avail_ids:
        avail_ids.append(body.player_id)
    set_available_ids(session, match_id, avail_ids)

    all_players = get_players(session, db_match.squad_id)
    players_db = [p for p in all_players if p.id in set(avail_ids)]

    match, domain_squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}

    # Lock all slots up to current_slot, then re-generate the rest
    current_plan = match_service.reconstruct_plan(
        session, match_id, domain_squad, id_to_player, lock_before=db_match.current_slot,
    )
    new_plan, fairness_warnings = match_service.adjust_and_save(
        session, db_match, current_plan, {}, players_db, domain_squad, match,
    )

    plan_data = build_plan_response(session, match_id, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = removed
    response["fairness_warnings"] = fairness_warnings
    return response


@router.delete("/{match_id}", status_code=204)
def delete_match(
    match_id: int,
    session: Session = Depends(get_session),
    db_match: MatchDB = Depends(editable_match),
) -> None:
    # Explicit ordered DELETEs — bypasses ORM flush ordering issues with PostgreSQL FKs
    delete_rotation(session, match_id)
    session.execute(sql_delete(MatchDB).where(MatchDB.id == match_id))
    session.commit()


# ── Game config reference endpoint ────────────────────────────────────────────

@router.get("/config/game-configs")
def get_game_configs() -> dict[str, Any]:
    """Return available team sizes, formations, and rules for the frontend."""
    configs = {}
    for team_size, formation_map in PRESET_CONFIGS.items():
        default_formation = DEFAULT_FORMATIONS[team_size]
        sample = formation_map[default_formation]
        formations = []
        for notation, cfg in formation_map.items():
            formations.append({
                "notation": notation,
                "positions": cfg.all_positions(),
            })
        configs[str(team_size)] = {
            "team_size": team_size,
            "label": f"{team_size}v{team_size}",
            "default_formation": default_formation,
            "formations": formations,
            "periods": sample.periods,
            "period_label": sample.period_label,
            "mid_period_subs": sample.mid_period_subs,
            "break_subs": sample.break_subs,
        }
    return configs
