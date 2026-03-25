import json
from datetime import date as date_type
from typing import Any

from sqlmodel import Session, select

from backend.db.models import MatchDB, PlayerDB, RotationPlanDB, SquadDB
from backend.models.match import Match, Squad
from backend.models.player import GKTier, Player
from backend.models.rotation import Position, RotationPlan


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
    return Player(
        name=p.name,
        gk_status=GKTier(p.gk_status),
        def_restricted=p.def_restricted,
        skill_rating=p.skill_rating,
    )


def match_db_to_domain(m: MatchDB, players: list[PlayerDB]) -> tuple[Match, Squad]:
    match = Match(
        date=date_type.fromisoformat(m.date),
        opponent=m.opponent,
        quarters=m.quarters,
        quarter_length_mins=m.quarter_length_mins,
    )
    squad = Squad(players=[player_db_to_domain(p) for p in players])
    return match, squad


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

        slots.append({"slot_index": slot_data["slot_index"], "lineup": lineup, "bench": bench})

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
        session.add(RotationPlanDB(match_id=match_id, slots_json=slots_json, warnings_json=warnings_json))
    session.commit()
