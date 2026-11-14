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


# The only write routes an assistant's ROLE admits: the plan routes. Creating is open;
# everything touching an existing match/tournament is then gated per row on who
# created it (`editable_match` / `editable_tournament`).
CREATE_ROUTES = {"/api/matches/", "/api/tournaments/"}


def test_only_plan_routes_are_granted_to_assistants():
    from backend.api.deps import ROLE_CAPS

    assistant_caps = ROLE_CAPS["assistant"]
    for r in _write_routes():
        granted = _capabilities(r) & assistant_caps
        assert granted <= {"author_plan"}, r.path
        if granted:
            assert r.path.startswith(("/api/matches", "/api/tournaments")), r.path
    # ...and the routes only the head coach may use never open up to an assistant.
    head_only = {"/api/matches/{match_id}/review", "/api/matches/{match_id}/owner",
                 "/api/tournaments/{tournament_id}/review", "/api/tournaments/{tournament_id}/owner"}
    for r in _write_routes():
        if r.path in head_only or r.path.startswith("/api/squad"):
            assert not (_capabilities(r) & assistant_caps), r.path


def test_every_plan_route_on_an_existing_row_has_the_per_row_guard():
    """`author_plan` alone only means "may create". A plan route that addresses an
    existing match/tournament must depend on `editable_match`/`editable_tournament`,
    or any assistant could change any plan."""

    def guarded(dep) -> bool:
        return getattr(dep.call, "_row_guard", False) or any(guarded(d) for d in dep.dependencies)

    missing = [
        r.path for r in _write_routes()
        if "author_plan" in _capabilities(r) and "{" in r.path and not guarded(r.dependant)
    ]
    assert missing == []


@pytest.mark.parametrize(
    "route",
    [r for r in _write_routes() if r.path not in CREATE_ROUTES],
    ids=lambda r: f"{sorted(r.methods)[0]} {r.path}",
)
def test_assistant_gets_403_on_every_write_to_someone_elses_plan(team, route):
    """The fixture's match + tournament were created by the head coach, so every
    write route that addresses them (and every squad route) must refuse an assistant.
    This is the net that catches a plan route forgetting its per-row check."""
    path = (
        route.path.replace("{match_id}", str(team["match_id"]))
        .replace("{tournament_id}", str(team["tournament_id"]))
        .replace("{player_id}", "1")
    )
    method = sorted(route.methods - {"HEAD"})[0]
    resp = team["asst"].request(method, path, json={})
    assert resp.status_code == 403, (method, path, resp.text)


# ── Assistant-authored plans ────────────────────────────────────────────────────
def _player_ids(client: TestClient) -> list[int]:
    return [p["id"] for p in client.get("/api/squad/players").json()]


def test_assistant_creates_plans_and_runs_their_own_match(team):
    a = team["asst"]
    ids = _player_ids(a)
    m = a.post("/api/matches/", json={"date": "2026-11-15", "opponent": "City"})
    assert m.status_code == 201, m.text
    mid = m.json()["id"]
    assert m.json()["can_edit"] is True

    gen = a.post(f"/api/matches/{mid}/rotation", json={"available_player_ids": ids})
    assert gen.status_code == 200, gen.text
    # Tinker (a no-op adjust is enough to prove access), edit settings, run matchday.
    assert a.post(f"/api/matches/{mid}/adjust", json={"edits": {}}).status_code == 200
    assert a.put(f"/api/matches/{mid}", json={"opponent": "City FC"}).status_code == 200
    assert a.post(f"/api/matches/{mid}/start").status_code == 200
    assert a.post(f"/api/matches/{mid}/goals", json={"goals": {"Ben": 1}}).status_code == 200
    assert a.post(
        f"/api/matches/{mid}/remove-player", json={"player_id": ids[-1], "from_slot": 2}
    ).status_code == 200
    assert a.post(f"/api/matches/{mid}/reinstate-player", json={"player_id": ids[-1]}).status_code == 200
    assert a.post(
        f"/api/matches/{mid}/progress", json={"current_slot": 7, "status": "completed"}
    ).status_code == 200
    assert a.get(f"/api/matches/{mid}").json()["match"]["can_edit"] is True
    # ...but still nothing of the head coach's.
    assert a.post(f"/api/matches/{team['match_id']}/start").status_code == 403
    assert a.get(f"/api/matches/{team['match_id']}").json()["match"]["can_edit"] is False


