"""Walkthrough + first-use intros: "seen" is remembered on the account (so the tour
never repeats on another device), and accounts from before intros existed are
backfilled from their data so live coaches don't get "first time" cards."""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from backend.db.database import get_session
from backend.db.models import AccountDB
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


def _redeem(client: TestClient, email: str) -> dict:
    resp = client.post("/api/admin/invites", headers={"X-Admin-Key": ADMIN}, json={"note": email})
    token = resp.json()["link"].split("invite=")[1]
    resp = client.post("/api/auth/redeem",
                       json={"token": token, "email": email, "display_name": "Sam"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_legacy(session, email: str) -> None:
    """Pretend the account predates intros (the migration leaves these rows at "")."""
    acct = session.exec(select(AccountDB).where(AccountDB.email == email)).one()
    acct.intros_seen = ""
    session.add(acct)
    session.commit()


def test_new_coach_starts_with_nothing_seen(clients):
    c = clients()
    assert _redeem(c, "new@example.com")["intros_seen"] == {}
    assert c.get("/api/auth/me").json()["intros_seen"] == {}


def test_marking_is_idempotent_and_follows_the_account(clients):
    a = clients()
    _redeem(a, "coach@example.com")
    first = a.post("/api/auth/intros/welcome")
    assert first.status_code == 200
    stamp = first.json()["intros_seen"]["welcome"]
    again = a.post("/api/auth/intros/welcome").json()["intros_seen"]
    assert again == {"welcome": stamp}  # second mark keeps the first date

    # Same account, another device (same cookie) → already seen.
    other = clients()
    other.cookies.update(a.cookies)
    assert "welcome" in other.get("/api/auth/me").json()["intros_seen"]


def test_unmark_and_bad_ids(clients):
    c = clients()
    _redeem(c, "tips@example.com")
    assert "__tips_off" in c.post("/api/auth/intros/__tips_off").json()["intros_seen"]
    assert c.delete("/api/auth/intros/__tips_off").json()["intros_seen"] == {}
    assert c.post("/api/auth/intros/Not%20An%20Id").status_code == 422
    assert c.post("/api/auth/intros/" + "x" * 80).status_code == 422


def test_only_touches_own_account(clients):
    a, b = clients(), clients()
    _redeem(a, "a@example.com")
    _redeem(b, "b@example.com")
    a.post("/api/auth/intros/first-review")
    assert b.get("/api/auth/me").json()["intros_seen"] == {}


def test_requires_sign_in(clients):
    c = clients()
    assert c.post("/api/auth/intros/welcome").status_code == 401


def test_backfill_marks_what_an_existing_coach_already_uses(clients, session):
    c = clients()
    _redeem(c, "live@example.com")
    c.post("/api/squad/players", json={"name": "Ava", "gk_status": "emergency_only"})
    c.post("/api/matches/", json={"date": "2026-11-01", "opponent": "Rovers"})
    _make_legacy(session, "live@example.com")

    seen = c.get("/api/auth/me").json()["intros_seen"]
    for intro in ("welcome", "first-squad", "first-setup", "first-review",
                  "first-tinker", "first-live", "first-rested"):
        assert intro in seen, intro
    assert "first-tournament" not in seen  # never made one → still gets that intro
    assert "assistant-welcome" not in seen


def test_backfill_for_an_empty_legacy_account(clients, session):
    c = clients()
    _redeem(c, "quiet@example.com")
    _make_legacy(session, "quiet@example.com")
    # Set up long ago but never added anyone: only the welcome tour is skipped.
    assert c.get("/api/auth/me").json()["intros_seen"].keys() == {"welcome"}
    # …and it runs once: later marks stick, nothing is recomputed.
    c.post("/api/auth/intros/first-squad")
    assert c.get("/api/auth/me").json()["intros_seen"].keys() == {"welcome", "first-squad"}
