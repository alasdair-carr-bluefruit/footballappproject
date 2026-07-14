"""Tournament setup orchestration (Phase C.5).

Tournament-specific decisions — how a match's period structure and fairness are
derived from the tournament settings, and how tournament-scoped position
overrides reshape a player — live here. The actual rotation generation is shared
with season matches and lives in ``match_service``.
"""
from __future__ import annotations

import copy
import json

from backend.db.models import PlayerDB, TournamentDB


def derive_period_structure(t: TournamentDB) -> tuple[int, int]:
    """Return (quarters, quarter_length_mins) for a tournament match.

    A tournament match is a single period unless half-time is enabled, in which
    case it splits into two halves of half the duration (min 1 minute each).
    """
    if t.has_halftime:
        return 2, max(1, t.match_duration_mins // 2)
    return 1, t.match_duration_mins


def resolve_fairness(
    t: TournamentDB, stage: str, knockout_override: int | None,
) -> tuple[int, str]:
    """Return (fairness_value, fairness_label) for a new tournament match.

    Knockout matches may override the tournament's default fairness (e.g. play
    the strongest side); values above 15 mean "competitive", else "equal".
    """
    if stage == "knockout" and knockout_override is not None:
        fv = knockout_override
    else:
        fv = t.fairness_value
    return fv, ("competitive" if fv > 15 else "equal")


def apply_position_overrides(
    players_db: list[PlayerDB], overrides: dict,
) -> list[PlayerDB]:
    """Return players with tournament-scoped position overrides applied (non-mutating).

    An override replaces a player's preferred positions for this tournament only
    and re-derives the GK tier and DEF restriction from that selection, leaving
    the permanent squad profile untouched.
    """
    result = []
    for p in players_db:
        pid_str = str(p.id)
        if pid_str in overrides and overrides[pid_str]:
            p2 = copy.copy(p)
            positions = overrides[pid_str]
            p2.preferred_positions = json.dumps(positions)
            if "GK" in positions and len(positions) == 1:
                p2.gk_status = "specialist"
            elif "GK" in positions:
                p2.gk_status = "can_play"
            else:
                p2.gk_status = "emergency_only"
            p2.def_restricted = len(positions) > 0 and "DEF" not in positions
            result.append(p2)
        else:
            result.append(p)
    return result
