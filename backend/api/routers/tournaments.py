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
from sqlmodel import Session, select

from backend.algorithm.rotation_engine import generate_rotation
from backend.db.database import get_session
from backend.db.models import MatchDB, PlayerDB, RotationPlanDB, TournamentDB
from backend.db.repositories import (
    get_or_create_squad,
    get_players,
    match_db_to_domain,
    rotation_plan_from_json,
    save_rotation,
)
from backend.models.game_config import build_tournament_config

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


def _compute_prior_slots(
    session: Session, tournament_id: int, exclude_match_id: int, players_db: list[PlayerDB],
) -> dict[str, int]:
    """Return {player_name: slots_played} across all OTHER completed matches in tournament."""
    id_to_name = {p.id: p.name for p in players_db if p.id is not None}
    prior_counts: dict = defaultdict(int)

    prev_matches = session.exec(
        select(MatchDB).where(
            MatchDB.tournament_id == tournament_id,
            MatchDB.id != exclude_match_id,
        )
    ).all()

    for prev_m in prev_matches:
        plan_db = session.exec(
            select(RotationPlanDB).where(RotationPlanDB.match_id == prev_m.id)
        ).first()
        if not plan_db:
            continue
        for slot_data in json.loads(plan_db.slots_json):
            for pid in slot_data["lineup"].values():
                if pid in id_to_name:
                    prior_counts[id_to_name[pid]] += 1

    return dict(prior_counts)


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
        our_goals = 0
        if r and r.goals_json and r.goals_json != "{}":
            our_goals = sum(json.loads(r.goals_json).values())
        match_list.append({
            "id": m.id,
            "match_number": m.match_number,
            "opponent": m.opponent,
            "stage": m.tournament_stage or "group",
            "status": m.status,
            "has_rotation": r is not None,
            "our_goals": our_goals,
            "opponent_goals": m.opponent_goals,
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

    return {
        "tournament": _tournament_read(t, len(matches)),
        "matches": match_list,
        "squad_players": [player_info(p) for p in squad_players],
        "guest_players": [player_info(p) for p in guest_players],
    }


@router.delete("/{tournament_id}", status_code=204)
def delete_tournament(
    tournament_id: int, session: Session = Depends(get_session),
) -> None:
    t = session.get(TournamentDB, tournament_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tournament not found")

    # Cascade: delete rotation plans, matches, guest players
    matches = list(session.exec(select(MatchDB).where(MatchDB.tournament_id == tournament_id)).all())
    for m in matches:
        rotation = session.exec(
            select(RotationPlanDB).where(RotationPlanDB.match_id == m.id)
        ).first()
        if rotation:
            session.delete(rotation)
        session.delete(m)

    guest_players = list(
        session.exec(select(PlayerDB).where(PlayerDB.source_tournament_id == tournament_id)).all()
    )
    for p in guest_players:
        session.delete(p)

    session.delete(t)
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

    # Determine period structure from tournament settings
    has_halftime = bool(t.has_halftime)
    if has_halftime:
        quarters = 2
        quarter_length_mins = max(1, t.match_duration_mins // 2)
    else:
        quarters = 1
        quarter_length_mins = t.match_duration_mins

    # Fairness: knockouts can override
    fv = body.knockout_fairness_value if (body.stage == "knockout" and body.knockout_fairness_value is not None) else t.fairness_value
    fairness = "competitive" if fv > 15 else "equal"

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

    total_duration = quarters * quarter_length_mins
    try:
        config = build_tournament_config(t.team_size, t.formation, total_duration, has_halftime)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    if len(players_db) < config.players_per_slot:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {config.players_per_slot} players for {t.team_size}v{t.team_size}",
        )

    match_domain, squad_domain = match_db_to_domain(db_match, players_db)

    # Cross-match fairness: load prior slot counts from earlier tournament matches
    prior_by_name = _compute_prior_slots(session, tournament_id, db_match.id, players_db)
    prior_slots_for_algo = None
    if prior_by_name:
        player_name_map = {p.name: p for p in squad_domain.available}
        prior_slots_for_algo = {
            player_name_map[name]: count
            for name, count in prior_by_name.items()
            if name in player_name_map
        }

    plan = generate_rotation(squad_domain, match_domain, prior_slots=prior_slots_for_algo)
    save_rotation(session, db_match.id, plan, players_db)

    # Store available player IDs on the rotation plan
    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == db_match.id)
    ).first()
    assert rotation is not None
    rotation.available_player_ids_json = json.dumps([p.id for p in players_db])
    session.add(rotation)
    session.commit()

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)
    return _match_response(db_match, plan_data["slots"], plan_data["warnings"])
