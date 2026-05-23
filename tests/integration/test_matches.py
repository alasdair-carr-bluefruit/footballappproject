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
    assert set(slot["lineup"].keys()) == {"GK", "CB", "LM", "RM", "CF"}
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


# ── Start Match tests ──────────────────────────────────────────────────────────

def test_start_match(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")

    # Initial status is planned
    data = client.get(f"/api/matches/{match_id}").json()
    assert data["match"]["status"] == "planned"

    # Start the match
    resp = client.post(f"/api/matches/{match_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"
    assert resp.json()["current_slot"] == 0

    # Status persists
    data = client.get(f"/api/matches/{match_id}").json()
    assert data["match"]["status"] == "in_progress"


def test_start_match_idempotent(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")
    client.post(f"/api/matches/{match_id}/start")
    resp = client.post(f"/api/matches/{match_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


def test_update_progress(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    client.post(f"/api/matches/{match_id}/rotation")
    client.post(f"/api/matches/{match_id}/start")

    resp = client.post(f"/api/matches/{match_id}/progress", json={"current_slot": 3})
    assert resp.status_code == 200
    assert resp.json()["current_slot"] == 3

    # Mark completed
    resp = client.post(f"/api/matches/{match_id}/progress", json={"current_slot": 7, "status": "completed"})
    assert resp.json()["status"] == "completed"


# ── Remove / reinstate player tests ───────────────────────────────────────────

def test_remove_player_from_match(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    rotation_data = client.post(f"/api/matches/{match_id}/rotation").json()

    # Pick a bench player to remove
    bench_player = rotation_data["slots"][2]["bench"][0]
    player_id = bench_player["id"]

    resp = client.post(
        f"/api/matches/{match_id}/remove-player",
        json={"player_id": player_id, "from_slot": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert str(player_id) in data["removed_players"]
    assert data["removed_players"][str(player_id)] == 2
    # Removed player should not appear in any slot from index 2 onward
    for slot in data["slots"][2:]:
        lineup_ids = list(slot["lineup"].values())
        bench_ids = [p["id"] for p in slot["bench"]]
        assert player_id not in [p["id"] if isinstance(p, dict) else p for p in lineup_ids]


def test_reinstate_player(client: TestClient, squad_10: None) -> None:
    match_id = client.post("/api/matches/", json={"date": "2026-03-25"}).json()["id"]
    rotation_data = client.post(f"/api/matches/{match_id}/rotation").json()
    client.post(f"/api/matches/{match_id}/start")
    client.post(f"/api/matches/{match_id}/progress", json={"current_slot": 2})

    bench_player = rotation_data["slots"][2]["bench"][0]
    player_id = bench_player["id"]

    # Remove then reinstate
    client.post(
        f"/api/matches/{match_id}/remove-player",
        json={"player_id": player_id, "from_slot": 3},
    )
    resp = client.post(
        f"/api/matches/{match_id}/reinstate-player",
        json={"player_id": player_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert str(player_id) not in data["removed_players"]
