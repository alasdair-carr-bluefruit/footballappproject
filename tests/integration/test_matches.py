import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

SQUAD_10 = [
    {"name": "Kai",     "gk_status": "specialist",     "def_restricted": False, "skill_rating": 4},
    {"name": "Rowan",   "gk_status": "preferred",      "def_restricted": False, "skill_rating": 3},
    {"name": "Wesley",  "gk_status": "preferred",      "def_restricted": False, "skill_rating": 3},
    {"name": "Kobe",    "gk_status": "can_play",       "def_restricted": True,  "skill_rating": 3},
    {"name": "Jago",    "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Eli",     "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Eden",    "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Jude",    "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Jackson", "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
    {"name": "Oscar",   "gk_status": "can_play",       "def_restricted": False, "skill_rating": 3},
]


@pytest.fixture()
def squad_10(client: TestClient) -> None:
    for p in SQUAD_10:
        client.post("/api/squad/players", json=p)


def test_create_match(client: TestClient) -> None:
    resp = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["opponent"] == "Rovers FC"
    assert data["has_rotation"] is False


def test_list_matches(client: TestClient) -> None:
    client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"})
    client.post("/api/matches/", json={"date": "2026-04-01", "opponent": "City FC"})
    resp = client.get("/api/matches/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_generate_rotation(client: TestClient, squad_10: None) -> None:
    match_id = client.post(
        "/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"}
    ).json()["id"]

    resp = client.post(f"/api/matches/{match_id}/rotation")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["slots"]) == 8
    slot = data["slots"][0]
    assert set(slot["lineup"].keys()) == {"GK", "DEF", "MID1", "MID2", "FWD"}
    assert len(slot["bench"]) == 5  # 10 players - 5 on pitch


def test_generate_rotation_too_few_players(client: TestClient) -> None:
    client.post(
        "/api/squad/players",
        json={"name": "Kai", "gk_status": "specialist", "def_restricted": False, "skill_rating": 4},
    )
    match_id = client.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Test"}).json()["id"]
    assert client.post(f"/api/matches/{match_id}/rotation").status_code == 400


def test_rotation_persists(client: TestClient, squad_10: None) -> None:
    match_id = client.post(
        "/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"}
    ).json()["id"]

    client.post(f"/api/matches/{match_id}/rotation")

    data = client.get(f"/api/matches/{match_id}").json()
    assert data["slots"] is not None
    assert len(data["slots"]) == 8


def test_regenerate_rotation(client: TestClient, squad_10: None) -> None:
    match_id = client.post(
        "/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers FC"}
    ).json()["id"]

    client.post(f"/api/matches/{match_id}/rotation")
    resp2 = client.post(f"/api/matches/{match_id}/rotation")
    assert resp2.status_code == 200  # idempotent — overwrites existing


def test_delete_match(client: TestClient) -> None:
    match_id = client.post(
        "/api/matches/", json={"date": "2026-03-25", "opponent": "Test"}
    ).json()["id"]

    assert client.delete(f"/api/matches/{match_id}").status_code == 204
    assert client.get(f"/api/matches/{match_id}").status_code == 404


def test_match_not_found(client: TestClient) -> None:
    assert client.get("/api/matches/999").status_code == 404
    assert client.post("/api/matches/999/rotation").status_code == 404
