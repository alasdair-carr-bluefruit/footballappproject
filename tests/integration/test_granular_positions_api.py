"""Granular positions toggle: on/off via squad info, picks never rewritten."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def _player(client: TestClient, name: str, picks: list[str]) -> int:
    r = client.post("/api/squad/players", json={
        "name": name, "gk_status": "emergency_only", "def_restricted": False,
        "skill_rating": 3, "preferred_positions": picks,
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _lefty_spots(client: TestClient) -> set[str]:
    m = client.post("/api/matches/", json={
        "date": "2026-11-28", "opponent": "X", "team_size": 9, "formation": "3-3-2",
        "fairness": "equal", "fairness_value": 0, "quarters": 2, "quarter_length_mins": 25,
    }).json()
    r = client.post(f"/api/matches/{m['id']}/rotation", json={})
    assert r.status_code == 200, r.text
    return {
        pos for s in r.json()["slots"] for pos, p in s["lineup"].items()
        if p and p["name"] == "Lefty"
    }


def test_toggle_round_trip_and_older_clients_leave_it_alone(client: TestClient):
    assert client.get("/api/squad/info").json()["granular_positions"] is False
    r = client.put("/api/squad/info", json={"team_name": "Reds", "team_logo": "",
                                             "granular_positions": True})
    assert r.json()["granular_positions"] is True
    # A rename from a client that doesn't know the field keeps the toggle.
    client.put("/api/squad/info", json={"team_name": "Reds FC", "team_logo": ""})
    info = client.get("/api/squad/info").json()
    assert info == {"team_name": "Reds FC", "team_logo": "", "granular_positions": True}
    # Flipping the toggle alone doesn't touch the name.
    client.put("/api/squad/info", json={"granular_positions": False})
    assert client.get("/api/squad/info").json()["team_name"] == "Reds FC"


def test_engine_follows_toggle_and_picks_survive_switching_off(client: TestClient):
    client.post("/api/squad/players", json={
        "name": "Keeper", "gk_status": "specialist", "def_restricted": False,
        "skill_rating": 3, "preferred_positions": ["GK"],
    })
    lefty = _player(client, "Lefty", ["LB"])
    for i in range(9):
        _player(client, f"P{i}", [])

    client.put("/api/squad/info", json={"granular_positions": True})
    assert _lefty_spots(client) <= {"LB", "GK"}

    client.put("/api/squad/info", json={"granular_positions": False})
    assert _lefty_spots(client) <= {"LB", "CB", "CB2", "RB", "GK"}
    stored = next(p for p in client.get("/api/squad/players").json() if p["id"] == lefty)
    assert stored["preferred_positions"] == ["LB"]  # nothing rewritten