def test_fixture_list_says_who_made_an_assistant_plan(team):
    a, h = team["asst"], team["head"]
    mid = a.post("/api/matches/", json={"date": "2026-11-15", "opponent": "City"}).json()["id"]

    def row(client: TestClient, match_id: int) -> dict:
        return next(m for m in client.get("/api/matches/").json() if m["id"] == match_id)

    mine, theirs = row(a, mid), row(h, mid)
    assert (mine["created_by_name"], mine["created_by_me"], mine["can_edit"]) == ("asst", True, True)
    assert (theirs["created_by_name"], theirs["created_by_me"], theirs["can_edit"]) == ("asst", False, True)
    # The head coach's own match carries no annotation, and the assistant can't edit it.
    head_row = row(a, team["match_id"])
    assert (head_row["created_by_name"], head_row["can_edit"]) == ("", False)
    assert row(h, team["match_id"])["created_by_name"] == ""


def test_head_can_tinker_and_run_an_assistants_match(team):
    a, h = team["asst"], team["head"]
    mid = a.post("/api/matches/", json={"date": "2026-11-15"}).json()["id"]
    assert a.post(f"/api/matches/{mid}/rotation", json={}).status_code == 200
    assert h.post(f"/api/matches/{mid}/adjust", json={"edits": {}}).status_code == 200
    assert h.post(f"/api/matches/{mid}/start").status_code == 200
    assert h.delete(f"/api/matches/{mid}").status_code == 204


def test_other_assistants_can_view_but_not_touch_an_assistants_plan(clients, team):
    a = team["asst"]
    other = clients()
    _redeem(other, "asst2@example.com", token=_assist_token(team["head"]))
    mid = a.post("/api/matches/", json={"date": "2026-11-15"}).json()["id"]
    assert a.post(f"/api/matches/{mid}/rotation", json={}).status_code == 200
    tid = a.post("/api/tournaments/", json={"name": "Sixes", "date": "2026-11-22"}).json()["id"]

    seen = other.get(f"/api/matches/{mid}")
    assert seen.status_code == 200 and seen.json()["slots"]
    assert seen.json()["match"]["can_edit"] is False
    for method, path, body in [
        ("POST", f"/api/matches/{mid}/adjust", {"edits": {}}),
        ("POST", f"/api/matches/{mid}/rotation", {}),
        ("POST", f"/api/matches/{mid}/blank-rotation", {}),
        ("PUT", f"/api/matches/{mid}", {"opponent": "x"}),
        ("POST", f"/api/matches/{mid}/start", None),
        ("POST", f"/api/matches/{mid}/goals", {"goals": {}}),
        ("POST", f"/api/matches/{mid}/progress", {"current_slot": 1}),
        ("DELETE", f"/api/matches/{mid}", None),
        ("PUT", f"/api/tournaments/{tid}", {"name": "x"}),
        ("POST", f"/api/tournaments/{tid}/matches/batch", {"count": 1, "available_player_ids": []}),
        ("DELETE", f"/api/tournaments/{tid}", None),
    ]:
        resp = other.request(method, path, json=body)
        assert resp.status_code == 403, (method, path, resp.text)


