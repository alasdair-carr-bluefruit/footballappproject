"""Integration tests for the D.3 stats spreadsheet exports.

Assert the endpoints return a parseable .xlsx with the expected columns/totals, and
— crucially — that **no sensitive data (skill) ever appears** in the workbook, since
these sheets are handed to parents / used in investigations.
"""
import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPECTED_HEADER = ["Player", "Matches", "Slots", "Minutes", "Goals", "GK", "DEF", "MID", "FWD"]

SQUAD = [
    {"name": "Gary Keeper", "gk_status": "specialist",     "skill_rating": 3},
    {"name": "Alan Back",   "gk_status": "emergency_only", "skill_rating": 4},
    {"name": "Bob Wing",    "gk_status": "emergency_only", "skill_rating": 3},
    {"name": "Carl Mid",    "gk_status": "emergency_only", "skill_rating": 5},
    {"name": "Dan Fwd",     "gk_status": "emergency_only", "skill_rating": 2},
    {"name": "Ed Sub",      "gk_status": "emergency_only", "skill_rating": 4},
]

TOURNAMENT_BASE = {
    "name": "Easter Cup", "date": "2026-04-12", "team_size": 5, "formation": "1-2-1",
    "match_duration_mins": 10, "has_halftime": False, "fairness_value": 50, "rotation_intensity": 50,
}


def _seed_squad(client: TestClient) -> None:
    for p in SQUAD:
        client.post("/api/squad/players", json=p)


def _rows(content: bytes) -> list[list]:
    wb = openpyxl.load_workbook(io.BytesIO(content))
    return [[c.value for c in row] for row in wb.active.iter_rows()]


def _assert_valid_sheet(resp) -> list[list]:
    assert resp.status_code == 200
    assert resp.headers["content-type"] == XLSX
    assert "attachment" in resp.headers["content-disposition"]
    assert ".xlsx" in resp.headers["content-disposition"]
    rows = _rows(resp.content)
    header = next(r for r in rows if r and r[0] == "Player")
    assert header == EXPECTED_HEADER
    assert any(r and r[0] == "TOTAL" for r in rows), "expected a TOTAL row"
    # Sensitive-data guard: skill must never leak into a parent-facing sheet.
    alltext = " ".join(str(c) for r in rows for c in r if c is not None).lower()
    assert "skill" not in alltext
    return rows


def _data_rows(rows: list[list]) -> list[list]:
    return [r for r in rows if r and r[0] not in ("Player", "TOTAL") and isinstance(r[2], int)]


def test_season_export_xlsx(client: TestClient) -> None:
    _seed_squad(client)
    mid = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers"}).json()["id"]
    assert client.post(f"/api/matches/{mid}/rotation").status_code == 200

    rows = _assert_valid_sheet(client.get("/api/matches/export/season.xlsx"))

    played = [r for r in _data_rows(rows) if r[2] > 0]
    assert played, "expected at least one player with slots"
    # 10-minute quarters → one slot = 5 minutes.
    for r in played:
        assert r[3] == r[2] * 5


def test_season_export_empty_squad_still_valid(client: TestClient) -> None:
    # No matches yet — endpoint must still return a valid (header-only) workbook.
    rows = _assert_valid_sheet(client.get("/api/matches/export/season.xlsx"))
    assert next(r for r in rows if r and r[0] == "TOTAL")


def test_all_tournament_export_aggregates_across_tournaments(client: TestClient) -> None:
    _seed_squad(client)
    ids = [p["id"] for p in client.get("/api/squad/players").json()]
    tid = client.post("/api/tournaments/", json=TOURNAMENT_BASE).json()["id"]
    for opp in ["Lions", "Tigers"]:
        r = client.post(
            f"/api/tournaments/{tid}/matches",
            json={"opponent": opp, "stage": "group", "available_player_ids": ids},
        )
        assert r.status_code == 200

    rows = _assert_valid_sheet(client.get("/api/tournaments/export/all.xlsx"))
    total = next(r for r in rows if r and r[0] == "TOTAL")
    # 2 matches × 2 slots × 5 on pitch = 20 player-slots across all tournaments.
    assert total[2] == 20


def test_single_tournament_export_and_404(client: TestClient) -> None:
    _seed_squad(client)
    ids = [p["id"] for p in client.get("/api/squad/players").json()]
    tid = client.post("/api/tournaments/", json=TOURNAMENT_BASE).json()["id"]
    client.post(
        f"/api/tournaments/{tid}/matches",
        json={"opponent": "Lions", "stage": "group", "available_player_ids": ids},
    )
    _assert_valid_sheet(client.get(f"/api/tournaments/{tid}/export.xlsx"))
    assert client.get("/api/tournaments/99999/export.xlsx").status_code == 404


def test_all_tournament_stats_json_route_not_shadowed(client: TestClient) -> None:
    # /stats/all must resolve to the aggregate, not be captured by /{tournament_id}.
    resp = client.get("/api/tournaments/stats/all")
    assert resp.status_code == 200
    assert "players" in resp.json()


def test_season_stats_json_gains_minutes_and_positions(client: TestClient) -> None:
    _seed_squad(client)
    mid = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers"}).json()["id"]
    client.post(f"/api/matches/{mid}/rotation")
    stats = client.get("/api/matches/stats/season").json()
    assert stats and all("minutes" in s and "positions" in s for s in stats)
    assert all(set(s["positions"]) == {"GK", "DEF", "MID", "FWD"} for s in stats)
