"""Multi-team management (T1.1): list / create / activate / delete, plus the
ownership (IDOR) guarantees. Runs auth-on (like test_auth.py) — the feature only
exists for real accounts. Two clients with separate cookie jars = two coaches.
"""
import pytest
from fastapi.testclient import TestClient

from backend.db.database import get_session
from main import app

pytestmark = pytest.mark.integration

ADMIN = "test-admin-key"


@pytest.fixture
def clients(session, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ADMIN_KEY", ADMIN)
    monkeypatch.setenv("COOKIE_SECURE", "false")

    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    made: list[TestClient] = []

    def make() -> TestClient:
        c = TestClient(app)
        made.append(c)
        return c

    yield make
    for c in made:
        c.close()
    app.dependency_overrides.clear()


def _redeem(client: TestClient, email: str) -> None:
    resp = client.post("/api/admin/invites", headers={"X-Admin-Key": ADMIN}, json={"note": email})
    token = resp.json()["link"].split("invite=")[1]
    resp = client.post(
        "/api/auth/redeem",
        json={"token": token, "email": email, "display_name": email.split("@")[0]},
    )
    assert resp.status_code == 200, resp.text


def _active_id(client: TestClient) -> int:
    return client.get("/api/auth/me").json()["squad_id"]


# ── List ──────────────────────────────────────────────────────────────────────
def test_new_account_has_one_owned_active_team(clients):
    c = clients()
    _redeem(c, "solo@example.com")
    teams = c.get("/api/teams").json()
    assert len(teams) == 1
    assert teams[0]["is_active"] is True
    assert teams[0]["id"] == _active_id(c)
    assert teams[0]["player_count"] == 0


def test_create_second_team_switches_active(clients):
    c = clients()
    _redeem(c, "multi@example.com")
    first_id = _active_id(c)

    created = c.post("/api/teams", json={"team_name": "Second XI"})
    assert created.status_code == 200, created.text
    second = created.json()
    assert second["team_name"] == "Second XI"
    assert second["is_active"] is True
    assert second["id"] != first_id
    assert _active_id(c) == second["id"]

    teams = {t["id"]: t for t in c.get("/api/teams").json()}
    assert len(teams) == 2
    assert teams[first_id]["is_active"] is False
    assert teams[second["id"]]["is_active"] is True


def test_activate_switches_which_squad_data_is_returned(clients):
    c = clients()
    _redeem(c, "switch@example.com")
    first_id = _active_id(c)
    # First team gets a player + a match.
    c.post("/api/squad/players", json={"name": "Alice", "gk_status": "emergency_only"})
    c.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers"})

    second = c.post("/api/teams", json={"team_name": "B Team"}).json()
    # Now active = second, which has no players/matches.
    assert c.get("/api/squad/players").json() == []
    assert c.get("/api/matches/").json() == []

    # Switch back → first team's data reappears.
    act = c.post(f"/api/teams/{first_id}/activate")
    assert act.status_code == 200 and act.json()["active_squad_id"] == first_id
    assert len(c.get("/api/squad/players").json()) == 1
    assert len(c.get("/api/matches/").json()) == 1

    # player_count in the list reflects reality.
    rows = {t["id"]: t for t in c.get("/api/teams").json()}
    assert rows[first_id]["player_count"] == 1
    assert rows[second["id"]]["player_count"] == 0


# ── Delete ──────────────────────────────────────────────────────────────────────
def test_delete_removes_only_that_teams_data(clients):
    c = clients()
    _redeem(c, "del@example.com")
    first_id = _active_id(c)
    c.post("/api/squad/players", json={"name": "Keep", "gk_status": "emergency_only"})

    second = c.post("/api/teams", json={"team_name": "Doomed"}).json()
    c.post("/api/squad/players", json={"name": "Gone", "gk_status": "emergency_only"})
    c.post("/api/matches/", json={"date": "2026-04-01", "opponent": "X"})

    resp = c.delete(f"/api/teams/{second['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["active_squad_id"] == first_id  # re-pointed to the survivor

    teams = c.get("/api/teams").json()
    assert [t["id"] for t in teams] == [first_id]
    # First team's data intact.
    assert _active_id(c) == first_id
    assert len(c.get("/api/squad/players").json()) == 1


def test_cannot_delete_only_team(clients):
    c = clients()
    _redeem(c, "only@example.com")
    only_id = _active_id(c)
    resp = c.delete(f"/api/teams/{only_id}")
    assert resp.status_code == 409
    assert len(c.get("/api/teams").json()) == 1


def test_delete_inactive_team_keeps_active(clients):
    c = clients()
    _redeem(c, "keepactive@example.com")
    first_id = _active_id(c)
    second = c.post("/api/teams", json={"team_name": "Second"}).json()  # now active
    # Delete the FIRST (inactive) team → active stays on second.
    resp = c.delete(f"/api/teams/{first_id}")
    assert resp.status_code == 200
    assert resp.json()["active_squad_id"] == second["id"]
    assert _active_id(c) == second["id"]


# ── Ownership (IDOR) ──────────────────────────────────────────────────────────
def test_cannot_touch_another_accounts_team(clients):
    a, b = clients(), clients()
    _redeem(a, "owner-a@example.com")
    _redeem(b, "owner-b@example.com")
    a_squad = _active_id(a)

    # B cannot see A's team in its own list.
    assert a_squad not in {t["id"] for t in b.get("/api/teams").json()}
    # B cannot activate or delete A's squad → 404 (not 403, no existence leak).
    assert b.post(f"/api/teams/{a_squad}/activate").status_code == 404
    assert b.delete(f"/api/teams/{a_squad}").status_code == 404
    # A's active team is unchanged.
    assert _active_id(a) == a_squad


def test_teams_endpoints_require_auth(clients):
    c = clients()  # not signed in
    assert c.get("/api/teams").status_code == 401
    assert c.post("/api/teams", json={}).status_code == 401
    assert c.post("/api/teams/1/activate").status_code == 401
    assert c.delete("/api/teams/1").status_code == 401