def test_assistant_tournament_matches_belong_to_its_creator(clients, team):
    a, h = team["asst"], team["head"]
    ids = _player_ids(a)
    t = a.post("/api/tournaments/", json={"name": "Sixes", "date": "2026-11-22"})
    assert t.status_code == 201, t.text
    tid = t.json()["id"]
    batch = a.post(
        f"/api/tournaments/{tid}/matches/batch", json={"count": 2, "available_player_ids": ids}
    )
    assert batch.status_code == 200, batch.text
    # A match the HEAD adds to the assistant's tournament is still the assistant's to run.
    added = h.post(f"/api/tournaments/{tid}/matches", json={"opponent": "Lions", "available_player_ids": ids})
    assert added.status_code == 200, added.text
    for m in a.get(f"/api/tournaments/{tid}").json()["matches"]:
        assert a.post(f"/api/matches/{m['id']}/start").status_code == 200
    detail = h.get(f"/api/tournaments/{tid}").json()["tournament"]
    assert (detail["created_by_name"], detail["can_edit"]) == ("asst", True)
    # The assistant can add a temporary player to their own tournament — at the default
    # rating, which they never see — but not to the head coach's.
    guest = a.post(f"/api/tournaments/{tid}/players", json={"name": "Guest", "skill_rating": 5})
    assert guest.status_code == 201, guest.text
    assert guest.json()["skill_rating"] is None
    as_head = next(p for p in h.get(f"/api/tournaments/{tid}").json()["guest_players"])
    assert as_head["skill_rating"] == 3
    assert a.delete(f"/api/tournaments/{tid}/players/{guest.json()['id']}").status_code == 204
    assert a.post(
        f"/api/tournaments/{team['tournament_id']}/players", json={"name": "Guest2"}
    ).status_code == 403
    # The head's tournament is closed to the assistant.
    assert a.post(
        f"/api/tournaments/{team['tournament_id']}/matches",
        json={"opponent": "x", "available_player_ids": ids},
    ).status_code == 403


def test_removed_assistant_loses_their_plans(team):
    a, h = team["asst"], team["head"]
    mid = a.post("/api/matches/", json={"date": "2026-11-15"}).json()["id"]
    asst_id = h.get("/api/teams/assistants").json()[0]["account_id"]
    assert h.delete(f"/api/teams/assistants/{asst_id}").status_code in (200, 204)
    assert a.post(f"/api/matches/{mid}/start").status_code in (403, 404)
    assert h.post(f"/api/matches/{mid}/rotation", json={}).status_code == 200  # head keeps it


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


# ── Hand-over, review mark, notifications ───────────────────────────────────────
@pytest.fixture
def notices(monkeypatch):
    """Capture plan emails instead of sending them: [(to, subject, paragraphs)]."""
    sent: list[tuple[str, str, list[str]]] = []

    def fake(to_email, *, subject, heading, paragraphs, cta_label, link):
        sent.append((to_email, subject, paragraphs))

    monkeypatch.setattr("backend.auth.email.send_notice", fake)
    return sent


def _asst_id(team) -> int:
    return team["head"].get("/api/teams/assistants").json()[0]["account_id"]


def test_head_hands_a_fixture_to_an_assistant_and_back(team, notices):
    a, h, mid = team["asst"], team["head"], team["match_id"]
    assert a.post(f"/api/matches/{mid}/adjust", json={"edits": {}}).status_code == 403
    assert a.put(f"/api/matches/{mid}/owner", json={"account_id": _asst_id(team)}).status_code == 403

    handed = h.put(f"/api/matches/{mid}/owner", json={"account_id": _asst_id(team)})
    assert handed.status_code == 200, handed.text
    assert (handed.json()["created_by_name"], handed.json()["created_by_account_id"]) == ("asst", _asst_id(team))
    assert notices == [("asst@example.com", "head asked you to do a plan for Tigers", notices[0][2])]
    assert "vs Rovers on 4 Oct" in notices[0][2][0]
    assert a.post(f"/api/matches/{mid}/adjust", json={"edits": {}}).status_code == 200
    assert a.post(f"/api/matches/{mid}/start").status_code == 200

    # A live match can't change hands; nor can a stranger's account be given one.
    assert h.put(f"/api/matches/{mid}/owner", json={"account_id": None}).status_code == 400
    other = h.post("/api/matches/", json={"date": "2026-11-20"}).json()["id"]
    assert h.put(f"/api/matches/{other}/owner", json={"account_id": 99999}).status_code == 404
    # Handing back makes it the head coach's alone again.
    h.put(f"/api/matches/{other}/owner", json={"account_id": _asst_id(team)})
    back = h.put(f"/api/matches/{other}/owner", json={"account_id": None}).json()
    assert (back["created_by_name"], back["created_by_account_id"]) == ("", None)
    assert a.put(f"/api/matches/{other}", json={"opponent": "x"}).status_code == 403


