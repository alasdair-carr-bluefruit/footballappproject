import json
from collections import defaultdict
from datetime import date as date_type
from typing import Any

from sqlmodel import Session, select

from backend.db.models import MatchDB, PlayerDB, RotationPlanDB, SquadDB
from backend.models.game_config import build_tournament_config, get_config
from backend.models.match import Match, Squad
from backend.models.player import GKTier, Player
from backend.models.rotation import RotationPlan


def get_or_create_squad(session: Session) -> SquadDB:
    squad = session.exec(select(SquadDB)).first()
    if not squad:
        squad = SquadDB(name="My Squad")
        session.add(squad)
        session.commit()
        session.refresh(squad)
    return squad


def get_players(session: Session, squad_id: int) -> list[PlayerDB]:
    return list(session.exec(select(PlayerDB).where(PlayerDB.squad_id == squad_id)).all())


def player_db_to_domain(p: PlayerDB) -> Player:
    positions = json.loads(p.preferred_positions) if p.preferred_positions else []
    return Player(
        name=p.name,
        gk_status=GKTier(p.gk_status),
        def_restricted=p.def_restricted,
        skill_rating=p.skill_rating,
        preferred_positions=positions,
        best_position=p.best_position or None,
    )


def match_db_to_domain(m: MatchDB, players: list[PlayerDB]) -> tuple[Match, Squad]:
    if m.tournament_id:
        # Tournament matches use a custom config derived from stored period structure
        total_duration = m.quarters * m.quarter_length_mins
        has_halftime = m.quarters > 1
        try:
            config = build_tournament_config(m.team_size, m.formation, total_duration, has_halftime)
        except (ValueError, KeyError):
            config = None
    else:
        try:
            config = get_config(m.team_size, m.formation)
        except KeyError:
            config = None
    match = Match(
        date=date_type.fromisoformat(m.date),
        opponent=m.opponent,
        quarters=m.quarters,
        quarter_length_mins=m.quarter_length_mins,
        game_config=config,
        fairness=m.fairness,
        fairness_value=m.fairness_value,
        rotation_intensity=m.rotation_intensity,
    )
    squad = Squad(players=[player_db_to_domain(p) for p in players])
    return match, squad


def get_prior_tournament_slots(
    session: Session, tournament_id: int, exclude_match_id: int, players_db: list[PlayerDB],
) -> dict[str, int]:
    """Return {player_name: slots_played} across all OTHER matches in the tournament.

    Feeds cross-match cumulative fairness (prior_slots in the rotation engine).
    """
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


def get_previous_match_zero_slot_players(
    session: Session,
    tournament_id: int,
    current_match_number: int | None,
    players_db: list[PlayerDB],
) -> set[str]:
    """Return names of players who were available but got zero slots in the
    immediately preceding tournament match (consecutive sit-out constraint input)."""
    if not current_match_number or current_match_number <= 1:
        return set()

    prev_m = session.exec(
        select(MatchDB).where(
            MatchDB.tournament_id == tournament_id,
            MatchDB.match_number == current_match_number - 1,
        )
    ).first()
    if not prev_m:
        return set()

    plan_db = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == prev_m.id)
    ).first()
    if not plan_db:
        return set()

    id_to_name = {p.id: p.name for p in players_db if p.id is not None}
    available_ids = (
        json.loads(plan_db.available_player_ids_json) if plan_db.available_player_ids_json else []
    )
    played_ids: set = set()
    for slot_data in json.loads(plan_db.slots_json):
        played_ids.update(slot_data["lineup"].values())

    return {
        id_to_name[pid] for pid in available_ids
        if pid in id_to_name and pid not in played_ids
    }


def get_must_play_players(
    session: Session,
    tournament_id: int,
    current_match_number: int | None,
    players_db: list[PlayerDB],
    domain_players: list[Player],
) -> set[Player] | None:
    """Domain-level set of players who sat out the entire previous tournament match.

    Returns None (not an empty set) when there are none, matching the rotation
    engine's optional-parameter convention.
    """
    names = get_previous_match_zero_slot_players(
        session, tournament_id, current_match_number, players_db,
    )
    by_name = {p.name: p for p in domain_players}
    result = {by_name[n] for n in names if n in by_name}
    return result or None


def rotation_plan_to_json(plan: RotationPlan, player_name_to_id: dict[str, int]) -> str:
    slots = []
    for slot in plan.slots:
        lineup = {pos.value: player_name_to_id[player.name] for pos, player in slot.lineup.items()}
        slots.append({"slot_index": slot.slot_index, "lineup": lineup})
    return json.dumps(slots)


def rotation_plan_from_json(
    slots_json: str,
    warnings_json: str,
    id_to_player: dict[int, PlayerDB],
) -> dict[str, Any]:
    """Convert stored JSON back to the API response shape the frontend expects."""
    all_ids = set(id_to_player.keys())
    slots_data: list[dict[str, Any]] = json.loads(slots_json)
    warnings: list[str] = json.loads(warnings_json)

    def player_dict(p: PlayerDB) -> dict[str, Any]:
        return {
            "id": p.id,
            "name": p.name,
            "gk_status": p.gk_status,
            "def_restricted": p.def_restricted,
        }

    slots = []
    for slot_data in slots_data:
        lineup_ids = set(slot_data["lineup"].values())
        bench_ids = sorted(all_ids - lineup_ids, key=lambda pid: id_to_player[pid].name)

        lineup = {pos: player_dict(id_to_player[pid]) for pos, pid in slot_data["lineup"].items()}
        bench = [player_dict(id_to_player[pid]) for pid in bench_ids]
        skill_total = sum(
            id_to_player[pid].skill_rating
            for pos, pid in slot_data["lineup"].items()
            if pos != "GK"
        )

        slots.append({
            "slot_index": slot_data["slot_index"],
            "lineup": lineup,
            "bench": bench,
            "skill_total": skill_total,
        })

    return {"slots": slots, "warnings": warnings}


def save_rotation(
    session: Session,
    match_id: int,
    plan: RotationPlan,
    players_db: list[PlayerDB],
) -> None:
    player_name_to_id = {p.name: p.id for p in players_db if p.id is not None}
    slots_json = rotation_plan_to_json(plan, player_name_to_id)
    warnings_json = json.dumps(plan.warnings)

    existing = session.exec(
        select(RotationPlanDB).where(RotationPlanDB.match_id == match_id)
    ).first()
    if existing:
        existing.slots_json = slots_json
        existing.warnings_json = warnings_json
        session.add(existing)
    else:
        session.add(RotationPlanDB(
            match_id=match_id, slots_json=slots_json, warnings_json=warnings_json
        ))
    session.commit()
