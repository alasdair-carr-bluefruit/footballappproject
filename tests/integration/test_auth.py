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


def test_invite_can_be_emailed(clients, monkeypatch):
    """Supplying an email mints the invite AND sends the invite-variant email."""
    import backend.api.routers.admin as admin_mod

    sent: list[tuple] = []
    monkeypatch.setattr(
        admin_mod, "send_login_link",
        lambda to, link, *, is_invite=False: sent.append((to, link, is_invite)),
    )
    c = clients()
    resp = c.post("/api/admin/invites", headers={"X-Admin-Key": ADMIN},
                  json={"email": "coach@example.com"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["emailed_to"] == "coach@example.com"
    assert "invite=" in body["link"]
    # Emailed once, as the invite variant, with the same link that was returned.
    assert sent == [("coach@example.com", body["link"], True)]


def test_invite_without_email_does_not_send(clients, monkeypatch):
    import backend.api.routers.admin as admin_mod

    sent: list = []
    monkeypatch.setattr(admin_mod, "send_login_link",
                        lambda *a, **k: sent.append(a))
    c = clients()
    resp = c.post("/api/admin/invites", headers={"X-Admin-Key": ADMIN}, json={"note": "no email"})
    assert resp.status_code == 200
    assert resp.json()["emailed_to"] is None
    assert sent == []


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


def test_invite_a_friend_requires_auth(clients):
    c = clients()
    assert c.post("/api/auth/invite-a-friend").status_code == 401


def test_invite_a_friend_creates_a_redeemable_one_time_link(clients):
    # A signed-in coach mints a shareable invite (no admin key needed)...
    coach = clients()
    _redeem(coach, "coach@example.com")
    resp = coach.post("/api/auth/invite-a-friend")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "invite=" in body["link"]
    assert body["expires_in_days"] == 14
    token = body["link"].split("invite=")[1]

    # The admin portal can see who created it (attribution).
    admin = coach.get("/api/admin/invites", headers={"X-Admin-Key": ADMIN}).json()
    mine = next(i for i in admin if i["note"] == "friend invite from coach@example.com")
    assert mine["created_by"] == "coach@example.com"
    assert mine["invited_by_account_id"] is not None

    # ...a new coach redeems it into their own separate account...
    friend = clients()
    assert friend.post(
        "/api/auth/redeem",
        json={"token": token, "email": "friend@example.com", "display_name": "Friend"},
    ).status_code == 200
    assert friend.get("/api/auth/me").json()["email"] == "friend@example.com"

    # ...and the link is single-use.
    third = clients()
    assert third.post(
        "/api/auth/redeem", json={"token": token, "email": "third@example.com"}
    ).status_code == 400


# ── Admin moderation (suspend / revoke) ─────────────────────────────────────────
def _account_id(client, email):
    accts = client.get("/api/admin/accounts", headers={"X-Admin-Key": ADMIN}).json()
    return next(a["id"] for a in accts if a["email"] == email)


def test_admin_suspend_locks_out_and_revokes_outstanding_invites(clients):
    coach = clients()
    _redeem(coach, "bad@example.com")
    token = coach.post("/api/auth/invite-a-friend").json()["link"].split("invite=")[1]

    r = coach.post(f"/api/admin/accounts/{_account_id(coach, 'bad@example.com')}/suspend",
                   headers={"X-Admin-Key": ADMIN})
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"
    assert r.json()["invites_revoked"] == 1

    # Session is dead: no app access, no more invites.
    assert coach.get("/api/auth/me").status_code == 401
    assert coach.post("/api/auth/invite-a-friend").status_code == 401
    # The already-sent invite link no longer redeems.
    friend = clients()
    assert friend.post(
        "/api/auth/redeem", json={"token": token, "email": "friend@example.com"}
    ).status_code == 400


def test_admin_suspend_blocks_login_link(clients):
    coach = clients()
    _redeem(coach, "nolink@example.com")
    coach.post(f"/api/admin/accounts/{_account_id(coach, 'nolink@example.com')}/suspend",
               headers={"X-Admin-Key": ADMIN})
    # request-link silently no-ops for a non-active account (no leak of who exists).
    resp = coach.post("/api/auth/request-link", json={"email": "nolink@example.com"})
    assert "dev_link" not in resp.json()


def test_admin_reactivate_restores_active_status(clients):
    coach = clients()
    _redeem(coach, "back@example.com")
    aid = _account_id(coach, "back@example.com")
    coach.post(f"/api/admin/accounts/{aid}/suspend", headers={"X-Admin-Key": ADMIN})
    r = coach.post(f"/api/admin/accounts/{aid}/reactivate", headers={"X-Admin-Key": ADMIN})
    assert r.status_code == 200 and r.json()["status"] == "active"


def test_admin_revoke_single_invite(clients):
    coach = clients()
    _redeem(coach, "rev@example.com")
    token = coach.post("/api/auth/invite-a-friend").json()["link"].split("invite=")[1]
    invites = coach.get("/api/admin/invites", headers={"X-Admin-Key": ADMIN}).json()
    inv_id = next(i["id"] for i in invites if not i["redeemed"])

    assert coach.post(f"/api/admin/invites/{inv_id}/revoke",
                      headers={"X-Admin-Key": ADMIN}).status_code == 200
    # Dead link + shows expired in the listing.
    friend = clients()
    assert friend.post(
        "/api/auth/redeem", json={"token": token, "email": "x@example.com"}
    ).status_code == 400
    after = coach.get("/api/admin/invites", headers={"X-Admin-Key": ADMIN}).json()
    assert next(i for i in after if i["id"] == inv_id)["expired"] is True


def test_moderation_endpoints_gated_by_admin_key(clients):
    coach = clients()
    _redeem(coach, "gate@example.com")
    aid = _account_id(coach, "gate@example.com")
    assert coach.post(f"/api/admin/accounts/{aid}/suspend").status_code == 403
    assert coach.post(f"/api/admin/accounts/{aid}/reactivate").status_code == 403
    assert coach.post("/api/admin/invites/1/revoke").status_code == 403


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


# ── Account self-service: clear data ─────────────────────────────────────────────
def test_clear_data_wipes_only_callers_squad(clients):
    a, b = clients(), clients()
    _redeem(a, "clear@example.com")
    _redeem(b, "keep@example.com")

    a.post("/api/squad/players", json={"name": "Alfa", "gk_status": "emergency_only"})
    a.post("/api/matches/", json={"date": "2026-03-25", "opponent": "Rovers"})
    a.post("/api/tournaments/", json={"name": "A Cup", "date": "2026-04-12"})
    b.post("/api/squad/players", json={"name": "Bravo", "gk_status": "emergency_only"})

    resp = a.post("/api/auth/account/clear-data")
    assert resp.status_code == 200 and resp.json() == {"ok": True}

    # A's football data is gone…
    assert a.get("/api/squad/players").json() == []
    assert a.get("/api/matches/").json() == []
    assert a.get("/api/tournaments/").json() == []
    # …but the account + login still work (can rebuild the squad).
    assert a.get("/api/auth/me").json()["email"] == "clear@example.com"
    assert a.post("/api/squad/players",
                  json={"name": "New", "gk_status": "emergency_only"}).status_code == 201
    # B is untouched.
    assert len(b.get("/api/squad/players").json()) == 1


def test_clear_data_requires_auth(clients):
    assert clients().post("/api/auth/account/clear-data").status_code == 401


# ── Account self-service: change email (re-verify) ───────────────────────────────
def test_email_change_confirms_to_new_address(clients):
    c = clients()
    _redeem(c, "old@example.com")
    req = c.post("/api/auth/account/request-email-change", json={"new_email": "new@example.com"})
    assert req.status_code == 200
    token = req.json()["dev_link"].split("email_change=")[1]  # dev-stub surfaces the link

    # Not switched until confirmed.
    assert c.get("/api/auth/me").json()["email"] == "old@example.com"

    confirm = c.post("/api/auth/account/confirm-email-change", json={"token": token})
    assert confirm.status_code == 200 and confirm.json()["email"] == "new@example.com"
    assert c.get("/api/auth/me").json()["email"] == "new@example.com"

    # New handle now receives sign-in links; the old one no longer resolves.
    assert "dev_link" in clients().post("/api/auth/request-link", json={"email": "new@example.com"}).json()
    assert "dev_link" not in clients().post("/api/auth/request-link", json={"email": "old@example.com"}).json()

    # Single-use: the confirm token can't be replayed.
    assert c.post("/api/auth/account/confirm-email-change", json={"token": token}).status_code == 400


def test_email_change_rejects_taken_or_same_email(clients):
    a, b = clients(), clients()
    _redeem(a, "a@example.com")
    _redeem(b, "b@example.com")
    # Requesting a change to an in-use address is refused up front.
    assert a.post("/api/auth/account/request-email-change",
                  json={"new_email": "b@example.com"}).status_code == 409
    # …as is changing to your own current address.
    assert a.post("/api/auth/account/request-email-change",
                  json={"new_email": "a@example.com"}).status_code == 422


def test_email_change_requires_auth(clients):
    c = clients()
    assert c.post("/api/auth/account/request-email-change",
                  json={"new_email": "x@example.com"}).status_code == 401


# ── Account reclaim (undo an unauthorised email change) ──────────────────────────
def _capture_reclaim_link(monkeypatch) -> list[dict]:
    """Capture the reclaim notice the router sends to the OLD address on confirm."""
    import backend.api.routers.auth as auth_mod

    captured: list[dict] = []
    monkeypatch.setattr(
        auth_mod, "send_email_changed_notice",
        lambda old, *, new_email, team_name, reclaim_link: captured.append(
            {"old": old, "new": new_email, "team": team_name, "link": reclaim_link}
        ),
    )
    return captured


def _change_email(c, new_email: str) -> None:
    token = c.post("/api/auth/account/request-email-change",
                   json={"new_email": new_email}).json()["dev_link"].split("email_change=")[1]
    assert c.post("/api/auth/account/confirm-email-change", json={"token": token}).status_code == 200


def test_reclaim_reverts_email_and_signs_out_all_devices(clients, monkeypatch):
    captured = _capture_reclaim_link(monkeypatch)
    victim = clients()
    _redeem(victim, "owner@example.com")
    # Second logged-in device for the same account (the "attacker" keeps this open).
    other = clients()
    tok = other.post("/api/auth/request-link", json={"email": "owner@example.com"}).json()["dev_link"].split("login=")[1]
    other.post("/api/auth/verify", json={"token": tok})
    assert other.get("/api/auth/me").status_code == 200

    # Email is changed away to the attacker's address.
    _change_email(victim, "attacker@example.com")
    assert captured and captured[-1]["old"] == "owner@example.com"
    reclaim_token = captured[-1]["link"].split("reclaim=")[1]

    # Owner reclaims from the notice sent to the old address (no session needed).
    fresh = clients()
    resp = fresh.post("/api/auth/account/reclaim", json={"token": reclaim_token})
    assert resp.status_code == 200 and resp.json()["email"] == "owner@example.com"

    # Every previously-issued session is now invalid (epoch bumped) — both devices.
    assert other.get("/api/auth/me").status_code == 401
    assert victim.get("/api/auth/me").status_code == 401

    # The restored address works for a fresh magic-link sign-in; the attacker's doesn't.
    assert "dev_link" in clients().post("/api/auth/request-link", json={"email": "owner@example.com"}).json()
    assert "dev_link" not in clients().post("/api/auth/request-link", json={"email": "attacker@example.com"}).json()

    # Reclaim token is single-use.
    assert fresh.post("/api/auth/account/reclaim", json={"token": reclaim_token}).status_code == 400


def test_normal_email_change_keeps_other_devices_signed_in(clients, monkeypatch):
    """A legitimate email change must NOT sign the coach out elsewhere — only reclaim does."""
    _capture_reclaim_link(monkeypatch)
    a = clients()
    _redeem(a, "coach@example.com")
    b = clients()
    tok = b.post("/api/auth/request-link", json={"email": "coach@example.com"}).json()["dev_link"].split("login=")[1]
    b.post("/api/auth/verify", json={"token": tok})

    _change_email(a, "coach2@example.com")
    # The other device stays authenticated (epoch unchanged on a normal change).
    assert b.get("/api/auth/me").status_code == 200
    assert b.get("/api/auth/me").json()["email"] == "coach2@example.com"


def test_reclaim_rejects_bad_token(clients):
    assert clients().post("/api/auth/account/reclaim", json={"token": "nope"}).status_code == 400


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