def test_head_hands_over_a_whole_tournament(team, notices):
    a, h, tid = team["asst"], team["head"], team["tournament_id"]
    ids = _player_ids(h)
    h.post(f"/api/tournaments/{tid}/matches/batch", json={"count": 2, "available_player_ids": ids})
    first = h.get(f"/api/tournaments/{tid}").json()["matches"][0]["id"]
    assert h.put(f"/api/matches/{first}/owner", json={"account_id": _asst_id(team)}).status_code == 400
    assert a.post(f"/api/matches/{first}/start").status_code == 403

    handed = h.put(f"/api/tournaments/{tid}/owner", json={"account_id": _asst_id(team)})
    assert handed.status_code == 200, handed.text
    assert handed.json()["created_by_name"] == "asst"
    assert len(notices) == 1 and "for Cup on 11 Oct" in notices[0][2][0]
    assert a.post(f"/api/matches/{first}/start").status_code == 200
    assert h.put(f"/api/tournaments/{tid}/owner", json={"account_id": None}).status_code == 400  # live


def test_head_is_told_once_when_an_assistant_makes_a_plan(team, notices):
    a = team["asst"]
    mid = a.post("/api/matches/", json={"date": "2026-11-15", "opponent": "City"}).json()["id"]
    assert notices == []  # a fixture with no plan yet isn't news
    a.post(f"/api/matches/{mid}/rotation", json={})
    a.post(f"/api/matches/{mid}/rotation", json={})  # regenerating doesn't email again
    assert [(to, subj) for to, subj, _ in notices] == [("head@example.com", "asst made a plan for Tigers")]
    assert "vs City on 15 Nov" in notices[0][2][0]

    tid = a.post("/api/tournaments/", json={"name": "Sixes", "date": "2026-11-22"}).json()["id"]
    ids = _player_ids(a)
    a.post(f"/api/tournaments/{tid}/matches/batch", json={"count": 2, "available_player_ids": ids})
    a.post(f"/api/tournaments/{tid}/matches/batch", json={"count": 1, "available_player_ids": ids})
    assert len(notices) == 2 and "for Sixes on 22 Nov" in notices[1][2][0]


def test_head_coachs_own_plans_and_opt_out_send_nothing(team, notices):
    a, h = team["asst"], team["head"]
    h.post(f"/api/matches/{team['match_id']}/rotation", json={})
    assert notices == []
    off = h.post("/api/auth/account/notifications", json={"notify_plans": False})
    assert off.status_code == 200 and off.json()["notify_plans"] is False
    mid = a.post("/api/matches/", json={"date": "2026-11-15"}).json()["id"]
    a.post(f"/api/matches/{mid}/rotation", json={})
    assert notices == []


def test_review_mark_is_the_heads_and_clears_when_the_assistant_changes_the_plan(team):
    a, h = team["asst"], team["head"]
    mid = a.post("/api/matches/", json={"date": "2026-11-15"}).json()["id"]
    gen = a.post(f"/api/matches/{mid}/rotation", json={}).json()

    def reviewed(client: TestClient) -> bool:
        listed = next(m for m in client.get("/api/matches/").json() if m["id"] == mid)["reviewed"]
        assert client.get(f"/api/matches/{mid}").json()["match"]["reviewed"] is listed
        return listed

    assert a.post(f"/api/matches/{mid}/review", json={"reviewed": True}).status_code == 403
    assert h.post(f"/api/matches/{mid}/review", json={"reviewed": True}).json() == {"reviewed": True}
    assert reviewed(a) is True
    # Not a gate, and running the match doesn't un-review it...
    # ...the head coach's own tinkering keeps the mark...
    slot = gen["slots"][0]
    pos, player = next((k, v) for k, v in slot["lineup"].items() if k != "GK")
    edit = {"edits": {"0": {pos: player["id"]}}}
    assert h.post(f"/api/matches/{mid}/adjust", json=edit).status_code == 200
    assert reviewed(h) is True
    # ...but the assistant changing the plan afterwards drops it.
    assert a.post(f"/api/matches/{mid}/adjust", json=edit).status_code == 200
    assert reviewed(h) is False
    assert h.post(f"/api/matches/{mid}/review", json={"reviewed": True}).status_code == 200
    assert a.post(f"/api/matches/{mid}/start").status_code == 200
    assert reviewed(h) is True


