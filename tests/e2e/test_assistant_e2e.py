"""Assistant coach mode, phase 1 (T3.2) in a real browser, auth on.

A head coach (driven over the API) sets up a squad, a season match and a tournament
match, then mints an assistant link. A brand-new person opens it, joins as an
assistant, and — in BOTH flows (season ⇄ tournament parity) — can open the upcoming
plan but is offered none of the controls that change anything.
"""
import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

ADMIN_HEADERS = {"X-Admin-Key": "e2e-admin"}
PLAYERS = ["Ava", "Ben", "Cal", "Dan", "Eve", "Fay", "Gus"]


def _head_coach_with_plans(base: str, email: str) -> str:
    """Create a head coach + squad + planned season & tournament matches over the
    API; return a one-time assistant invite token for that team."""
    with httpx.Client(base_url=base, timeout=20) as head:
        r = head.post("/api/admin/invites", headers=ADMIN_HEADERS, json={"note": email})
        token = r.json()["link"].split("invite=")[1]
        head.post("/api/auth/redeem", json={"token": token, "email": email, "display_name": "Sam"}).raise_for_status()
        head.put("/api/squad/info", json={"team_name": "Tigers", "team_logo": ""}).raise_for_status()
        ids = []
        for i, name in enumerate(PLAYERS):
            p = head.post("/api/squad/players", json={
                "name": name, "gk_status": "preferred" if i == 0 else "can_play", "skill_rating": 3,
            })
            p.raise_for_status()
            ids.append(p.json()["id"])

        m = head.post("/api/matches/", json={"date": "2026-10-04", "opponent": "Rovers"}).json()
        head.post(f"/api/matches/{m['id']}/rotation", json={"available_player_ids": ids}).raise_for_status()

        t = head.post("/api/tournaments/", json={"name": "Autumn Cup", "date": "2026-10-11"}).json()
        head.post(f"/api/tournaments/{t['id']}/matches",
                  json={"opponent": "Lions", "available_player_ids": ids}).raise_for_status()

        link = head.post("/api/teams/assistant-invite").json()["link"]
        return link.split("assist=")[1]


def _join_as_assistant(base: str, page: Page, token: str, email: str) -> None:
    # Retire the one-time multi-team popover (it overlays the list headers).
    page.add_init_script("localStorage.setItem('gaffer_multiteam_seen', '1')")
    page.goto(base + f"/?assist={token}")
    expect(page.locator("#screen-join")).to_be_visible()
    expect(page.locator("#join-title")).to_have_text("Join Tigers")
    expect(page.locator("#join-sub")).to_contain_text("Sam has invited you")
    page.fill("#join-email", email)
    page.fill("#join-name", "Alex")
    page.click("#btn-join-create")
    # No team of their own to set up → no tutorial, straight to the landing.
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(page.locator("#assistant-banner")).to_be_visible()
    expect(page.locator("#team-pill-landing .team-pill")).to_contain_text("Tigers")
    expect(page.locator("#team-pill-landing .role-badge")).to_have_text("Assistant")
    expect(page.locator("#btn-squad-management")).to_be_hidden()
    expect(page.locator("#btn-coach-teaser")).to_be_hidden()


def _assert_read_only_review(page: Page) -> None:
    expect(page.locator("#screen-review")).to_be_visible()
    expect(page.locator("#review-grid")).to_contain_text("Ava")  # the draft plan is visible
    expect(page.locator("#btn-review-start")).to_be_hidden()
    page.click("#btn-review-view")
    expect(page.locator("#screen-pitch")).to_be_visible()
    expect(page.locator("#btn-adjust")).to_be_hidden()
    expect(page.locator("#start-match-bar")).to_be_hidden()
    expect(page.locator("#end-match-bar")).to_be_hidden()
    expect(page.locator("#match-timer")).to_be_hidden()


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_assistant_sees_plan_but_no_editing_controls(auth_server, page: Page, flow: str):
    base = auth_server
    token = _head_coach_with_plans(base, f"head-{flow}@example.com")
    _join_as_assistant(base, page, token, f"asst-{flow}@example.com")

    if flow == "season":
        page.click("#btn-season-mode")
        expect(page.locator("#screen-home")).to_be_visible()
        expect(page.locator("#btn-go-new-match")).to_be_hidden()
        row = page.locator("#match-list .match-item").first
        expect(row).to_contain_text("Rovers")
        expect(row.locator(".match-delete")).to_be_hidden()
        row.locator(".match-item-main").click()
    else:
        page.click("#btn-tournament-mode")
        expect(page.locator("#screen-tournament-home")).to_be_visible()
        expect(page.locator("#btn-new-tournament")).to_be_hidden()
        t_row = page.locator("#tournament-list .match-item").first
        expect(t_row.locator(".match-delete")).to_be_hidden()
        t_row.locator(".match-item-main").click()
        expect(page.locator("#screen-tournament-lobby")).to_be_visible()
        expect(page.locator("#btn-edit-tournament")).to_be_hidden()
        expect(page.locator("#btn-add-group-match")).to_be_hidden()
        m_row = page.locator("#lobby-match-list .match-item").first
        expect(m_row.locator(".match-rename")).to_be_hidden()
        m_row.locator(".match-item-main").click()

    _assert_read_only_review(page)


