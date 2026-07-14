"""Tournament Mode API router.

Tournaments group multiple matches played on the same day. Each match reuses
the core Match / RotationPlan infrastructure, with the addition of:
- Cross-match minute tracking (time_balancer prior_slots)
- Guest players scoped to a single tournament (source_tournament_id on PlayerDB)
- Group + knockout stages
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlmodel import Session, select

from backend.db.database import get_session
from backend.db.models import MatchDB, PlayerDB, RotationPlanDB, TournamentDB
from backend.db.repositories import (
    build_plan_response,
    delete_rotation,
    get_available_ids,
    get_goals,
    get_goals_total,
    get_or_create_squad,
    get_plan_slots,
    get_players,
    get_position_overrides,
    get_rotation,
)
from backend.db.repositories import (
    set_position_overrides as save_position_overrides,
)
from backend.models.game_config import build_tournament_config
from backend.services import match_service, tournament_service

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TournamentCreate(BaseModel):
    name: str = "Tournament"
    date: str  # ISO date e.g. "2026-04-12"
    team_size: int = 5
    formation: str = "1-2-1"
    match_duration_mins: int = 10
    has_halftime: bool = False
    fairness_value: int = 50  # 0=equal, 100=start strong
    rotation_intensity: int = 50


class TournamentRead(BaseModel):
    id: int
    name: str
    date: str
    team_size: int
    formation: str
    match_duration_mins: int
    has_halftime: bool
    fairness_value: int
    rotation_intensity: int
    status: str
    match_count: int = 0


class GuestPlayerCreate(BaseModel):
    name: str
    gk_status: str = "can_play"
    def_restricted: bool = False
    skill_rating: int = 3
    preferred_positions: list[str] = []
    best_position: str = ""
    shirt_number: int | None = None


class TournamentMatchCreate(BaseModel):
    opponent: str = ""
    stage: str = "group"  # "group" or "knockout"
    available_player_ids: list[int]  # required: coach must select players
    knockout_fairness_value: int | None = None  # override fairness for knockouts


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tournament_read(t: TournamentDB, match_count: int = 0) -> TournamentRead:
    return TournamentRead(
        id=t.id,  # type: ignore[arg-type]
        name=t.name,
        date=t.date,
        team_size=t.team_size,
        formation=t.formation,
        match_duration_mins=t.match_duration_mins,
        has_halftime=bool(t.has_halftime),
        fairness_value=t.fairness_value,
        rotation_intensity=t.rotation_intensity,
        status=t.status,
        match_count=match_count,
    )


def _match_response(
    m: MatchDB,
    slots: list[Any],
    warnings: list[str],
    removed_players: dict | None = None,
) -> dict[str, Any]:
    """Build the rotation response dict for a tournament match."""
    try:
        total_duration = m.quarters * m.quarter_length_mins
        cfg = build_tournament_config(m.team_size, m.formation, total_duration, m.quarters > 1)
        period_label = cfg.period_label
    except Exception:
        period_label = "Period"

    return {
        "match": {
            "id": m.id,
            "date": m.date,
            "opponent": m.opponent,
            "team_size": m.team_size,
            "formation": m.formation,
            "fairness": m.fairness,
            "fairness_value": m.fairness_value,
            "rotation_intensity": m.rotation_intensity,
            "period_label": period_label,
            "home_away": m.home_away,
            "opponent_goals": m.opponent_goals,
            "status": m.status,
            "current_slot": m.current_slot,
            "tournament_id": m.tournament_id,
            "tournament_stage": m.tournament_stage or "",
            "match_number": m.match_number,
        },
        "slots": slots,
        "warnings": warnings,
        "removed_players": removed_players or {},
    }


# ── Tournament CRUD ───────────────────────────────────────────────────────────

@router.get("/", response_model=list[TournamentRead])
def list_tournaments(session: Session = Depends(get_session)) -> list[TournamentRead]:
    squad = get_or_create_squad(session)
    tournaments = list(
        session.exec(
            select(TournamentDB).where(TournamentDB.squad_id == squad.id)
            .order_by(TournamentDB.date.desc())  # type: ignore[arg-type]
        ).all()
    )
    counts = {}
    for t in tournaments:
        counts[t.id] = session.exec(
            select(MatchDB).where(MatchDB.tournament_id == t.id)
        ).all().__len__()

    return [_tournament_read(t, counts.get(t.id, 0)) for t in tournaments]


@router.post("/", response_model=TournamentRead, status_code=201)
def create_tournament(
    body: TournamentCreate, session: Session = Depends(get_session),
) -> TournamentRead:
    # Validate formation
    try:
        build_tournament_config(body.team_size, body.formation, body.match_duration_mins, body.has_halftime)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    squad = get_or_create_squad(session)
    t = TournamentDB(
        squad_id=squad.id,
        name=body.name,
        date=body.date,
        team_size=body.team_size,
        formation=body.formation,
        match_duration_mins=body.match_duration_mins,
        has_halftime=1 if body.has_halftime else 0,
        fairness_value=body.fairness_value,
        rotation_intensity=body.rotation_intensity,
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return _tournament_read(t, 0)


@router.get("/{tournament_id}")
def get_tournament(
    tournament_id: int, session: Session = Depends(get_session),
) -> dict[str, Any]:
    t = session.get(TournamentDB, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")

    matches = list(
        session.exec(
            select(MatchDB).where(MatchDB.tournament_id == tournament_id)
            .order_by(MatchDB.match_number)  # type: ignore[arg-type]
        ).all()
    )
    match_ids = {m.id for m in matches}
    rotations = {
        r.match_id: r
        for r in session.exec(select(RotationPlanDB)).all()
        if r.match_id in match_ids
    }

    match_list = []
    for m in matches:
        r = rotations.get(m.id)
        our_goals = get_goals_total(session, m.id) if r else 0
        available_ids = get_available_ids(session, m.id)
        match_list.append({
            "id": m.id,
            "match_number": m.match_number,
            "opponent": m.opponent,
            "stage": m.tournament_stage or "group",
            "status": m.status,
            "has_rotation": r is not None,
            "our_goals": our_goals,
            "opponent_goals": m.opponent_goals,
            "available_player_ids": available_ids,
        })

    # Load players for this tournament (squad + guest players)
    squad = get_or_create_squad(session)
    squad_players = [
        p for p in get_players(session, squad.id)
        if p.source_tournament_id is None
    ]
    guest_players = list(
        session.exec(
            select(PlayerDB).where(PlayerDB.source_tournament_id == tournament_id)
        ).all()
    )

    def player_info(p: PlayerDB) -> dict:
        return {
            "id": p.id,
            "name": p.name,
            "skill_rating": p.skill_rating,
            "gk_status": p.gk_status,
            "preferred_positions": json.loads(p.preferred_positions) if p.preferred_positions else [],
            "best_position": p.best_position or "",
            "shirt_number": p.shirt_number,
            "is_guest": p.source_tournament_id is not None,
        }

    position_overrides = get_position_overrides(t)

    return {
        "tournament": _tournament_read(t, len(matches)),
        "matches": match_list,
        "squad_players": [player_info(p) for p in squad_players],
        "guest_players": [player_info(p) for p in guest_players],
        "position_overrides": position_overrides,
    }


@router.get("/{tournament_id}/stats")
def get_tournament_stats(
    tournament_id: int, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Return per-player slot counts and goals aggregated across all tournament matches."""
    t = session.get(TournamentDB, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")

    matches = list(session.exec(select(MatchDB).where(MatchDB.tournament_id == tournament_id)).all())

    slot_counts: dict[int, int] = defaultdict(int)
    goal_totals: dict[int, int] = defaultdict(int)

    for m in matches:
        if not get_rotation(session, m.id):
            continue
        for slot_data in get_plan_slots(session, m.id):
            for pid in slot_data.get("lineup", {}).values():
                if pid:
                    slot_counts[int(pid)] += 1
        for pid_str, count in get_goals(session, m.id).items():
            goal_totals[int(pid_str)] += count

    # Resolve player names
    squad = get_or_create_squad(session)
    all_players = get_players(session, squad.id)
    id_to_name = {p.id: p.name for p in all_players if p.id is not None}

    players_data = [
        {"name": id_to_name.get(pid, f"Player {pid}"), "slots_played": slots, "goals": goal_totals.get(pid, 0)}
        for pid, slots in slot_counts.items()
    ]
    players_data.sort(key=lambda x: (-x["slots_played"], x["name"]))

    return {"players": players_data}


class TournamentUpdate(BaseModel):
    name: str | None = None
    date: str | None = None
    team_size: int | None = None
    formation: str | None = None
    match_duration_mins: int | None = None
    has_halftime: bool | None = None
    fairness_value: int | None = None
    rotation_intensity: int | None = None


@router.put("/{tournament_id}", response_model=TournamentRead)
def update_tournament(
    tournament_id: int, body: TournamentUpdate, session: Session = Depends(get_session),
) -> TournamentRead:
    t = session.get(TournamentDB, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if body.name is not None:
        t.name = body.name
    if body.date is not None:
        t.date = body.date
    if body.team_size is not None:
        t.team_size = body.team_size
    if body.formation is not None:
        t.formation = body.formation
    if body.match_duration_mins is not None:
        t.match_duration_mins = body.match_duration_mins
    if body.has_halftime is not None:
        t.has_halftime = 1 if body.has_halftime else 0
    if body.fairness_value is not None:
        t.fairness_value = body.fairness_value
    if body.rotation_intensity is not None:
        t.rotation_intensity = body.rotation_intensity
    session.add(t)
    session.commit()
    session.refresh(t)
    count = len(list(session.exec(select(MatchDB).where(MatchDB.tournament_id == tournament_id)).all()))
    return _tournament_read(t, count)


class SetAvailablePlayersBody(BaseModel):
    available_player_ids: list[int]


@router.post("/{tournament_id}/set-available-players")
def set_available_players(
    tournament_id: int,
    body: SetAvailablePlayersBody,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Update the available player list for all planned matches and regenerate their rotations."""
    t = session.get(TournamentDB, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")

    squad = get_or_create_squad(session)
    all_players = get_players(session, squad.id)
    available_ids = set(body.available_player_ids)
    players_db = [p for p in all_players if p.id in available_ids]
    position_overrides = get_position_overrides(t)
    if position_overrides:
        players_db = tournament_service.apply_position_overrides(players_db, position_overrides)

    quarters, quarter_length_mins = tournament_service.derive_period_structure(t)
    total_duration = quarters * quarter_length_mins
    try:
        config = build_tournament_config(t.team_size, t.formation, total_duration, bool(t.has_halftime))
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    if len(players_db) < config.players_per_slot:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {config.players_per_slot} players for {t.team_size}v{t.team_size}",
        )

    planned_matches = list(session.exec(
        select(MatchDB).where(
            MatchDB.tournament_id == tournament_id,
            MatchDB.status == "planned",
        ).order_by(MatchDB.match_number)  # type: ignore[arg-type]
    ).all())

    for db_match in planned_matches:
        # Delete existing rotation plan before regenerating
        delete_rotation(session, db_match.id)
        session.commit()
        match_service.generate_and_save_rotation(session, db_match, players_db)

    return {"updated": len(planned_matches)}


class SetPositionOverridesBody(BaseModel):
    overrides: dict  # { "player_id": ["DEF", "MID"] }


@router.post("/{tournament_id}/set-position-overrides")
def set_position_overrides(
    tournament_id: int,
    body: SetPositionOverridesBody,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Store tournament-scoped position overrides for players.

    Overrides are applied during rotation generation for all matches in this
    tournament. They do not modify the player's permanent squad profile.
    """
    t = session.get(TournamentDB, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")
    save_position_overrides(session, t, body.overrides)
    return {"overrides": body.overrides}


class MatchOpponentUpdate(BaseModel):
    opponent: str


@router.patch("/{tournament_id}/matches/{match_id}/opponent")
def update_match_opponent(
    tournament_id: int,
    match_id: int,
    body: MatchOpponentUpdate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Update the opponent name for a tournament match."""
    m = session.get(MatchDB, match_id)
    if not m or m.tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Match not found in this tournament")
    m.opponent = body.opponent
    session.add(m)
    session.commit()
    return {"id": m.id, "opponent": m.opponent}


@router.delete("/{tournament_id}", status_code=204)
def delete_tournament(
    tournament_id: int, session: Session = Depends(get_session),
) -> None:
    t = session.get(TournamentDB, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Explicit ordered DELETEs — bypasses ORM flush ordering issues with PostgreSQL FKs
    match_ids = [
        m.id for m in session.exec(select(MatchDB).where(MatchDB.tournament_id == tournament_id)).all()
    ]
    if match_ids:
        for mid in match_ids:
            delete_rotation(session, mid)
        session.execute(sql_delete(MatchDB).where(MatchDB.tournament_id == tournament_id))
    session.execute(sql_delete(PlayerDB).where(PlayerDB.source_tournament_id == tournament_id))
    session.execute(sql_delete(TournamentDB).where(TournamentDB.id == tournament_id))
    session.commit()


# ── Guest players ─────────────────────────────────────────────────────────────

@router.post("/{tournament_id}/players", status_code=201)
def add_guest_player(
    tournament_id: int,
    body: GuestPlayerCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    t = session.get(TournamentDB, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")

    squad = get_or_create_squad(session)

    # Check for name collision (across all players in this squad including guests)
    existing = session.exec(
        select(PlayerDB).where(PlayerDB.squad_id == squad.id, PlayerDB.name == body.name)
    ).first()
    if existing:
        raise HTTPException(status_code=422, detail=f"A player named '{body.name}' already exists.")

    p = PlayerDB(
        squad_id=squad.id,
        name=body.name,
        gk_status=body.gk_status,
        def_restricted=body.def_restricted,
        skill_rating=body.skill_rating,
        preferred_positions=json.dumps(body.preferred_positions),
        best_position=body.best_position,
        shirt_number=body.shirt_number,
        source_tournament_id=tournament_id,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return {
        "id": p.id,
        "name": p.name,
        "skill_rating": p.skill_rating,
        "gk_status": p.gk_status,
        "preferred_positions": body.preferred_positions,
        "best_position": p.best_position,
        "shirt_number": p.shirt_number,
        "is_guest": True,
    }


@router.delete("/{tournament_id}/players/{player_id}", status_code=204)
def remove_guest_player(
    tournament_id: int, player_id: int, session: Session = Depends(get_session),
) -> None:
    p = session.get(PlayerDB, player_id)
    if not p or p.source_tournament_id != tournament_id:
        raise HTTPException(status_code=404, detail="Guest player not found in this tournament")
    session.delete(p)
    session.commit()


# ── Tournament matches ────────────────────────────────────────────────────────

@router.post("/{tournament_id}/matches")
def add_tournament_match(
    tournament_id: int,
    body: TournamentMatchCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create a match for this tournament and immediately generate its rotation."""
    t = session.get(TournamentDB, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")

    squad = get_or_create_squad(session)

    quarters, quarter_length_mins = tournament_service.derive_period_structure(t)
    fv, fairness = tournament_service.resolve_fairness(t, body.stage, body.knockout_fairness_value)

    # Auto-assign match_number
    existing_count = len(list(session.exec(
        select(MatchDB).where(MatchDB.tournament_id == tournament_id)
    ).all()))
    match_number = existing_count + 1

    db_match = MatchDB(
        squad_id=squad.id,
        date=t.date,
        opponent=body.opponent,
        quarters=quarters,
        quarter_length_mins=quarter_length_mins,
        team_size=t.team_size,
        formation=t.formation,
        fairness=fairness,
        fairness_value=fv,
        rotation_intensity=t.rotation_intensity,
        home_away="home",
        tournament_id=tournament_id,
        tournament_stage=body.stage,
        match_number=match_number,
    )
    session.add(db_match)
    session.commit()
    session.refresh(db_match)

    # Load available players (squad + guests for this tournament)
    all_players = get_players(session, squad.id)
    available_ids = set(body.available_player_ids)
    players_db = [p for p in all_players if p.id in available_ids]
    position_overrides = get_position_overrides(t)
    if position_overrides:
        players_db = tournament_service.apply_position_overrides(players_db, position_overrides)

    total_duration = quarters * quarter_length_mins
    try:
        config = build_tournament_config(t.team_size, t.formation, total_duration, bool(t.has_halftime))
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    if len(players_db) < config.players_per_slot:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {config.players_per_slot} players for {t.team_size}v{t.team_size}",
        )

    match_service.generate_and_save_rotation(session, db_match, players_db)

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    plan_data = build_plan_response(session, db_match.id, id_to_player)
    return _match_response(db_match, plan_data["slots"], plan_data["warnings"])
