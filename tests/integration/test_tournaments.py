import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

SQUAD_10 = [
    {"name": "Kai",     "gk_status": "specialist", "def_restricted": False, "skill_rating": 4},
    {"name": "Rowan",   "gk_status": "preferred",  "def_restricted": False, "skill_rating": 3},
    {"name": "Wesley",  "gk_status": "preferred",  "def_restricted": False, "skill_rating": 3},
    {"name": "Kobe",    "gk_status": "can_play",   "def_restricted": True,  "skill_rating": 3},
    {"name": "Jago",    "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Eli",     "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Eden",    "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Jude",    "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Jackson", "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
    {"name": "Oscar",   "gk_status": "can_play",   "def_restricted": False, "skill_rating": 3},
]

TOURNAMENT_BASE = {
    "name": "Easter Cup",
    "date": "2026-04-12",
    "team_size": 5,
    "formation": "1-2-1",
    "match_duration_mins": 10,
    "has_halftime": False,
    "fairness_value": 50,
    "rotation_intensity": 50,
}


@pytest.fixture()
def squad_10(client: TestClient) -> None:
    for p in SQUAD_10:
        client.post("/api/squad/players", json=p)


@pytest.fixture()
def tournament(client: TestClient) -> dict:
    resp = client.post("/api/tournaments/", json=TOURNAMENT_BASE)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture()
def squad_ids(client: TestClient, squad_10: None) -> list[int]:
    return [p["id"] for p in client.get("/api/squad/players").json()]


# ── CRUD ──────────────────────────────────────────────────────────────────────

def test_create_tournament(client: TestClient) -> None:
    resp = client.post("/api/tournaments/", json=TOURNAMENT_BASE)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Easter Cup"
    assert data["team_size"] == 5
    assert data["has_halftime"] is False
    assert data["status"] == "active"


def test_list_tournaments(client: TestClient, tournament: dict) -> None:
    resp = client.get("/api/tournaments/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == tournament["id"]


def test_get_tournament(client: TestClient, tournament: dict, squad_10: None) -> None:
    resp = client.get(f"/api/tournaments/{tournament['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert "tournament" in data
    assert "matches" in data
    assert "squad_players" in data
    assert "guest_players" in data
    assert len(data["squad_players"]) == 10


def test_get_tournament_not_found(client: TestClient) -> None:
    assert client.get("/api/tournaments/999").status_code == 404


def test_delete_tournament(client: TestClient, tournament: dict) -> None:
    tid = tournament["id"]
    assert client.delete(f"/api/tournaments/{tid}").status_code == 204
    assert client.get(f"/api/tournaments/{tid}").status_code == 404


# ── Guest players ─────────────────────────────────────────────────────────────

def test_add_guest_player(client: TestClient, tournament: dict) -> None:
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/players",
        json={"name": "Guest McGee", "gk_status": "can_play", "skill_rating": 3},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Guest McGee"
    assert data["is_guest"] is True


def test_guest_player_not_in_main_squad(client: TestClient, tournament: dict) -> None:
    client.post(
        f"/api/tournaments/{tournament['id']}/players",
        json={"name": "Guest McGee", "gk_status": "can_play", "skill_rating": 3},
    )
    squad = client.get("/api/squad/players").json()
    assert all(p["name"] != "Guest McGee" for p in squad)


def test_guest_player_appears_in_tournament(client: TestClient, tournament: dict) -> None:
    client.post(
        f"/api/tournaments/{tournament['id']}/players",
        json={"name": "Guest McGee", "gk_status": "can_play", "skill_rating": 3},
    )
    data = client.get(f"/api/tournaments/{tournament['id']}").json()
    assert any(p["name"] == "Guest McGee" for p in data["guest_players"])


def test_remove_guest_player(client: TestClient, tournament: dict) -> None:
    tid = tournament["id"]
    pid = client.post(
        f"/api/tournaments/{tid}/players",
        json={"name": "Guest", "gk_status": "can_play", "skill_rating": 3},
    ).json()["id"]
    assert client.delete(f"/api/tournaments/{tid}/players/{pid}").status_code == 204
    data = client.get(f"/api/tournaments/{tid}").json()
    assert all(p["id"] != pid for p in data["guest_players"])


def test_delete_tournament_removes_guest_players(
    client: TestClient, tournament: dict
) -> None:
    """Guest players are cascade-deleted with the tournament."""
    tid = tournament["id"]
    guest_id = client.post(
        f"/api/tournaments/{tid}/players",
        json={"name": "Guest", "gk_status": "can_play", "skill_rating": 3},
    ).json()["id"]

    client.delete(f"/api/tournaments/{tid}")
    # Guest player should not appear in the main squad either
    squad = client.get("/api/squad/players").json()
    assert all(p["id"] != guest_id for p in squad)


# ── Match generation ──────────────────────────────────────────────────────────

def test_add_tournament_match(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Lions FC", "stage": "group", "available_player_ids": squad_ids},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["match"]["tournament_id"] == tournament["id"]
    assert data["match"]["tournament_stage"] == "group"
    assert data["match"]["match_number"] == 1
    # 5v5 no-halftime = 2 slots
    assert len(data["slots"]) == 2


def test_tournament_match_not_in_season_list(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Lions FC", "stage": "group", "available_player_ids": squad_ids},
    )
    season_matches = client.get("/api/matches/").json()
    assert len(season_matches) == 0


def test_tournament_match_not_in_season_stats(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Lions FC", "stage": "group", "available_player_ids": squad_ids},
    )
    stats = client.get("/api/matches/stats/season").json()
    assert all(s["matches_available"] == 0 for s in stats)


def test_add_multiple_matches_increments_match_number(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    for opponent in ["Lions", "Tigers", "Bears"]:
        client.post(
            f"/api/tournaments/{tournament['id']}/matches",
            json={"opponent": opponent, "stage": "group", "available_player_ids": squad_ids},
        )
    data = client.get(f"/api/tournaments/{tournament['id']}").json()
    numbers = [m["match_number"] for m in data["matches"]]
    assert numbers == [1, 2, 3]


def test_knockout_match_stage(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={
            "opponent": "Final Opponent",
            "stage": "knockout",
            "available_player_ids": squad_ids,
            "knockout_fairness_value": 80,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["match"]["tournament_stage"] == "knockout"


def test_with_halftime_gives_4_slots(client: TestClient, squad_ids: list[int]) -> None:
    tournament = client.post(
        "/api/tournaments/",
        json={**TOURNAMENT_BASE, "match_duration_mins": 20, "has_halftime": True},
    ).json()
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Rovers", "stage": "group", "available_player_ids": squad_ids},
    )
    assert len(resp.json()["slots"]) == 4


def test_cross_match_prior_slots_used(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    """Generating match 2 succeeds — prior slots from match 1 are loaded without error."""
    for _ in range(2):
        resp = client.post(
            f"/api/tournaments/{tournament['id']}/matches",
            json={"opponent": "Team", "stage": "group", "available_player_ids": squad_ids},
        )
        assert resp.status_code == 200


def test_too_few_players_rejected(client: TestClient, tournament: dict) -> None:
    resp = client.post(
        f"/api/tournaments/{tournament['id']}/matches",
        json={"opponent": "Team", "stage": "group", "available_player_ids": [1]},
    )
    assert resp.status_code == 400


def test_tournament_match_with_guest_player(
    client: TestClient, tournament: dict, squad_ids: list[int]
) -> None:
    tid = tournament["id"]
    guest_id = client.post(
        f"/api/tournaments/{tid}/players",
        json={"name": "Guest", "gk_status": "can_play", "skill_rating": 3},
    ).json()["id"]

    resp = client.post(
        f"/api/tournaments/{tid}/matches",
        json={
            "opponent": "Team",
            "stage": "group",
            "available_player_ids": squad_ids + [guest_id],
        },
    )
    assert resp.status_code == 200
