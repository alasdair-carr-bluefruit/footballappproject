import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from backend.algorithm.rotation_engine import generate_rotation
from backend.db.database import get_session
from backend.db.models import MatchDB, RotationPlanDB
from backend.db.repositories import (
    get_or_create_squad,
    get_players,
    match_db_to_domain,
    rotation_plan_from_json,
    save_rotation,
)
from backend.models.game_config import (
    DEFAULT_FORMATIONS, Formation, GameConfig, PRESET_CONFIGS,
    build_tournament_config, get_config,
)

router = APIRouter()


def _season_config(team_size: int, formation: str, quarters: int, quarter_length_mins: int) -> GameConfig:
    """Build a GameConfig for a season match, honouring the stored period structure."""
    try:
        preset = get_config(team_size, formation)
    except KeyError:
        preset = None

    if preset and quarters == preset.periods:
        return preset  # matches the preset exactly — nothing to override

    # Build a custom config with the user's chosen period count
    period_label = "Half" if quarters == 2 else "Quarter"
    break_subs = None if quarters == 2 else (preset.break_subs if preset else 5)
    mid_subs = preset.mid_period_subs if preset else 2
    return GameConfig(
        team_size=team_size,
        formation=Formation.parse(formation),
        periods=quarters,
        period_length_mins=quarter_length_mins,
        mid_period_subs=mid_subs,
        break_subs=break_subs,
        period_label=period_label,
    )


