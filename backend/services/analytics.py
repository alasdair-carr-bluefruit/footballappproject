"""Stats / history aggregation (Phase C.7).

The read-only aggregation the frontend uses for the season stats table, a single
player's match history, and the tournament stats board. Extracted from the
routers so the loops live in one place; routers keep the HTTP concerns (the
player-not-found / tournament-not-found 404s) and just call these.
"""
from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from backend.db.models import MatchDB, PlayerDB, RotationPlanDB
from backend.db.repositories import (
    get_available_ids,
    get_goals,
    get_plan_slots,
    get_players,
    get_removed,
    get_rested_ids,
    rotations_by_match,
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
    return rotations_by_match(session, {m.id for m in matches if m.id is not None})


def _empty_positions() -> dict[str, int]:
    return {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}


def _aggregate(session: Session, matches: list[MatchDB]) -> dict[int, dict[str, Any]]:
    """Per-player slot/minute/goal/position aggregation across the given matches.

    Returns {pid: {"slots_played","minutes","goals","positions","match_ids"}}.
    Minutes derive from each match's period length — one slot is half a period, so
    a slot is worth ``quarter_length_mins / 2`` minutes; summed per-match so mixed
    period lengths stay correct. Names/availability are resolved by callers.
    """
    rotations = _rotations_by_match(session, matches)
    agg: dict[int, dict[str, Any]] = {}

    def _row(pid: int) -> dict[str, Any]:
        return agg.setdefault(pid, {
            "slots_played": 0, "minutes": 0.0, "goals": 0,
            "positions": _empty_positions(), "match_ids": set(),
        })

    for m in matches:
        if m.id not in rotations:
            continue
        slot_mins = m.quarter_length_mins / 2
        for slot in get_plan_slots(session, m.id):
            for pos, pid in slot["lineup"].items():
                if not pid:
                    continue
                row = _row(int(pid))
                row["slots_played"] += 1
                row["minutes"] += slot_mins
                norm = normalize_position(pos)
                row["positions"][norm] = row["positions"].get(norm, 0) + 1
                row["match_ids"].add(m.id)
        for pid_str, count in get_goals(session, m.id).items():
            _row(int(pid_str))["goals"] += count

    return agg


def _players_from_agg(
    session: Session, squad_id: int, agg: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Resolve names and shape `_aggregate` output for the tournament boards/exports."""
    id_to_name = {p.id: p.name for p in get_players(session, squad_id) if p.id is not None}
    players_data = [
        {
            "name": id_to_name.get(pid, f"Player {pid}"),
            "matches_available": len(a["match_ids"]),
            "slots_played": a["slots_played"],
            "minutes": round(a["minutes"]),
            "goals": a["goals"],
            "positions": a["positions"],
        }
        for pid, a in agg.items()
    ]
    players_data.sort(key=lambda x: (-x["slots_played"], x["name"]))
    return players_data


# Below this many owed minutes it's noise (one slot is 5–15 minutes).
OWED_MIN_MINUTES = 5


def owed_minutes(session: Session, squad_id: int) -> list[dict[str, Any]]:
    """Advisory season-long fairness (owner decision 2026-11-24: flag, don't
    auto-adjust). For each finished season match on Equal play, the minutes played
    are shared fairly between everyone who was there OR rested; a player's debt is
    their fair share minus what they played. Unavailable players owe/are owed
    nothing for that match, and a player taken off injured is left out of it.
    Competitive matches are skipped (uneven time is the point there).

    Returns [{player_id, name, owed_mins, rested}] for players at least
    OWED_MIN_MINUTES behind, most owed first.
    """
    matches = [
        m for m in _season_matches(session, squad_id, ordered=True)
        if m.status == "completed" and (m.fairness_value or 0) <= 15
    ]
    rotations = _rotations_by_match(session, matches)
    owed: dict[int, float] = {}
    rested_count: dict[int, int] = {}
    for m in matches:
        if m.id not in rotations:
            continue
        available = set(get_available_ids(session, m.id))
        if not available:
            continue  # legacy match with no stored availability — can't tell who was there
        rested = set(get_rested_ids(session, m.id)) - available
        removed = {int(k) for k in get_removed(session, m.id)}
        share_group = (available - removed) | rested
        if not share_group:
            continue
        slot_mins = m.quarter_length_mins / 2
        played: dict[int, float] = {}
        for slot in get_plan_slots(session, m.id):
            for pid in slot["lineup"].values():
                if pid and int(pid) in share_group:
                    played[int(pid)] = played.get(int(pid), 0.0) + slot_mins
        fair = sum(played.values()) / len(share_group)
        for pid in share_group:
            owed[pid] = owed.get(pid, 0.0) + fair - played.get(pid, 0.0)
        for pid in rested:
            rested_count[pid] = rested_count.get(pid, 0) + 1

    names = {p.id: p.name for p in get_players(session, squad_id) if p.id is not None}
    rows = [
        {
            "player_id": pid, "name": names[pid],
            "owed_mins": round(mins), "rested": rested_count.get(pid, 0),
        }
        for pid, mins in owed.items()
        if pid in names and mins >= OWED_MIN_MINUTES
    ]
    rows.sort(key=lambda r: (-r["owed_mins"], r["name"]))
    return rows


def season_stats(session: Session, squad_id: int) -> list[dict[str, Any]]:
    """Aggregate per-player stats across all season matches (excludes tournaments)."""
    # Exclude guest players (source_tournament_id IS NOT NULL)
    players = [p for p in get_players(session, squad_id) if p.source_tournament_id is None]
    matches = _season_matches(session, squad_id)
    rotations = _rotations_by_match(session, matches)

    stats: dict[int, dict[str, Any]] = {
        p.id: {
            "id": p.id, "name": p.name, "matches_available": 0,
            "slots_played": 0, "minutes": 0, "goals": 0, "positions": _empty_positions(),
        }
        for p in players
    }

    # matches_available keeps its availability-based meaning (available ≠ played):
    # count matches the player was listed available for.
    for m in matches:
        if m.id not in rotations:
            continue
        available_ids = get_available_ids(session, m.id) or [p.id for p in players]
        for pid in available_ids:
            if pid in stats:
                stats[pid]["matches_available"] += 1

    # slots / minutes / goals / positions from the shared aggregator (guests excluded).
    for pid, a in _aggregate(session, matches).items():
        if pid in stats:
            stats[pid]["slots_played"] = a["slots_played"]
            stats[pid]["minutes"] = round(a["minutes"])
            stats[pid]["goals"] = a["goals"]
            stats[pid]["positions"] = a["positions"]

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


def tournament_stats(session: Session, squad_id: int, tournament_id: int) -> dict[str, Any]:
    """Per-player matches/slots/minutes/goals/positions across one tournament."""
    matches = list(session.exec(
        select(MatchDB).where(
            MatchDB.tournament_id == tournament_id,
            MatchDB.squad_id == squad_id,
        )
    ).all())
    return {"players": _players_from_agg(session, squad_id, _aggregate(session, matches))}


def all_tournament_stats(session: Session, squad_id: int) -> dict[str, Any]:
    """Same shape as `tournament_stats`, aggregated across this squad's tournament matches."""
    matches = list(session.exec(
        select(MatchDB).where(
            MatchDB.tournament_id != None,  # noqa: E711 — all tournament matches
            MatchDB.squad_id == squad_id,
        )
    ).all())
    return {"players": _players_from_agg(session, squad_id, _aggregate(session, matches))}
