"""Assistant coach mode, phase 1 (T3.2): per-team roles, read-only assistants.

Runs auth-on (like test_teams.py). Separate TestClients = separate cookie jars =
separate coaches. Covers invites (new + existing accounts), the read/write split,
skill-rating redaction, IDOR, leave/remove/delete re-pointing, the deny-by-default
route guard, and the Alembic backfill.
"""
import pytest
from fastapi.routing import APIRoute
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


def _redeem(client: TestClient, email: str, token: str | None = None) -> dict:
    if token is None:
        resp = client.post("/api/admin/invites", headers={"X-Admin-Key": ADMIN}, json={"note": email})
        token = resp.json()["link"].split("invite=")[1]
    resp = client.post(
        "/api/auth/redeem",
        json={"token": token, "email": email, "display_name": email.split("@")[0]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _assist_token(head: TestClient) -> str:
    resp = head.post("/api/teams/assistant-invite")
    assert resp.status_code == 200, resp.text
    return resp.json()["link"].split("assist=")[1]


def _me(client: TestClient) -> dict:
    return client.get("/api/auth/me").json()


@pytest.fixture
def team(clients):
    """A head coach with a named team, one player, a planned match and a tournament,
    plus a brand-new assistant who joined via an assistant link."""
    head = clients()
    _redeem(head, "head@example.com")
    head.put("/api/squad/info", json={"team_name": "Tigers", "team_logo": ""})
    for i, name in enumerate(["Ava", "Ben", "Cal", "Dan", "Eve", "Fay"]):
        r = head.post(
            "/api/squad/players",
            json={"name": name, "gk_status": "can_play" if i == 0 else "emergency_only",
                  "skill_rating": 4},
        )
        assert r.status_code == 201, r.text
    match = head.post("/api/matches/", json={"date": "2026-10-04", "opponent": "Rovers"}).json()
    gen = head.post(f"/api/matches/{match['id']}/rotation", json={})
    assert gen.status_code == 200, gen.text
    tourn = head.post(
        "/api/tournaments/", json={"name": "Cup", "date": "2026-10-11", "team_size": 5}
    )
    assert tourn.status_code == 201, tourn.text

    asst = clients()
    me = _redeem(asst, "asst@example.com", token=_assist_token(head))
    return {
        "head": head,
        "asst": asst,
        "squad_id": _me(head)["squad_id"],
        "match_id": match["id"],
        "tournament_id": tourn.json()["id"],
        "asst_me": me,
    }


# ── Joining ───────────────────────────────────────────────────────────────────
def test_new_person_joins_as_assistant_without_a_team_of_their_own(team):
    me = team["asst_me"]
    assert me["role"] == "assistant"
    assert me["squad_id"] == team["squad_id"]
    teams = team["asst"].get("/api/teams").json()
    assert len(teams) == 1
    assert teams[0]["role"] == "assistant"
    assert teams[0]["team_name"] == "Tigers"
    assert teams[0]["head_name"] == "head"
    assert _me(team["head"])["role"] == "head"


def test_existing_coach_joins_via_join_endpoint_and_keeps_own_team(clients, team):
    other = clients()
    _redeem(other, "other@example.com")
    own_id = _me(other)["squad_id"]

    resp = other.post("/api/teams/join", json={"token": _assist_token(team["head"])})
    assert resp.status_code == 200, resp.text
    assert _me(other)["squad_id"] == team["squad_id"]
    assert _me(other)["role"] == "assistant"

    roles = {t["id"]: t["role"] for t in other.get("/api/teams").json()}
    assert roles == {own_id: "head", team["squad_id"]: "assistant"}
    # Switching back to their own team makes them head again.
    other.post(f"/api/teams/{own_id}/activate")
    assert _me(other)["role"] == "head"


def test_assistant_link_is_single_use_and_previewable(clients, team):
    token = _assist_token(team["head"])
    preview = clients().post("/api/teams/assist-preview", json={"token": token})
    assert preview.status_code == 200
    assert preview.json() == {"team_name": "Tigers", "head_name": "head"}

    _redeem(clients(), "first@example.com", token=token)
    again = clients().post(
        "/api/auth/redeem", json={"token": token, "email": "second@example.com"}
    )
    assert again.status_code == 400
    assert clients().post("/api/teams/assist-preview", json={"token": token}).status_code == 400


def test_plain_invite_cannot_be_used_to_join_a_team(clients, team):
    resp = team["head"].post("/api/admin/invites", headers={"X-Admin-Key": ADMIN}, json={})
    plain = resp.json()["link"].split("invite=")[1]
    assert team["asst"].post("/api/teams/join", json={"token": plain}).status_code == 400


def test_head_cannot_join_own_team_as_assistant(team):
    resp = team["head"].post("/api/teams/join", json={"token": _assist_token(team["head"])})
    assert resp.status_code == 409


# ── Read access + redaction ─────────────────────────────────────────────────────
def test_assistant_can_read_everything_the_team_has(team):
    a, mid, tid = team["asst"], team["match_id"], team["tournament_id"]
    for path in [
        "/api/squad/info",
        "/api/squad/players",
        "/api/matches/",
        f"/api/matches/{mid}",
        "/api/matches/stats/season",
        "/api/matches/export/season.xlsx",
        "/api/tournaments/",
        f"/api/tournaments/{tid}",
        f"/api/tournaments/{tid}/stats",
        "/api/tournaments/stats/all",
    ]:
        assert a.get(path).status_code == 200, path
    plan = a.get(f"/api/matches/{mid}").json()
    assert plan["slots"], "assistant sees the draft plan"
    assert all(isinstance(s["skill_total"], int) for s in plan["slots"])  # pooled totals stay


def test_skill_ratings_redacted_for_assistant_only(team):
    a_players = team["asst"].get("/api/squad/players").json()
    h_players = team["head"].get("/api/squad/players").json()
    assert {p["skill_rating"] for p in a_players} == {None}
    assert {p["skill_rating"] for p in h_players} == {4}

    tid = team["tournament_id"]
    a_t = team["asst"].get(f"/api/tournaments/{tid}").json()
    h_t = team["head"].get(f"/api/tournaments/{tid}").json()
    assert {p["skill_rating"] for p in a_t["squad_players"]} == {None}
    assert {p["skill_rating"] for p in h_t["squad_players"]} == {4}


# ── Write access ─────────────────────────────────────────────────────────────────
SQUAD_SCOPED_PREFIXES = ("/api/squad", "/api/matches", "/api/tournaments")


def _write_routes() -> list[APIRoute]:
    return [
        r for r in app.routes
        if isinstance(r, APIRoute)
        and r.path.startswith(SQUAD_SCOPED_PREFIXES)
        and r.methods - {"GET", "HEAD"}
    ]


def _capabilities(route: APIRoute) -> set[str]:
    found: set[str] = set()

    def walk(dep) -> None:
        cap = getattr(dep.call, "_capability", None)
        if cap:
            found.add(cap)
        for sub in dep.dependencies:
            walk(sub)

    walk(route.dependant)
    return found


def test_every_squad_scoped_write_route_declares_a_capability():
    """Deny by default: a new write route that forgets `require(...)` fails here."""
    routes = _write_routes()
    assert len(routes) >= 26  # sanity: the walk actually found the routers
    missing = [f"{sorted(r.methods)} {r.path}" for r in routes if not _capabilities(r)]
    assert missing == []


def test_no_write_route_is_granted_to_assistants():
    from backend.api.deps import ROLE_CAPS

    assistant_caps = ROLE_CAPS["assistant"]
    for r in _write_routes():
        assert not (_capabilities(r) & assistant_caps), r.path


@pytest.mark.parametrize(
    "route", _write_routes(), ids=lambda r: f"{sorted(r.methods)[0]} {r.path}"
)
def test_assistant_gets_403_on_every_write_route(team, route):
    path = (
        route.path.replace("{match_id}", str(team["match_id"]))
        .replace("{tournament_id}", str(team["tournament_id"]))
        .replace("{player_id}", "1")
    )
    method = sorted(route.methods - {"HEAD"})[0]
    resp = team["asst"].request(method, path, json={})
    assert resp.status_code == 403, (method, path, resp.text)


def test_assistant_blocked_from_team_level_actions(team):
    a, sid = team["asst"], team["squad_id"]
    assert a.post("/api/teams/assistant-invite").status_code == 403
    assert a.get("/api/teams/assistants").status_code == 403
    assert a.post("/api/auth/account/clear-data").status_code == 403
    assert a.delete(f"/api/teams/{sid}").status_code == 403
    # Nothing was cleared.
    assert len(team["head"].get("/api/squad/players").json()) == 6


def test_head_can_still_write(team):
    h, mid = team["head"], team["match_id"]
    assert h.post(f"/api/matches/{mid}/start").status_code == 200
    assert h.post(f"/api/matches/{mid}/goals", json={"goals": {}}).status_code == 200


def test_assistant_can_still_create_their_own_team(team):
    a = team["asst"]
    created = a.post("/api/teams", json={"team_name": "Lions"})
    assert created.status_code == 200
    assert created.json()["role"] == "head"
    assert _me(a)["role"] == "head"
    assert a.post("/api/squad/players", json={"name": "Zed", "gk_status": "can_play"}).status_code == 201


# ── Isolation (IDOR) ───────────────────────────────────────────────────────────
def test_assistant_on_one_team_cannot_read_another(clients, team):
    stranger = clients()
    _redeem(stranger, "stranger@example.com")
    m = stranger.post("/api/matches/", json={"date": "2026-10-04"}).json()
    assert team["asst"].get(f"/api/matches/{m['id']}").status_code == 404
    other_squad = _me(stranger)["squad_id"]
    assert team["asst"].post(f"/api/teams/{other_squad}/activate").status_code == 404


# ── Leaving, removing, deleting ────────────────────────────────────────────────
def test_head_lists_and_removes_assistant(team):
    rows = team["head"].get("/api/teams/assistants").json()
    assert [r["email"] for r in rows] == ["asst@example.com"]

    resp = team["head"].delete(f"/api/teams/assistants/{rows[0]['account_id']}")
    assert resp.status_code == 200
    assert team["head"].get("/api/teams/assistants").json() == []
    # The ex-assistant had no team of their own: they land on a fresh one they head.
    me = _me(team["asst"])
    assert me["squad_id"] != team["squad_id"]
    assert me["role"] == "head"
    assert team["asst"].get(f"/api/matches/{team['match_id']}").status_code == 404


def test_assistant_leaves_but_head_cannot(team):
    sid = team["squad_id"]
    assert team["head"].post(f"/api/teams/{sid}/leave").status_code == 409
    assert team["asst"].post(f"/api/teams/{sid}/leave").status_code == 200
    assert _me(team["asst"])["squad_id"] != sid
    assert team["head"].get("/api/teams/assistants").json() == []


def test_deleting_team_repoints_its_assistants(team):
    h, sid = team["head"], team["squad_id"]
    h.post("/api/teams", json={"team_name": "Second"})  # head needs another team to delete one
    assert h.delete(f"/api/teams/{sid}").status_code == 200
    me = _me(team["asst"])
    assert me["squad_id"] != sid
    assert me["role"] == "head"
    assert all(t["id"] != sid for t in team["asst"].get("/api/teams").json())


# ── Alembic backfill ────────────────────────────────────────────────────────────
def test_migration_backfills_one_head_membership_per_owned_squad(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text
    from sqlmodel import SQLModel

    import backend.db.database as database
    import backend.db.models  # noqa: F401

    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    SQLModel.metadata.create_all(engine)
    # Shape the DB as production looks before this revision.
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE squad_memberships"))
        conn.execute(text("ALTER TABLE invites DROP COLUMN squad_id"))
        conn.execute(text("ALTER TABLE invites DROP COLUMN role"))
        conn.execute(text("INSERT INTO squads (id, account_id, name, team_name, team_logo) "
                          "VALUES (1, 10, 'a', '', ''), (2, 10, 'b', '', ''), (3, NULL, 'c', '', '')"))
    monkeypatch.setattr(database, "engine", engine)
    cfg = Config(str(database._ALEMBIC_INI))
    command.stamp(cfg, "c9d4e2b1a7f6")
    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")  # no-op re-run

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT squad_id, account_id, role FROM squad_memberships ORDER BY squad_id")
        ).all()
    assert [tuple(r) for r in rows] == [(1, 10, "head"), (2, 10, "head")]
    cols = {c["name"] for c in inspect(engine).get_columns("invites")}
    assert {"squad_id", "role"} <= cols
    # Re-applying from the previous revision rebuilds the same rows.
    command.downgrade(cfg, "c9d4e2b1a7f6")
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM squad_memberships")).scalar()
    assert n == 2


def test_assistant_invite_needs_head_coach_name(team, session):
    from sqlmodel import select

    from backend.db.models import AccountDB

    head = session.exec(select(AccountDB).where(AccountDB.email == "head@example.com")).one()
    head.display_name = ""
    session.add(head)
    session.commit()
    assert team["head"].post("/api/teams/assistant-invite").status_code == 409
    team["head"].post("/api/auth/account/name", json={"display_name": "Sam"})
    assert team["head"].post("/api/teams/assistant-invite").status_code == 200