def test_tournament_review_mark(team):
    a, h = team["asst"], team["head"]
    ids = _player_ids(a)
    tid = a.post("/api/tournaments/", json={"name": "Sixes", "date": "2026-11-22"}).json()["id"]
    a.post(f"/api/tournaments/{tid}/matches/batch", json={"count": 1, "available_player_ids": ids})
    assert a.post(f"/api/tournaments/{tid}/review", json={}).status_code == 403
    assert h.post(f"/api/tournaments/{tid}/review", json={}).json() == {"reviewed": True}
    assert a.get(f"/api/tournaments/{tid}").json()["tournament"]["reviewed"] is True
    a.post(f"/api/tournaments/{tid}/matches", json={"opponent": "KO", "available_player_ids": ids})
    assert h.get(f"/api/tournaments/{tid}").json()["tournament"]["reviewed"] is False


# ── One controlling device + the server clock ───────────────────────────────────
def _dev(name: str) -> dict:
    return {"X-Device-Id": name}


@pytest.fixture
def live(team):
    """An assistant's match, started on the assistant's phone."""
    a = team["asst"]
    mid = a.post("/api/matches/", json={"date": "2026-11-15", "opponent": "City"}).json()["id"]
    a.post(f"/api/matches/{mid}/rotation", json={})
    started = a.post(f"/api/matches/{mid}/start", headers=_dev("asst-phone"))
    assert started.status_code == 200, started.text
    assert started.json()["controller"] == {
        "name": "asst", "is_me": True, "same_account": True,
        "since": started.json()["controller"]["since"],
    }
    assert started.json()["timer"]["running"] is True
    return {**team, "live_id": mid}


def test_only_the_controlling_device_can_run_a_live_match(live):
    a, h, mid = live["asst"], live["head"], live["live_id"]
    writes = [
        ("POST", "progress", {"current_slot": 2}),
        ("POST", "goals", {"goals": {"Ben": 1}}),
        ("POST", "adjust", {"edits": {}}),
        ("PUT", "timer", {"running": False, "elapsed_ms": 1000}),
        ("POST", "unstart", None),
    ]
    for method, path, body in writes:
        resp = h.request(method, f"/api/matches/{mid}/{path}", json=body, headers=_dev("head-phone"))
        assert resp.status_code == 409, (path, resp.text)
        assert resp.json()["detail"]["code"] == "not_controller"
        assert resp.json()["detail"]["controller_name"] == "asst"
        assert resp.json()["detail"]["same_account"] is False
    # The same coach on a second device is held off too, with its own wording.
    other = a.post(f"/api/matches/{mid}/progress", json={"current_slot": 2}, headers=_dev("asst-tablet"))
    assert other.status_code == 409 and other.json()["detail"]["same_account"] is True
    # The controlling device carries on.
    assert a.post(
        f"/api/matches/{mid}/progress", json={"current_slot": 2}, headers=_dev("asst-phone")
    ).status_code == 200
    # Everyone sees who is running it.
    seen = h.get(f"/api/matches/{mid}", headers=_dev("head-phone")).json()["match"]
    assert (seen["controller"]["name"], seen["controller"]["is_me"], seen["current_slot"]) == ("asst", False, 2)


