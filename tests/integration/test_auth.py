"""Multi-user auth: invite redeem, magic-link login, and squad isolation (IDOR).

These run with AUTH_ENABLED=true (the rest of the suite runs auth-off, exercising
the single-squad fallback). Two authenticated clients with separate cookie jars
stand in for two coaches sharing one deployment; the isolation tests assert one
can never see or touch the other's data.
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from backend.auth.session import verify_session
from backend.db.database import get_session
from backend.db.models import InviteDB
from backend.settings import SESSION_COOKIE
from main import app

pytestmark = pytest.mark.integration

ADMIN = "test-admin-key"


@pytest.fixture
def clients(session, monkeypatch):
    """Factory for auth-enabled clients sharing one in-memory DB (separate cookies)."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("ADMIN_KEY", ADMIN)
    monkeypatch.setenv("COOKIE_SECURE", "false")  # TestClient rides http://

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


def _mint_invite(client: TestClient, note: str = "") -> str:
    """Admin-mint an invite and return the raw token."""
    resp = client.post("/api/admin/invites", headers={"X-Admin-Key": ADMIN}, json={"note": note})
    assert resp.status_code == 200, resp.text
    return resp.json()["link"].split("invite=")[1]


def _redeem(client: TestClient, email: str) -> None:
    token = _mint_invite(client, email)
    resp = client.post(
        "/api/auth/redeem",
        json={"token": token, "email": email, "display_name": email.split("@")[0]},
    )
    assert resp.status_code == 200, resp.text


# ── Gate & session lifecycle ────────────────────────────────────────────────────
def test_protected_routes_require_auth(clients):
    c = clients()
    for path in ("/api/matches/", "/api/squad/players", "/api/tournaments/", "/api/auth/me"):
        assert c.get(path).status_code == 401, path


def test_admin_invites_gated_by_key(clients):
    c = clients()
    assert c.post("/api/admin/invites", json={"note": "x"}).status_code == 403  # no key
    assert c.post("/api/admin/invites", headers={"X-Admin-Key": "wrong"},
                  json={"note": "x"}).status_code == 403
    ok = c.post("/api/admin/invites", headers={"X-Admin-Key": ADMIN}, json={"note": "x"})
    assert ok.status_code == 200 and "invite=" in ok.json()["link"]


def test_redeem_creates_account_and_logs_in(clients):
    c = clients()
    _redeem(c, "coach@example.com")
    me = c.get("/api/auth/me").json()
    assert me["authenticated"] and me["auth_enabled"] and me["email"] == "coach@example.com"
    # Now authorised: can create + read the squad's players.
    assert c.post("/api/squad/players",
                  json={"name": "P1", "gk_status": "emergency_only"}).status_code == 201
    assert len(c.get("/api/squad/players").json()) == 1


def test_logout_clears_session(clients):
    c = clients()
    _redeem(c, "bye@example.com")
    assert c.get("/api/auth/me").status_code == 200
    c.post("/api/auth/logout")
    assert c.get("/api/auth/me").status_code == 401


def test_session_rolls_forward_on_activity(clients):
    """Each authenticated request re-issues a valid session cookie (sliding window),
    so an active coach never has to request a fresh magic link."""
    c = clients()
    _redeem(c, "rolling@example.com")
    resp = c.get("/api/auth/me")
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert SESSION_COOKIE in set_cookie  # middleware refreshed it
    # The refreshed token is itself valid.
    refreshed = c.cookies.get(SESSION_COOKIE)
    assert verify_session(refreshed) is not None


def test_duplicate_email_redeem_is_rejected(clients):
    c1, c2 = clients(), clients()
    _redeem(c1, "dup@example.com")
    token = _mint_invite(c2, "second")
    resp = c2.post("/api/auth/redeem",
                   json={"token": token, "email": "dup@example.com"})
    assert resp.status_code == 409


# ── Invite token lifecycle ──────────────────────────────────────────────────────
def test_invite_is_single_use(clients):
    c = clients()
    token = _mint_invite(c)
    assert c.post("/api/auth/redeem", json={"token": token, "email": "first@example.com"}).status_code == 200
    # Same token, different email → already redeemed.
    c2 = clients()
    assert c2.post("/api/auth/redeem", json={"token": token, "email": "second@example.com"}).status_code == 400


def test_invalid_and_expired_invites_rejected(clients, session):
    c = clients()
    assert c.post("/api/auth/redeem", json={"token": "nope", "email": "x@example.com"}).status_code == 400

    token = _mint_invite(c)
    invite = session.exec(select(InviteDB)).first()
    invite.expires_at = "2000-01-01T00:00:00+00:00"  # in the past
    session.add(invite)
    session.commit()
    assert c.post("/api/auth/redeem", json={"token": token, "email": "y@example.com"}).status_code == 400


