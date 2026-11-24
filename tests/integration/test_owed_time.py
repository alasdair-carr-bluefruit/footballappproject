"""Advisory season fairness: rested players are owed time, unavailable ones aren't."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

NAMES = ["Ann", "Ben", "Cal", "Dee", "Eve", "Fay", "Gus", "Hal"]  # 8 players, 5v5


def _squad(client: TestClient) -> dict[str, int]:
    for n in NAMES:
        client.post("/api/squad/players", json={
            "name": n, "gk_status": "can_play", "def_restricted": False, "skill_rating": 3,
        })
    return {p["name"]: p["id"] for p in client.get("/api/squad/players").json()}


def _played_match(client: TestClient, available: list[int], rested: list[int] | None = None,
                  fairness_value: int = 0) -> int:
    m = client.post("/api/matches/", json={
        "date": "2026-11-01", "opponent": "X", "team_size": 5, "formation": "1-2-1",
        "fairness": "equal" if fairness_value <= 15 else "competitive",
        "fairness_value": fairness_value, "quarters": 4, "quarter_length_mins": 10,
    }).json()
    body: dict = {"available_player_ids": available}
    if rested is not None:
        body["rested_player_ids"] = rested
    r = client.post(f"/api/matches/{m['id']}/rotation", json=body)
    assert r.status_code == 200, r.text
    client.post(f"/api/matches/{m['id']}/progress", json={"current_slot": 7, "status": "completed"})
    return m["id"]


def _owed(client: TestClient) -> dict[str, int]:
    return {r["name"]: r["owed_mins"] for r in client.get("/api/matches/stats/owed").json()}


def test_rested_player_is_owed_their_share(client: TestClient):
    ids = _squad(client)
    everyone_but_hal = [ids[n] for n in NAMES if n != "Hal"]
    _played_match(client, everyone_but_hal, rested=[ids["Hal"]])
    # 8 slots × 5 players × 5 min = 200 player-minutes over 8 (7 there + Hal rested) = 25 each.
    owed = _owed(client)
    assert owed["Hal"] == 25
    rows = client.get("/api/matches/stats/owed").json()
    assert next(r for r in rows if r["name"] == "Hal")["rested"] == 1


def test_unavailable_player_is_not_owed(client: TestClient):
    ids = _squad(client)
    _played_match(client, [ids[n] for n in NAMES if n != "Hal"], rested=[])
    assert "Hal" not in _owed(client)


def test_competitive_and_unfinished_matches_are_ignored(client: TestClient):
    ids = _squad(client)
    _played_match(client, [ids[n] for n in NAMES if n != "Hal"], rested=[ids["Hal"]],
                  fairness_value=80)
    m = client.post("/api/matches/", json={
        "date": "2026-11-08", "opponent": "Y", "team_size": 5, "formation": "1-2-1",
        "fairness": "equal", "fairness_value": 0, "quarters": 4, "quarter_length_mins": 10,
    }).json()
    client.post(f"/api/matches/{m['id']}/rotation", json={
        "available_player_ids": [ids[n] for n in NAMES if n != "Hal"],
        "rested_player_ids": [ids["Hal"]],
    })  # planned, never played
    assert "Hal" not in _owed(client)


def test_regenerating_without_rested_keeps_stored_picks(client: TestClient):
    ids = _squad(client)
    m = client.post("/api/matches/", json={
        "date": "2026-11-01", "opponent": "X", "team_size": 5, "formation": "1-2-1",
        "fairness": "equal", "fairness_value": 0, "quarters": 4, "quarter_length_mins": 10,
    }).json()
    avail = [ids[n] for n in NAMES if n != "Hal"]
    client.post(f"/api/matches/{m['id']}/rotation",
                json={"available_player_ids": avail, "rested_player_ids": [ids["Hal"]]})
    client.post(f"/api/matches/{m['id']}/rotation", json={"available_player_ids": avail})
    client.post(f"/api/matches/{m['id']}/progress", json={"current_slot": 7, "status": "completed"})
    assert _owed(client)["Hal"] == 25