def test_take_control_moves_the_match_to_the_new_device(live, clients):
    a, h, mid = live["asst"], live["head"], live["live_id"]
    a.post(f"/api/matches/{mid}/goals", json={"goals": {"Ben": 2}}, headers=_dev("asst-phone"))

    taken = h.post(f"/api/matches/{mid}/take-control", headers=_dev("head-phone"))
    assert taken.status_code == 200, taken.text
    assert taken.json()["match"]["controller"]["is_me"] is True
    assert taken.json()["goals"] == {"Ben": 2}  # nothing is lost with the dead phone
    assert h.post(
        f"/api/matches/{mid}/progress", json={"current_slot": 4}, headers=_dev("head-phone")
    ).status_code == 200
    lost = a.post(f"/api/matches/{mid}/progress", json={"current_slot": 2}, headers=_dev("asst-phone"))
    assert lost.status_code == 409 and lost.json()["detail"]["controller_name"] == "head"
    # ...and the assistant can take it straight back.
    assert a.post(f"/api/matches/{mid}/take-control", headers=_dev("asst-phone")).status_code == 200

    # Someone who can't run this match can't take control of it.
    bystander = clients()
    _redeem(bystander, "asst2@example.com", token=_assist_token(h))
    assert bystander.post(f"/api/matches/{mid}/take-control", headers=_dev("x")).status_code == 403
    assert a.post(f"/api/matches/{mid}/take-control").status_code == 400  # no device id


def test_full_time_releases_control_and_old_clients_are_never_blocked(live):
    a, h, mid = live["asst"], live["head"], live["live_id"]
    # A client that sends no device id (a stale cached app) is never refused.
    assert h.post(f"/api/matches/{mid}/progress", json={"current_slot": 1}).status_code == 200
    done = a.post(
        f"/api/matches/{mid}/progress", json={"current_slot": 7, "status": "completed"},
        headers=_dev("asst-phone"),
    )
    assert done.status_code == 200
    after = h.get(f"/api/matches/{mid}", headers=_dev("head-phone")).json()["match"]
    assert after["controller"] is None and after["timer"]["running"] is False
    # The report can now be edited from any device allowed to.
    assert h.post(
        f"/api/matches/{mid}/goals", json={"goals": {"Ben": 3}}, headers=_dev("head-phone")
    ).status_code == 200


def test_a_live_match_nobody_controls_is_claimed_by_the_first_device(team):
    h, mid = team["head"], team["match_id"]
    h.post(f"/api/matches/{mid}/start")  # started by a client with no device id
    assert h.get(f"/api/matches/{mid}", headers=_dev("p1")).json()["match"]["controller"] is None
    assert h.post(f"/api/matches/{mid}/progress", json={"current_slot": 2}, headers=_dev("p1")).status_code == 200
    assert h.post(
        f"/api/matches/{mid}/progress", json={"current_slot": 3}, headers=_dev("p2")
    ).status_code == 409
    # Returning to the plan gives control up again.
    h.post(f"/api/matches/{mid}/progress", json={"current_slot": 0}, headers=_dev("p1"))
    assert h.post(f"/api/matches/{mid}/unstart", headers=_dev("p1")).status_code == 200
    assert h.post(f"/api/matches/{mid}/start", headers=_dev("p2")).json()["controller"]["is_me"] is True


def test_server_clock_follows_the_controlling_device(live):
    a, h, mid = live["asst"], live["head"], live["live_id"]

    def clock() -> dict:
        return h.get(f"/api/matches/{mid}", headers=_dev("head-phone")).json()["match"]["timer"]

    assert clock()["running"] is True and 0 <= clock()["elapsed_ms"] < 5000
    paused = a.put(
        f"/api/matches/{mid}/timer", json={"running": False, "elapsed_ms": 185_000},
        headers=_dev("asst-phone"),
    )
    assert paused.json() == {"timer": {"running": False, "elapsed_ms": 185_000}}
    assert clock() == {"running": False, "elapsed_ms": 185_000}
    a.put(f"/api/matches/{mid}/timer", json={"running": True, "elapsed_ms": 185_000},
          headers=_dev("asst-phone"))
    assert clock()["running"] is True and 185_000 <= clock()["elapsed_ms"] < 190_000