# ── Magic-link login ────────────────────────────────────────────────────────────
def test_magic_link_login_on_new_device(clients):
    signup = clients()
    _redeem(signup, "returning@example.com")

    device = clients()  # fresh cookie jar = new device
    link_resp = device.post("/api/auth/request-link", json={"email": "returning@example.com"})
    assert link_resp.status_code == 200
    token = link_resp.json()["dev_link"].split("login=")[1]  # dev-stub surfaces the link

    verify = device.post("/api/auth/verify", json={"token": token})
    assert verify.status_code == 200
    assert device.get("/api/auth/me").json()["email"] == "returning@example.com"

    # Single-use: the same token can't be replayed.
    assert device.post("/api/auth/verify", json={"token": token}).status_code == 400


def test_request_link_for_unknown_email_is_silent(clients):
    c = clients()
    resp = c.post("/api/auth/request-link", json={"email": "ghost@example.com"})
    assert resp.status_code == 200
    assert "dev_link" not in resp.json()  # no account → no link, but still 200 (no enumeration)


# ── Admin support tooling ───────────────────────────────────────────────────────
def test_admin_can_list_dump_and_impersonate(clients):
    coach = clients()
    _redeem(coach, "support@example.com")
    coach.post("/api/squad/players", json={"name": "Kid", "gk_status": "emergency_only"})
    match_id = coach.post("/api/matches/",
                          json={"date": "2026-03-25", "opponent": "Rovers"}).json()["id"]

    admin = clients()
    hdr = {"X-Admin-Key": ADMIN}
    accounts = admin.get("/api/admin/accounts", headers=hdr).json()
    acct = next(a for a in accounts if a["email"] == "support@example.com")

    dump = admin.get(f"/api/admin/accounts/{acct['id']}/dump", headers=hdr).json()
    assert dump["counts"] == {"players": 1, "matches": 1, "tournaments": 0}
    assert dump["matches"][0]["id"] == match_id

    # Impersonate: the admin client gets a session cookie for the coach's account.
    imp = admin.post(f"/api/admin/accounts/{acct['id']}/impersonate", headers=hdr)
    assert imp.status_code == 200
    assert admin.get("/api/auth/me").json()["email"] == "support@example.com"
    # ...and now sees the coach's data through the normal API.
    assert admin.get(f"/api/matches/{match_id}").status_code == 200


def test_admin_account_tooling_is_gated(clients):
    c = clients()
    assert c.get("/api/admin/accounts").status_code == 403
    assert c.get("/api/admin/accounts/1/dump").status_code == 403
    assert c.post("/api/admin/accounts/1/impersonate").status_code == 403


# ── Isolation / IDOR ────────────────────────────────────────────────────────────
def test_accounts_are_isolated(clients):
    a, b = clients(), clients()
    _redeem(a, "a@example.com")
    _redeem(b, "b@example.com")

    a_match = a.post("/api/matches/", json={"date": "2026-03-25", "opponent": "A Rovers"}).json()["id"]
    a_player = a.post("/api/squad/players",
                      json={"name": "Alfa", "gk_status": "emergency_only"}).json()["id"]
    a_tourn = a.post("/api/tournaments/", json={"name": "A Cup", "date": "2026-04-12"}).json()["id"]

    # B's lists never include A's rows.
    assert b.get("/api/matches/").json() == []
    assert b.get("/api/squad/players").json() == []
    assert b.get("/api/tournaments/").json() == []

    # B cannot read or mutate A's rows by guessing the id → 404 (not 403, no existence leak).
    assert b.get(f"/api/matches/{a_match}").status_code == 404
    assert b.delete(f"/api/matches/{a_match}").status_code == 404
    assert b.post(f"/api/matches/{a_match}/start").status_code == 404
    assert b.put(f"/api/squad/players/{a_player}",
                 json={"name": "Hijack", "gk_status": "emergency_only"}).status_code == 404
    assert b.delete(f"/api/squad/players/{a_player}").status_code == 404
    assert b.get(f"/api/tournaments/{a_tourn}").status_code == 404
    assert b.delete(f"/api/tournaments/{a_tourn}").status_code == 404

    # A still sees its own data intact.
    assert len(a.get("/api/matches/").json()) == 1
    assert a.get(f"/api/matches/{a_match}").status_code == 200
