"""Stats / history aggregation (Phase C.7).

The read-only aggregation the frontend uses for the season stats table, a single
player's match history, and the tournament stats board. Extracted from the
routers so the loops live in one place; routers keep the HTTP concerns (the
player-not-found / tournament-not-found 404s) and just call these.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlmodel import Session, select

from backend.db.models import MatchDB, PlayerDB, RotationPlanDB
from backend.db.repositories import (
    get_available_ids,
    get_goals,
    get_or_create_squad,
    get_plan_slots,
    get_players,
)
from backend.models.rotation import normalize_position


def _season_matches(session: Session, squad_id: int, *, ordered: bool = False) -> list[MatchDB]:
    stmt = select(MatchDB).where(
        MatchDB.squad_id == squad_id,
        MatchDB.tournament_id == None,  # noqa: E711 — season matches only
    )
    if ordered:
        stmt = stmt.order_by(MatchDB.date.asc())  # type: ignore[arg-type]
    return list(session.exec(stmt).all())


def _rotations_by_match(session: Session, matches: list[MatchDB]) -> dict[int, RotationPlanDB]:
    match_ids = {m.id for m in matches}
    return {
        r.match_id: r
        for r in session.exec(select(RotationPlanDB)).all()
        if r.match_id in match_ids
    }


def season_stats(session: Session) -> list[dict[str, Any]]:
    """Aggregate per-player stats across all season matches (excludes tournaments)."""
    squad = get_or_create_squad(session)
    # Exclude guest players (source_tournament_id IS NOT NULL)
    players = [p for p in get_players(session, squad.id) if p.source_tournament_id is None]
    matches = _season_matches(session, squad.id)
    rotations = _rotations_by_match(session, matches)

    stats: dict[int, dict[str, Any]] = {
        p.id: {"id": p.id, "name": p.name, "matches_available": 0, "slots_played": 0, "goals": 0}
        for p in players
    }

    for m in matches:
        if m.id not in rotations:
            continue

        # Count available players (legacy plans stored none → assume everyone)
        available_ids = get_available_ids(session, m.id) or [p.id for p in players]
        for pid in available_ids:
            if pid in stats:
                stats[pid]["matches_available"] += 1

        for slot in get_plan_slots(session, m.id):
            for _pos, pid in slot["lineup"].items():
                if pid in stats:
                    stats[pid]["slots_played"] += 1

        for pid_str, count in get_goals(session, m.id).items():
            pid = int(pid_str)
            if pid in stats:
                stats[pid]["goals"] += count

    return sorted(stats.values(), key=lambda s: s["name"])


def player_history(session: Session, player: PlayerDB) -> dict[str, Any]:
    """Per-match history for a single player: slots, positions, goals per match."""
    matches = _season_matches(session, player.squad_id, ordered=True)
    rotations = _rotations_by_match(session, matches)

    match_history = []
    totals: dict[str, Any] = {
        "matches_available": 0, "slots_played": 0, "goals": 0,
        "positions": {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0},
    }

    for m in matches:
        if m.id not in rotations:
            continue
        avail_ids = get_available_ids(session, m.id)
        if player.id not in avail_ids and avail_ids:
            continue

        totals["matches_available"] += 1
        positions_this_match: list[str] = []
        for slot in get_plan_slots(session, m.id):
            for pos, pid in slot["lineup"].items():
                if pid == player.id:
                    norm = normalize_position(pos)
                    positions_this_match.append(norm)
                    totals["positions"][norm] = totals["positions"].get(norm, 0) + 1

        player_goals = get_goals(session, m.id).get(str(player.id), 0)
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
        "player": {"id": player.id, "name": player.name},
        "matches": match_history,
        "totals": totals,
    }


def tournament_stats(session: Session, tournament_id: int) -> dict[str, Any]:
    """Per-player slot counts and goals aggregated across all matches in a tournament."""
    matches = list(session.exec(
        select(MatchDB).where(MatchDB.tournament_id == tournament_id)
    ).all())

    slot_counts: dict[int, int] = defaultdict(int)
    goal_totals: dict[int, int] = defaultdict(int)

    rotations = {
        r.match_id
        for r in session.exec(select(RotationPlanDB)).all()
        if r.match_id in {m.id for m in matches}
    }
    for m in matches:
        if m.id not in rotations:
            continue
        for slot_data in get_plan_slots(session, m.id):
            for pid in slot_data.get("lineup", {}).values():
                if pid:
                    slot_counts[int(pid)] += 1
        for pid_str, count in get_goals(session, m.id).items():
            goal_totals[int(pid_str)] += count

    # Resolve player names
    squad = get_or_create_squad(session)
    id_to_name = {p.id: p.name for p in get_players(session, squad.id) if p.id is not None}

    players_data = [
        {"name": id_to_name.get(pid, f"Player {pid}"), "slots_played": slots, "goals": goal_totals.get(pid, 0)}
        for pid, slots in slot_counts.items()
    ]
    players_data.sort(key=lambda x: (-x["slots_played"], x["name"]))
    return {"players": players_data}