def test_head_coach_manages_assistants_in_settings(auth_server, page: Page):
    """The landing card opens Settings → Assistant coaches, where a link can be minted."""
    base = auth_server
    with httpx.Client(base_url=base, timeout=20) as api:
        r = api.post("/api/admin/invites", headers=ADMIN_HEADERS, json={"note": "hc"})
        token = r.json()["link"].split("invite=")[1]
    page.goto(base + f"/?invite={token}")
    page.fill("#join-email", "settings-head@example.com")
    page.fill("#join-name", "Jo")
    page.click("#btn-join-create")
    page.fill("#tutorial-team-name", "Hawks")
    page.click("#btn-tutorial-start")
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(page.locator("#assistant-banner")).to_be_hidden()
    page.evaluate(
        "() => { document.getElementById('squad-onboarding').style.display='none';"
        " document.querySelector('.landing').classList.remove('landing--onboarding'); }"
    )

    page.click("#btn-coach-teaser")
    expect(page.locator("#screen-settings")).to_be_visible()
    expect(page.locator("#settings-assistants-empty")).to_be_visible()
    expect(page.locator("#settings-assisting")).to_be_hidden()
    page.click("#btn-assistant-invite-create")
    link = page.locator("#assistant-invite-link")
    expect(link).to_be_visible()
    assert "assist=" in link.input_value()


@pytest.mark.parametrize("route", ["link", "form"])
def test_existing_coach_signs_in_then_accepts_assistant_invite(auth_server, page: Page, route: str):
    """Signed-out existing coach: the join form spots their account, parks the invite,
    and after the magic-link sign-in they confirm joining — keeping their own team."""
    base = auth_server
    token = _head_coach_with_plans(base, f"head-existing-{route}@example.com")
    existing = f"existing-{route}@example.com"
    with httpx.Client(base_url=base, timeout=20) as other:
        r = other.post("/api/admin/invites", headers=ADMIN_HEADERS, json={"note": "x"})
        own = r.json()["link"].split("invite=")[1]
        other.post("/api/auth/redeem", json={
            "token": own, "email": existing, "display_name": "Pat",
        }).raise_for_status()
        other.put("/api/squad/info", json={"team_name": "My Own XI", "team_logo": ""}).raise_for_status()

    page.add_init_script("localStorage.setItem('gaffer_multiteam_seen', '1')")
    page.goto(base + f"/?assist={token}")
    expect(page.locator("#screen-join")).to_be_visible()
    page.fill("#join-email", existing)
    if route == "link":
        # "Already use Level? Sign in instead" — no name needed.
        page.click("#btn-join-have-account")
        expect(page.locator("#screen-login")).to_be_visible()
        expect(page.locator("#login-email")).to_have_value(existing)
    else:
        # Filled the form anyway: the server's 409 routes them to sign in.
        page.fill("#join-name", "Pat")
        page.click("#btn-join-create")
        expect(page.locator("#screen-login")).to_be_visible()
        expect(page.locator("#login-msg")).to_contain_text("already have a Level account")

    page.click("#btn-login-send")
    devlink = page.locator("#login-devlink")
    expect(devlink).to_be_visible()
    login_token = devlink.get_attribute("href").split("login=")[1]
    page.goto(base + f"/?login={login_token}")
    page.click("#btn-verify-confirm")

    expect(page.locator("#screen-assist-join")).to_be_visible()
    expect(page.locator("#assist-join-title")).to_have_text("Join Tigers")
    page.click("#btn-assist-join-confirm")
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(page.locator("#team-pill-landing .role-badge")).to_have_text("Assistant")

    # Their own team is still there, as head coach.
    page.click("#team-pill-landing .team-pill")
    expect(page.locator("#team-switcher-list .team-row")).to_have_count(2)
    page.locator(".team-row-main", has_text="My Own XI").click()
    expect(page.locator("#assistant-banner")).to_be_hidden()
    expect(page.locator("#btn-squad-management")).to_be_visible()
