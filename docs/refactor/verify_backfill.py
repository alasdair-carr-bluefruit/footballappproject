"""Verify the relational backfill matches the original JSON blobs.

Compares, for every rotation plan, the table-backed repository reads
(get_plan_slots / get_goals / get_available_ids / get_removed) against the
original RotationPlanDB `*_json` columns. Works on SQLite or Postgres — just set
DATABASE_URL.

Usage:
    DATABASE_URL="postgresql://...neon-branch..." .venv/bin/python docs/refactor/verify_backfill.py

Exit code 0 = clean, 1 = mismatches found. Safe (read-only).
"""
import json
import sys
from pathlib import Path

# Allow running by file path from the repo root: put the repo root on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlmodel import Session, select

from backend.db import repositories as repo
from backend.db.database import engine
from backend.db.models import RotationPlanDB


def main() -> int:
    mismatches = 0
    checked = 0
    with Session(engine) as s:
        for p in s.exec(select(RotationPlanDB)).all():
            mid = p.match_id
            j_slots = sorted(
                (json.loads(p.slots_json or "[]")),
                key=lambda x: x["slot_index"],
            )
            j_slots = [
                {"slot_index": sd["slot_index"], "lineup": dict(sd["lineup"])}
                for sd in j_slots
            ]
            j_goals = dict(json.loads(p.goals_json or "{}"))
            j_avail = sorted(dict.fromkeys(json.loads(p.available_player_ids_json or "[]")))
            j_removed = json.loads(p.removed_players_json or "{}")

            checks = [
                ("slots", j_slots, repo.get_plan_slots(s, mid)),
                ("goals", j_goals, repo.get_goals(s, mid)),
                ("avail", j_avail, sorted(repo.get_available_ids(s, mid))),
                ("removed", j_removed, repo.get_removed(s, mid)),
            ]
            checked += 1
            for label, expected, got in checks:
                if expected != got:
                    mismatches += 1
                    print(f"  MISMATCH match={mid} {label}:\n    json={expected}\n    repo={got}")

    print(f"checked {checked} plans, {mismatches} mismatches")
    print("ROUND-TRIP CLEAN" if mismatches == 0 else "!!! MISMATCHES FOUND")
    return 0 if mismatches == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
