"""End-to-end auth flow with AUTH_ENABLED (uses the `auth_server` fixture).

Drives a real browser through the gate: logged-out → login screen; open an invite
→ redeem → set up team → land in the app with a sign-out control; sign out; then
sign back in via a magic link. The default suite runs auth-off, so this is the one
place the login UI + boot gate are exercised in a browser.
"""
import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

ADMIN_HEADERS = {"X-Admin-Key": "e2e-admin"}


def _mint_invite(base: str) -> str:
    r = httpx.post(base + "/api/admin/invites", headers=ADMIN_HEADERS, json={"note": "e2e"}, timeout=10)
    r.raise_for_status()
    return r.json()["link"].split("invite=")[1]


def test_auth_gate_redeem_signout_and_magic_link(auth_server, page: Page):
    base = auth_server

    # Logged out → the gate shows the login screen; the app stays hidden.
    page.goto(base + "/")
    expect(page.locator("#screen-login")).to_be_visible()
    expect(page.locator("#screen-landing")).to_be_hidden()

    # Opening an invite link shows the redeem screen.
    token = _mint_invite(base)
    page.goto(base + f"/?invite={token}")
    expect(page.locator("#screen-join")).to_be_visible()

    # Redeem → brand-new account has no team yet → first-launch tutorial.
    page.fill("#join-email", "coach@example.com")
    page.fill("#join-name", "Coach")
    page.click("#btn-join-create")
    expect(page.locator("#screen-tutorial")).to_be_visible()

    # Finish setup → landing, now with a sign-out affordance (auth is on).
    page.fill("#tutorial-team-name", "E2E United")
    page.click("#btn-tutorial-start")
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(page.locator("#btn-signout")).to_be_visible()

    # Sign out → back to the login screen.
    page.click("#btn-signout")
    expect(page.locator("#screen-login")).to_be_visible()

    # Sign back in via a magic link (dev link surfaced since no email provider).
    page.fill("#login-email", "coach@example.com")
    page.click("#btn-login-send")
    devlink = page.locator("#login-devlink")
    expect(devlink).to_be_visible()
    login_token = devlink.get_attribute("href").split("login=")[1]

    page.goto(base + f"/?login={login_token}")
    # Team already configured → tutorial skipped → straight into the app.
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(page.locator("#btn-signout")).to_be_visible()


def test_unauthenticated_api_calls_are_blocked(auth_server, page: Page):
    """A direct API call without a session is refused (the gate isn't the only guard)."""
    resp = page.request.get(auth_server + "/api/matches/")
    assert resp.status == 401
