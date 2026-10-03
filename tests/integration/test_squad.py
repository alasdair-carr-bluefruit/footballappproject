import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_list_players_empty(client: TestClient) -> None:
    resp = client.get("/api/squad/players")
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_player(client: TestClient) -> None:
    resp = client.post(
        "/api/squad/players",
        json={"name": "Kai", "gk_status": "specialist", "def_restricted": False, "skill_rating": 4},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Kai"
    assert data["gk_status"] == "specialist"
    assert "id" in data


def test_update_player(client: TestClient) -> None:
    pid = client.post(
        "/api/squad/players",
        json={"name": "Kai", "gk_status": "specialist", "def_restricted": False, "skill_rating": 4},
    ).json()["id"]

    resp = client.put(
        f"/api/squad/players/{pid}",
        json={"name": "Kai Updated", "gk_status": "preferred", "def_restricted": True, "skill_rating": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Kai Updated"
    assert resp.json()["gk_status"] == "preferred"


def test_delete_player(client: TestClient) -> None:
    pid = client.post(
        "/api/squad/players",
        json={"name": "Kai", "gk_status": "specialist", "def_restricted": False, "skill_rating": 4},
    ).json()["id"]

    assert client.delete(f"/api/squad/players/{pid}").status_code == 204

    remaining = client.get("/api/squad/players").json()
    assert all(p["id"] != pid for p in remaining)


def test_player_not_found(client: TestClient) -> None:
    assert client.put(
        "/api/squad/players/999",
        json={"name": "X", "gk_status": "can_play", "def_restricted": False, "skill_rating": 3},
    ).status_code == 404
    assert client.delete("/api/squad/players/999").status_code == 404


# ── Shirt number tests ─────────────────────────────────────────────────────────

def test_shirt_number_stored_and_returned(client: TestClient) -> None:
    resp = client.post(
        "/api/squad/players",
        json={"name": "Liam", "gk_status": "emergency_only", "skill_rating": 3, "shirt_number": 7},
    )
    assert resp.status_code == 201
    assert resp.json()["shirt_number"] == 7


def test_shirt_number_optional_defaults_null(client: TestClient) -> None:
    resp = client.post(
        "/api/squad/players",
        json={"name": "Oliver", "gk_status": "emergency_only", "skill_rating": 3},
    )
    assert resp.status_code == 201
    assert resp.json()["shirt_number"] is None


def test_shirt_number_survives_update(client: TestClient) -> None:
    pid = client.post(
        "/api/squad/players",
        json={"name": "Ethan", "gk_status": "can_play", "skill_rating": 2, "shirt_number": 11},
    ).json()["id"]

    resp = client.put(
        f"/api/squad/players/{pid}",
        json={"name": "Ethan", "gk_status": "can_play", "skill_rating": 2, "shirt_number": 9},
    )
    assert resp.status_code == 200
    assert resp.json()["shirt_number"] == 9


# ── Duplicate name tests (issue #3) ───────────────────────────────────────────

def test_duplicate_player_name_rejected(client: TestClient) -> None:
    client.post(
        "/api/squad/players",
        json={"name": "Noah", "gk_status": "emergency_only", "skill_rating": 3},
    )
    resp = client.post(
        "/api/squad/players",
        json={"name": "Noah", "gk_status": "emergency_only", "skill_rating": 3},
    )
    assert resp.status_code == 422


def test_duplicate_name_ignores_case_and_spaces(client: TestClient) -> None:
    client.post("/api/squad/players", json={"name": "Sam", "gk_status": "emergency_only"})
    resp = client.post("/api/squad/players", json={"name": "  sam ", "gk_status": "emergency_only"})
    assert resp.status_code == 422
    assert "already got a player called 'Sam'" in resp.json()["detail"]


def test_new_player_name_is_trimmed(client: TestClient) -> None:
    resp = client.post("/api/squad/players", json={"name": "  Leo  ", "gk_status": "emergency_only"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "Leo"


def test_rename_to_taken_name_rejected(client: TestClient) -> None:
    client.post("/api/squad/players", json={"name": "Jamie", "gk_status": "emergency_only"})
    pid = client.post(
        "/api/squad/players", json={"name": "Roy", "gk_status": "emergency_only"}
    ).json()["id"]
    resp = client.put(f"/api/squad/players/{pid}", json={"name": "JAMIE", "gk_status": "emergency_only"})
    assert resp.status_code == 422
    # Roy is still Roy.
    names = [p["name"] for p in client.get("/api/squad/players").json()]
    assert "Roy" in names


def test_rename_changing_only_case_of_own_name_allowed(client: TestClient) -> None:
    pid = client.post(
        "/api/squad/players", json={"name": "dani", "gk_status": "emergency_only"}
    ).json()["id"]
    resp = client.put(f"/api/squad/players/{pid}", json={"name": "Dani", "gk_status": "emergency_only"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Dani"


def test_legacy_case_duplicates_can_still_be_edited(client: TestClient, session) -> None:
    """Squads saved before the case-insensitive rule may hold "Moe" and "moe"; editing
    one without renaming it must still work."""
    from sqlmodel import select

    from backend.db.models import PlayerDB

    pid = client.post("/api/squad/players", json={"name": "Moe", "gk_status": "emergency_only"}).json()["id"]
    squad_id = session.exec(select(PlayerDB).where(PlayerDB.id == pid)).one().squad_id
    session.add(PlayerDB(squad_id=squad_id, name="moe", gk_status="emergency_only"))
    session.commit()
    resp = client.put(
        f"/api/squad/players/{pid}",
        json={"name": "Moe", "gk_status": "emergency_only", "shirt_number": 7},
    )
    assert resp.status_code == 200


def test_duplicate_name_different_squads_allowed(client: TestClient) -> None:
    """Two squads can independently have a player named the same."""
    client.post(
        "/api/squad/players",
        json={"name": "Noah B", "gk_status": "emergency_only", "skill_rating": 3},
    )
    # Updating to same name within same squad should be allowed (same player)
    pid = client.post(
        "/api/squad/players",
        json={"name": "Noah C", "gk_status": "emergency_only", "skill_rating": 3},
    ).json()["id"]
    resp = client.put(
        f"/api/squad/players/{pid}",
        json={"name": "Noah C", "gk_status": "emergency_only", "skill_rating": 3},
    )
    assert resp.status_code == 200