def _compute_prior_tournament_slots(
    session: Session, db_match: "MatchDB", players_db: list,
) -> dict[str, int]:
    """Return {player_name: slots_played} from all OTHER matches in the same tournament."""
    from collections import defaultdict
    id_to_name = {p.id: p.name for p in players_db if p.id is not None}
    prior_counts: dict = defaultdict(int)

    prev_matches = session.exec(
        select(MatchDB).where(
            MatchDB.tournament_id == db_match.tournament_id,
            MatchDB.id != db_match.id,
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


class MatchCreate(BaseModel):
    date: str  # ISO format e.g. "2026-03-25"
    opponent: str = ""
    quarters: int = 4
    quarter_length_mins: int = 10
    team_size: int = 5
    formation: str = "1-2-1"
    fairness: str = "equal"
    fairness_value: int = 0
    rotation_intensity: int = 50
    home_away: str = "home"


class MatchRead(BaseModel):
    id: int
    date: str
    opponent: str
    quarters: int
    quarter_length_mins: int
    has_rotation: bool
    team_size: int
    formation: str
    fairness: str
    fairness_value: int
    rotation_intensity: int
    home_away: str = "home"
    opponent_goals: int = 0
    status: str = "planned"
    current_slot: int = 0
    our_goals: int = 0  # sum of all player goals (for match list display)


def _match_read(m: MatchDB, has_rotation: bool, our_goals: int = 0) -> MatchRead:
    return MatchRead(
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
        home_away=m.home_away,
        opponent_goals=m.opponent_goals,
        status=m.status,
        current_slot=m.current_slot,
        our_goals=our_goals,
    )


def _rotation_response(m: MatchDB, slots: list[Any], warnings: list[str]) -> dict[str, Any]:
    try:
        if m.tournament_id:
            total_duration = m.quarters * m.quarter_length_mins
            cfg = build_tournament_config(m.team_size, m.formation, total_duration, m.quarters > 1)
        else:
            cfg = _season_config(m.team_size, m.formation, m.quarters, m.quarter_length_mins)
        period_label = cfg.period_label
    except (KeyError, Exception):
        period_label = "Quarter"
    return {
        "match": {
            "id": m.id,
            "date": m.date,
            "opponent": m.opponent,
            "team_size": m.team_size,
            "formation": m.formation,
            "fairness": m.fairness,
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
    }


@router.get("/", response_model=list[MatchRead])
def list_matches(session: Session = Depends(get_session)) -> list[MatchRead]:
    squad = get_or_create_squad(session)
    matches = list(
        session.exec(
            select(MatchDB).where(
                MatchDB.squad_id == squad.id,
                MatchDB.tournament_id == None,  # noqa: E711 — season matches only
            ).order_by(MatchDB.date.desc())  # type: ignore[arg-type]
        ).all()
    )
    match_ids = {m.id for m in matches}
    rotations = {
        r.match_id: r
        for r in session.exec(select(RotationPlanDB)).all()
        if r.match_id in match_ids
    }
    result = []
    for m in matches:
        r = rotations.get(m.id)
        our_goals = 0
        if r and r.goals_json and r.goals_json != "{}":
            our_goals = sum(json.loads(r.goals_json).values())
        result.append(_match_read(m, m.id in rotations, our_goals))
    return result


@router.post("/", response_model=MatchRead, status_code=201)
def create_match(match: MatchCreate, session: Session = Depends(get_session)) -> MatchRead:
    # Validate team_size + formation combo
    try:
        get_config(match.team_size, match.formation)
    except KeyError as e:
        raise HTTPException(status_code=422, detail=str(e))

    squad = get_or_create_squad(session)
    db_match = MatchDB(squad_id=squad.id, **match.model_dump())
    session.add(db_match)
    session.commit()
    session.refresh(db_match)
    return _match_read(db_match, False)


@router.get("/{match_id}")
def get_match(match_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if not rotation:
        return _rotation_response(db_match, [], [])

    players = get_players(session, db_match.squad_id)
    id_to_player = {p.id: p for p in players if p.id is not None}
    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = json.loads(rotation.removed_players_json)
    return response


class RotationRequest(BaseModel):
    available_player_ids: list[int] | None = None  # None = all players


@router.post("/{match_id}/rotation")
def generate_match_rotation(
    match_id: int,
    body: RotationRequest | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    if db_match.tournament_id:
        total_duration = db_match.quarters * db_match.quarter_length_mins
        try:
            config = build_tournament_config(db_match.team_size, db_match.formation, total_duration, db_match.quarters > 1)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=422, detail=str(e))
    else:
        try:
            config = _season_config(db_match.team_size, db_match.formation, db_match.quarters, db_match.quarter_length_mins)
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e))

    all_players = get_players(session, db_match.squad_id)

    # Filter to available players if specified
    if body and body.available_player_ids is not None:
        available_ids = set(body.available_player_ids)
        players_db = [p for p in all_players if p.id in available_ids]
    else:
        players_db = all_players

    if len(players_db) < config.players_per_slot:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {config.players_per_slot} players for {db_match.team_size}v{db_match.team_size}",
        )

    match, squad = match_db_to_domain(db_match, players_db)

    # For tournament matches, compute prior slot counts for cross-match fairness
    prior_slots_for_algo = None
    if db_match.tournament_id:
        prior_by_name = _compute_prior_tournament_slots(session, db_match, players_db)
        player_name_map = {p.name: p for p in squad.available}
        if prior_by_name:
            prior_slots_for_algo = {
                player_name_map[name]: count
                for name, count in prior_by_name.items()
                if name in player_name_map
            }

    plan = generate_rotation(squad, match, prior_slots=prior_slots_for_algo)

    save_rotation(session, match_id, plan, players_db)

    # Store which players were available
    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    assert rotation is not None
    rotation.available_player_ids_json = json.dumps([p.id for p in players_db])
    session.add(rotation)
    session.commit()

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = {}
    return response


@router.post("/{match_id}/blank-rotation")
def create_blank_rotation(
    match_id: int,
    body: RotationRequest | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Create an empty rotation (all positions unfilled) for manual slot assignment."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    if db_match.tournament_id:
        total_duration = db_match.quarters * db_match.quarter_length_mins
        config = build_tournament_config(db_match.team_size, db_match.formation, total_duration, db_match.quarters > 1)
    else:
        config = _season_config(db_match.team_size, db_match.formation, db_match.quarters, db_match.quarter_length_mins)

    all_players = get_players(session, db_match.squad_id)
    if body and body.available_player_ids is not None:
        avail_set = set(body.available_player_ids)
        players_db = [p for p in all_players if p.id in avail_set]
    else:
        players_db = all_players

    num_slots = config.total_slots
    slots_json = json.dumps([{"slot_index": i, "lineup": {}} for i in range(num_slots)])
    avail_ids_json = json.dumps([p.id for p in players_db])

    existing = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if existing:
        existing.slots_json = slots_json
        existing.warnings_json = "[]"
        existing.available_player_ids_json = avail_ids_json
        session.add(existing)
    else:
        session.add(RotationPlanDB(
            match_id=match_id, slots_json=slots_json, warnings_json="[]",
            available_player_ids_json=avail_ids_json,
        ))
    session.commit()

    id_to_player = {p.id: p for p in players_db if p.id is not None}
    plan_data = rotation_plan_from_json(slots_json, "[]", id_to_player)
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
    match_id: int, body: AdjustRequest, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Apply manual edits and re-generate unlocked slots."""
    from backend.algorithm.rotation_engine import adjust_rotation

    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if not rotation:
        raise HTTPException(status_code=400, detail="No rotation exists — generate one first")

    all_players = get_players(session, db_match.squad_id)

    # Load available players for this match
    avail_ids = json.loads(rotation.available_player_ids_json)
    if avail_ids:
        avail_set = set(avail_ids)
        players_db = [p for p in all_players if p.id in avail_set]
    else:
        players_db = all_players

    match, squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}

    # Reconstruct current plan as domain objects
    from backend.models.rotation import Position, RotationPlan, SlotAssignment
    slots_data = json.loads(rotation.slots_json)
    domain_players = squad.available
    player_by_name = {p.name: p for p in domain_players}

    current_slots = []
    for sd in slots_data:
        slot = SlotAssignment(slot_index=sd["slot_index"])
        for pos_key, pid in sd["lineup"].items():
            db_p = id_to_player.get(pid)
            if db_p:
                domain_p = player_by_name.get(db_p.name)
                if domain_p:
                    slot.lineup[Position(pos_key)] = domain_p
        # Mark previously locked slots
        if sd["slot_index"] in body.locked_slots:
            slot.locked = True
        current_slots.append(slot)

    current_plan = RotationPlan(slots=current_slots)

    # Convert edits from player IDs to player names
    edits_by_name: dict[int, dict[str, str]] = {}
    for slot_idx_str, pos_map in body.edits.items():
        slot_idx = int(slot_idx_str)
        edits_by_name[slot_idx] = {
            pos_key: id_to_player[pid].name
            for pos_key, pid in pos_map.items()
            if pid in id_to_player
        }

    new_plan, fairness_warnings = adjust_rotation(current_plan, edits_by_name, squad, match)

    # Save updated plan
    save_rotation(session, match_id, new_plan, players_db)

    # Re-read for response
    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    assert rotation is not None
    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)

    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["fairness_warnings"] = fairness_warnings
    # Include locked slot indices in response
    response["locked_slots"] = [s.slot_index for s in new_plan.slots if s.locked]
    return response


class GoalsSave(BaseModel):
    goals: dict[str, int]  # {player_name: goal_count}
    opponent_goals: int = 0


@router.post("/{match_id}/goals")
def save_match_goals(
    match_id: int, body: GoalsSave, session: Session = Depends(get_session),
) -> dict[str, str]:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if not rotation:
        raise HTTPException(status_code=404, detail="No rotation for this match")

    # Convert player names to IDs for storage
    players = get_players(session, db_match.squad_id)
    name_to_id = {p.name: p.id for p in players}
    goals_by_id = {
        str(name_to_id[name]): count
        for name, count in body.goals.items()
        if name in name_to_id and count > 0
    }
    rotation.goals_json = json.dumps(goals_by_id)
    session.add(rotation)

    # Save opponent goals on the match
    db_match.opponent_goals = body.opponent_goals
    session.add(db_match)

    session.commit()
    return {"status": "saved"}


@router.get("/stats/season")
def get_season_stats(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """Aggregate stats across all season matches (excludes tournament matches)."""
    squad = get_or_create_squad(session)
    # Exclude guest players (source_tournament_id IS NOT NULL)
    players = [p for p in get_players(session, squad.id) if p.source_tournament_id is None]
    matches = list(
        session.exec(
            select(MatchDB).where(
                MatchDB.squad_id == squad.id,
                MatchDB.tournament_id == None,  # noqa: E711
            )
        ).all()
    )
    rotations = {
        r.match_id: r
        for r in session.exec(select(RotationPlanDB)).all()
        if r.match_id in {m.id for m in matches}
    }

    stats: dict[int, dict[str, Any]] = {}
    for p in players:
        stats[p.id] = {  # type: ignore[index]
            "id": p.id,
            "name": p.name,
            "matches_available": 0,
            "slots_played": 0,
            "goals": 0,
        }

    for m in matches:
        r = rotations.get(m.id)
        if not r:
            continue

        # Count available players
        available_ids = json.loads(r.available_player_ids_json) if r.available_player_ids_json != "[]" else []
        if not available_ids:
            # Legacy: assume all players were available
            available_ids = [p.id for p in players]
        for pid in available_ids:
            if pid in stats:
                stats[pid]["matches_available"] += 1

        # Count slots played per player
        slots_data = json.loads(r.slots_json)
        for slot in slots_data:
            for pos, pid in slot["lineup"].items():
                if pid in stats:
                    stats[pid]["slots_played"] += 1

        # Count goals
        goals = json.loads(r.goals_json) if r.goals_json != "{}" else {}
        for pid_str, count in goals.items():
            pid = int(pid_str)
            if pid in stats:
                stats[pid]["goals"] += count

    return sorted(stats.values(), key=lambda s: s["name"])


@router.get("/stats/player/{player_id}")
def get_player_history(player_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Return per-match history for a single player: slots, positions, goals per match."""
    squad = get_or_create_squad(session)
    players = get_players(session, squad.id)
    player_db = next((p for p in players if p.id == player_id), None)
    if not player_db:
        raise HTTPException(status_code=404, detail="Player not found")

    matches = list(
        session.exec(
            select(MatchDB).where(
                MatchDB.squad_id == squad.id,
                MatchDB.tournament_id == None,  # noqa: E711 — season matches only
            ).order_by(MatchDB.date.asc())  # type: ignore[arg-type]
        ).all()
    )
    rotations = {
        r.match_id: r
        for r in session.exec(select(RotationPlanDB)).all()
        if r.match_id in {m.id for m in matches}
    }

    _pos_normalize = {"LB": "DEF", "CB": "DEF", "CB2": "DEF", "RB": "DEF",
                      "LM": "MID", "CM": "MID", "CM2": "MID", "RM": "MID", "CAM": "MID",
                      "LW": "FWD", "CF": "FWD", "CF2": "FWD", "RW": "FWD", "GK": "GK"}

    match_history = []
    totals: dict[str, Any] = {"matches_available": 0, "slots_played": 0, "goals": 0,
                               "positions": {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}}

    for m in matches:
        r = rotations.get(m.id)
        if not r:
            continue
        avail_ids = json.loads(r.available_player_ids_json) if r.available_player_ids_json != "[]" else []
        if player_id not in avail_ids and avail_ids:
            continue

        totals["matches_available"] += 1
        slots_data = json.loads(r.slots_json)
        positions_this_match: list[str] = []
        for slot in slots_data:
            for pos, pid in slot["lineup"].items():
                if pid == player_id:
                    norm = _pos_normalize.get(pos, pos)
                    positions_this_match.append(norm)
                    totals["positions"][norm] = totals["positions"].get(norm, 0) + 1

        goals_data = json.loads(r.goals_json) if r.goals_json != "{}" else {}
        player_goals = goals_data.get(str(player_id), 0)

        totals["slots_played"] += len(positions_this_match)
        totals["goals"] += player_goals

        match_history.append({
            "match_id": m.id,
            "date": m.date,
            "opponent": m.opponent or "Unknown",
            "slots_played": len(positions_this_match),
            "goals": player_goals,
            "positions": positions_this_match,
        })

    return {
        "player": {"id": player_db.id, "name": player_db.name},
        "matches": match_history,
        "totals": totals,
    }


@router.post("/{match_id}/start")
def start_match(match_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Mark match as in_progress. Idempotent if already started."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    if db_match.status == "planned":
        db_match.status = "in_progress"
        db_match.current_slot = 0
        session.add(db_match)
        session.commit()
    return {"status": db_match.status, "current_slot": db_match.current_slot}


@router.post("/{match_id}/unstart")
def unstart_match(match_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """Revert an accidentally-started match back to planned. Only allowed when current_slot == 0."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    if db_match.status != "in_progress":
        raise HTTPException(status_code=400, detail="Match is not in progress")
    if db_match.current_slot != 0:
        raise HTTPException(status_code=400, detail="Cannot revert — match has already progressed")
    db_match.status = "planned"
    session.add(db_match)
    session.commit()
    return {"status": db_match.status, "current_slot": db_match.current_slot}


class ProgressUpdate(BaseModel):
    current_slot: int
    status: str | None = None  # "in_progress" or "completed"


@router.post("/{match_id}/progress")
def update_progress(
    match_id: int, body: ProgressUpdate, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Persist current slot position and optionally update match status."""
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    db_match.current_slot = body.current_slot
    if body.status and body.status in ("in_progress", "completed"):
        db_match.status = body.status
    session.add(db_match)
    session.commit()
    return {"status": db_match.status, "current_slot": db_match.current_slot}


class RemovePlayerRequest(BaseModel):
    player_id: int
    from_slot: int  # first slot where player should no longer appear


@router.post("/{match_id}/remove-player")
def remove_player_from_match(
    match_id: int, body: RemovePlayerRequest, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Mark a player unavailable from a given slot onward and re-generate remaining slots."""
    from backend.algorithm.rotation_engine import adjust_rotation
    from backend.models.rotation import Position, RotationPlan, SlotAssignment

    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if not rotation:
        raise HTTPException(status_code=400, detail="No rotation exists")

    # Track removed player
    removed = json.loads(rotation.removed_players_json)
    removed[str(body.player_id)] = body.from_slot
    rotation.removed_players_json = json.dumps(removed)

    # Remove player from available set
    avail_ids = json.loads(rotation.available_player_ids_json)
    avail_ids = [pid for pid in avail_ids if pid != body.player_id]
    rotation.available_player_ids_json = json.dumps(avail_ids)
    session.add(rotation)
    session.commit()

    all_players = get_players(session, db_match.squad_id)
    players_db = [p for p in all_players if p.id in set(avail_ids)]

    match, squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}
    player_by_name = {p.name: p for p in squad.available}

    # Reconstruct current plan; lock all slots before from_slot
    slots_data = json.loads(rotation.slots_json)
    current_slots = []
    for sd in slots_data:
        slot = SlotAssignment(slot_index=sd["slot_index"])
        for pos_key, pid in sd["lineup"].items():
            db_p = id_to_player.get(pid)
            if db_p and db_p.name in player_by_name:
                slot.lineup[Position(pos_key)] = player_by_name[db_p.name]
        if sd["slot_index"] < body.from_slot:
            slot.locked = True
        current_slots.append(slot)

    current_plan = RotationPlan(slots=current_slots)
    new_plan, _ = adjust_rotation(current_plan, {}, squad, match)
    save_rotation(session, match_id, new_plan, players_db)

    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    assert rotation is not None
    rotation.removed_players_json = json.dumps(removed)
    rotation.available_player_ids_json = json.dumps(avail_ids)
    session.add(rotation)
    session.commit()

    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = removed
    return response


class ReinstatePlayerRequest(BaseModel):
    player_id: int


@router.post("/{match_id}/reinstate-player")
def reinstate_player_in_match(
    match_id: int, body: ReinstatePlayerRequest, session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Restore a removed player and re-generate slots from current match position."""
    from backend.algorithm.rotation_engine import adjust_rotation
    from backend.models.rotation import Position, RotationPlan, SlotAssignment

    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")

    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if not rotation:
        raise HTTPException(status_code=400, detail="No rotation exists")

    # Remove from removed list and restore to available
    removed = json.loads(rotation.removed_players_json)
    removed.pop(str(body.player_id), None)
    rotation.removed_players_json = json.dumps(removed)

    avail_ids = json.loads(rotation.available_player_ids_json)
    if body.player_id not in avail_ids:
        avail_ids.append(body.player_id)
    rotation.available_player_ids_json = json.dumps(avail_ids)
    session.add(rotation)
    session.commit()

    all_players = get_players(session, db_match.squad_id)
    players_db = [p for p in all_players if p.id in set(avail_ids)]

    match, squad = match_db_to_domain(db_match, players_db)
    id_to_player = {p.id: p for p in players_db if p.id is not None}
    player_by_name = {p.name: p for p in squad.available}

    # Lock all slots up to current_slot
    from_slot = db_match.current_slot
    slots_data = json.loads(rotation.slots_json)
    current_slots = []
    for sd in slots_data:
        slot = SlotAssignment(slot_index=sd["slot_index"])
        for pos_key, pid in sd["lineup"].items():
            db_p = id_to_player.get(pid)
            if db_p and db_p.name in player_by_name:
                slot.lineup[Position(pos_key)] = player_by_name[db_p.name]
        if sd["slot_index"] < from_slot:
            slot.locked = True
        current_slots.append(slot)

    current_plan = RotationPlan(slots=current_slots)
    new_plan, _ = adjust_rotation(current_plan, {}, squad, match)
    save_rotation(session, match_id, new_plan, players_db)

    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    assert rotation is not None
    rotation.removed_players_json = json.dumps(removed)
    rotation.available_player_ids_json = json.dumps(avail_ids)
    session.add(rotation)
    session.commit()

    plan_data = rotation_plan_from_json(rotation.slots_json, rotation.warnings_json, id_to_player)
    response = _rotation_response(db_match, plan_data["slots"], plan_data["warnings"])
    response["removed_players"] = removed
    return response


@router.delete("/{match_id}", status_code=204)
def delete_match(match_id: int, session: Session = Depends(get_session)) -> None:
    db_match = session.get(MatchDB, match_id)
    if not db_match:
        raise HTTPException(status_code=404, detail="Match not found")
    rotation = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if rotation:
        session.delete(rotation)
    session.delete(db_match)
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
