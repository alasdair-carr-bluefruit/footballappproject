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
    # Magic links don't auto-verify on load (corporate Safe-Links would burn the
    # one-time token) — a confirm-click interstitial completes the sign-in.
    expect(page.locator("#screen-verify")).to_be_visible()
    page.click("#btn-verify-confirm")
    # Team already configured → tutorial skipped → straight into the app.
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(page.locator("#btn-signout")).to_be_visible()


def _redeem_and_setup(base: str, page: Page, team_name: str, email: str) -> None:
    """Redeem a fresh invite and finish first-launch setup → land in the app."""
    token = _mint_invite(base)
    page.goto(base + f"/?invite={token}")
    expect(page.locator("#screen-join")).to_be_visible()
    page.fill("#join-email", email)
    page.fill("#join-name", "Coach")
    page.click("#btn-join-create")
    expect(page.locator("#screen-tutorial")).to_be_visible()
    page.fill("#tutorial-team-name", team_name)
    page.click("#btn-tutorial-start")
    expect(page.locator("#screen-landing")).to_be_visible()
    # Dismiss the first-run squad-building tip (its scrim intercepts mode-card
    # clicks); mirrors the app's own dismissSquadTip().
    page.evaluate(
        "() => { document.getElementById('squad-onboarding').style.display='none';"
        " document.querySelector('.landing').classList.remove('landing--onboarding'); }"
    )


def test_multi_team_pill_add_and_switch(auth_server, page: Page):
    """The header pill lets a coach add a second team, name it, and switch back —
    exercised on the season home (the tournament home shares the same render)."""
    base = auth_server
    _redeem_and_setup(base, page, "First FC", "multi@example.com")

    # The pill is also surfaced on the landing screen and squad-management screen
    # (not just the two home screens) — same shared render.
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(page.locator("#team-pill-landing .team-pill")).to_contain_text("First FC")
    # The one-time "multi-team is live" banner shows on landing and dismisses.
    expect(page.locator("#multiteam-callout")).to_be_visible()
    page.click("#btn-multiteam-callout-dismiss")
    expect(page.locator("#multiteam-callout")).to_be_hidden()
    page.click("#btn-squad-management")
    expect(page.locator("#screen-squad")).to_be_visible()
    expect(page.locator("#team-pill-squad .team-pill")).to_contain_text("First FC")
    page.click("#btn-squad-back")
    expect(page.locator("#screen-landing")).to_be_visible()

    # Season home shows the team pill with the active team's name.
    page.click("#btn-season-mode")
    expect(page.locator("#screen-home")).to_be_visible()
    pill = page.locator("#team-pill-home .team-pill")
    expect(pill).to_be_visible()
    expect(pill).to_contain_text("First FC")

    # Open the switcher → one team, marked active → add a new team.
    pill.click()
    expect(page.locator("#team-switcher-overlay")).to_be_visible()
    expect(page.locator("#team-switcher-list .team-row")).to_have_count(1)
    page.click("#btn-team-add")

    # Adding a blank team drops into squad management to name it.
    expect(page.locator("#screen-squad")).to_be_visible()
    page.fill("#team-name-input", "Second XI")
    page.click("#btn-save-team-info")
    page.click("#btn-squad-back")
    expect(page.locator("#screen-landing")).to_be_visible()

    # The new team is now active.
    page.click("#btn-season-mode")
    expect(page.locator("#team-pill-home .team-pill")).to_contain_text("Second XI")

    # Switch back to the first team via the switcher.
    page.click("#team-pill-home .team-pill")
    expect(page.locator("#team-switcher-list .team-row")).to_have_count(2)
    page.locator(".team-row-main", has_text="First FC").click()
    expect(page.locator("#team-pill-home .team-pill")).to_contain_text("First FC")


def test_unauthenticated_api_calls_are_blocked(auth_server, page: Page):
    """A direct API call without a session is refused (the gate isn't the only guard)."""
    resp = page.request.get(auth_server + "/api/matches/")
    assert resp.status == 401
