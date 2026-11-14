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


def _head_coach_with_plans(base: str, email: str, cookies: dict | None = None) -> str:
    """Create a head coach + squad + planned season & tournament matches over the
    API; return a one-time assistant invite token for that team. Pass `cookies` to
    get the head coach's session back (to sign a browser in as them)."""
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

        # A finished match with a goal — the assistant reviews its report.
        done = head.post("/api/matches/", json={"date": "2026-09-27", "opponent": "Wolves"}).json()
        head.post(f"/api/matches/{done['id']}/rotation", json={"available_player_ids": ids}).raise_for_status()
        head.post(f"/api/matches/{done['id']}/start").raise_for_status()
        head.post(f"/api/matches/{done['id']}/goals",
                  json={"goals": {"Ben": 2}, "opponent_goals": 1}).raise_for_status()
        head.post(f"/api/matches/{done['id']}/progress",
                  json={"current_slot": 7, "status": "completed"}).raise_for_status()

        link = head.post("/api/teams/assistant-invite").json()["link"]
        if cookies is not None:
            cookies.update(dict(head.cookies))
        return link.split("assist=")[1]


def _head_page(browser, base: str, cookies: dict) -> Page:
    """A second device: a fresh browser context signed in as the head coach."""
    ctx = browser.new_context(service_workers="block")
    ctx.add_cookies([{"name": k, "value": v, "url": base} for k, v in cookies.items()])
    page = ctx.new_page()
    page.add_init_script("localStorage.setItem('gaffer_multiteam_seen', '1')")
    page.on("dialog", lambda d: d.accept())
    page.goto(base + "/")
    expect(page.locator("#screen-landing")).to_be_visible()
    return page


def _open_list(page: Page, flow: str) -> None:
    if flow == "season":
        page.click("#btn-season-mode")
        expect(page.locator("#screen-home")).to_be_visible()
    else:
        page.click("#btn-tournament-mode")
        expect(page.locator("#screen-tournament-home")).to_be_visible()


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
        expect(page.locator("#btn-go-new-match")).to_be_visible()  # may create their own
        row = page.locator("#match-list .match-item").first
        expect(row).to_contain_text("Rovers")
        expect(row.locator(".match-delete")).to_be_hidden()
        row.locator(".match-item-main").click()
    else:
        page.click("#btn-tournament-mode")
        expect(page.locator("#screen-tournament-home")).to_be_visible()
        expect(page.locator("#btn-new-tournament")).to_be_visible()  # may create their own
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


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_assistant_creates_and_runs_their_own_plan(auth_server, page: Page, flow: str):
    """An assistant makes a plan of their own, can tinker with it and start the match,
    and the list says whose plan it is — while the head coach's plans stay read-only."""
    base = auth_server
    token = _head_coach_with_plans(base, f"head-own-{flow}@example.com")
    _join_as_assistant(base, page, token, f"asst-own-{flow}@example.com")

    if flow == "season":
        page.click("#btn-season-mode")
        page.click("#btn-go-new-match")
        page.fill("#opponent-input", "City")
        page.click("#btn-select-players")
        expect(page.locator("#screen-match-squad")).to_be_visible()
        page.click("#btn-generate")
    else:
        page.click("#btn-tournament-mode")
        page.click("#btn-new-tournament")
        page.fill("#tournament-name-input", "Sixes")
        page.click("#btn-create-tournament")
        expect(page.locator("#screen-tournament-squad")).to_be_visible()
        # Whoever runs the tournament can add a temporary player — an assistant just
        # isn't shown (and can't set) a skill rating.
        page.click("#btn-tournament-add-guest")
        expect(page.locator("#guest-skill")).to_be_hidden()
        page.fill("#guest-name", "Zed")
        page.click("#guest-player-form button[type=submit]")
        expect(page.locator("#tournament-squad-list .avail-item-guest")).to_contain_text("Zed")
        page.click("#btn-generate-all-matches")
        expect(page.locator("#screen-tournament-lobby")).to_be_visible()
        expect(page.locator("#btn-add-group-match")).to_be_visible()
        expect(page.locator("#btn-edit-tournament")).to_be_visible()
        page.locator("#lobby-match-list .match-item-main").first.click()

    # Their own plan: tinker on/off, then start the match.
    expect(page.locator("#screen-review")).to_be_visible()
    expect(page.locator("#btn-review-start")).to_be_visible()
    page.click("#btn-review-view")
    expect(page.locator("#screen-pitch")).to_be_visible()
    page.click("#btn-adjust")
    expect(page.locator("#edit-mode-badge")).to_be_visible()
    page.click("#btn-adjust")
    expect(page.locator("#edit-mode-badge")).to_be_hidden()
    page.click("#btn-start-match-cta")
    expect(page.locator("#live-badge")).to_be_visible()
    expect(page.locator("#end-match-bar")).to_be_visible()

    # Back to the list: their plan is annotated + deletable; the head coach's is neither.
    page.click("#btn-pitch-back")
    if flow == "season":
        expect(page.locator("#screen-home")).to_be_visible()
        mine = page.locator("#match-list .match-item", has_text="City")
        theirs = page.locator("#match-list .match-item", has_text="Rovers")
    else:
        expect(page.locator("#screen-tournament-lobby")).to_be_visible()
        page.click("#btn-lobby-back")
        expect(page.locator("#screen-tournament-home")).to_be_visible()
        mine = page.locator("#tournament-list .match-item", has_text="Sixes")
        theirs = page.locator("#tournament-list .match-item", has_text="Autumn Cup")
    expect(mine.locator(".match-badge-author")).to_have_text("Plan by you")
    expect(mine.locator(".match-delete")).to_be_visible()
    expect(theirs.locator(".match-badge-author")).to_have_count(0)
    expect(theirs.locator(".match-delete")).to_have_count(0)

    # ...and opening the head coach's plan is still read-only (no stale edit rights).
    theirs.locator(".match-item-main").click()
    if flow == "tournament":
        expect(page.locator("#screen-tournament-lobby")).to_be_visible()
        expect(page.locator("#btn-add-group-match")).to_be_hidden()
        page.locator("#lobby-match-list .match-item-main").first.click()
    _assert_read_only_review(page)


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_head_hands_over_a_plan_and_marks_it_reviewed(auth_server, browser, page: Page, flow: str):
    """The head coach hands one of their own plans to an assistant from the list,
    then marks it reviewed; the assistant sees both and can now run it."""
    base, cookies = auth_server, {}
    token = _head_coach_with_plans(base, f"head-hand-{flow}@example.com", cookies)
    _join_as_assistant(base, page, token, f"asst-hand-{flow}@example.com")
    head = _head_page(browser, base, cookies)
    name = "Rovers" if flow == "season" else "Autumn Cup"
    rows = "#match-list .match-item" if flow == "season" else "#tournament-list .match-item"

    _open_list(head, flow)
    row = head.locator(rows, has_text=name)
    expect(row.locator(".plan-owner-btn")).to_have_text("Hand over")
    row.locator(".plan-owner-btn").click()
    expect(head.locator("#plan-owner-overlay")).to_be_visible()
    head.locator("#plan-owner-options button", has_text="Alex").click()
    row = head.locator(rows, has_text=name)
    expect(row.locator(".plan-owner-btn")).to_have_text("Plan by Alex")

    # Review it: open the plan(s), mark reviewed.
    row.locator(".match-item-main").click()
    if flow == "tournament":
        head.click("#btn-tournament-review")
    expect(head.locator("#screen-review")).to_be_visible()
    expect(head.locator("#review-mark-text")).to_have_text("Plan by Alex")
    head.click("#btn-review-mark")
    expect(head.locator("#review-mark-text")).to_contain_text("Reviewed ✓")

    # The assistant sees it is theirs and reviewed — and can start the match.
    _open_list(page, flow)
    mine = page.locator(rows, has_text=name)
    expect(mine.locator(".match-badge-author")).to_have_text("Plan by you ✓")
    mine.locator(".match-item-main").click()
    if flow == "tournament":
        expect(page.locator("#btn-add-group-match")).to_be_visible()
        page.locator("#lobby-match-list .match-item-main").first.click()
    expect(page.locator("#screen-review")).to_be_visible()
    expect(page.locator("#btn-review-start")).to_be_visible()
    head.context.close()


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_one_device_runs_a_live_match_and_another_can_take_control(
    auth_server, browser, page: Page, flow: str
):
    """The assistant starts their match; the head coach's device watches it live
    (read-only, with the clock), then takes control — and the assistant's device
    drops to the same read-only view on its next save."""
    base, cookies = auth_server, {}
    token = _head_coach_with_plans(base, f"head-live-{flow}@example.com", cookies)
    _join_as_assistant(base, page, token, f"asst-live-{flow}@example.com")
    page.on("dialog", lambda d: d.accept())

    # The assistant makes a plan and starts the match on their phone.
    if flow == "season":
        page.click("#btn-season-mode")
        page.click("#btn-go-new-match")
        page.fill("#opponent-input", "City")
        page.click("#btn-select-players")
        page.click("#btn-generate")
    else:
        page.click("#btn-tournament-mode")
        page.click("#btn-new-tournament")
        page.fill("#tournament-name-input", "Sixes")
        page.click("#btn-create-tournament")
        page.click("#btn-generate-all-matches")
        page.locator("#lobby-match-list .match-item-main").first.click()
    expect(page.locator("#screen-review")).to_be_visible()
    page.click("#btn-review-start")
    expect(page.locator("#live-badge")).to_be_visible()
    expect(page.locator("#control-banner")).to_be_hidden()

    # The head coach opens the same match on another device: live, but view-only.
    head = _head_page(browser, base, cookies)
    _open_list(head, flow)
    if flow == "season":
        head.locator("#match-list .match-item", has_text="City").locator(".match-item-main").click()
    else:
        head.locator("#tournament-list .match-item", has_text="Sixes").locator(".match-item-main").click()
        head.locator("#lobby-match-list .match-item-main").first.click()
    expect(head.locator("#screen-pitch")).to_be_visible()
    expect(head.locator("#control-banner-text")).to_have_text("● Alex is running this match")
    expect(head.locator("#end-match-bar")).to_be_hidden()
    expect(head.locator("#btn-adjust")).to_be_hidden()
    expect(head.locator("#match-timer")).to_be_visible()      # the server's clock...
    expect(head.locator("#btn-timer-pause")).to_be_hidden()   # ...but not its controls

    # A goal on the assistant's phone shows up on the head coach's within a poll.
    token_el = page.locator("#pitch .player-circle").first
    token_el.dispatch_event("pointerdown")
    expect(page.locator("#pitch .goal-badge")).to_have_count(1)
    token_el.dispatch_event("pointerup")
    expect(head.locator("#pitch .goal-badge")).to_have_count(1, timeout=20_000)

    # Take control: the head coach's device now runs it...
    head.click("#btn-take-control")
    expect(head.locator("#control-banner")).to_be_hidden()
    expect(head.locator("#end-match-bar")).to_be_visible()
    expect(head.locator("#btn-timer-pause")).to_be_visible()
    expect(head.locator("#pitch .goal-badge")).to_have_count(1)  # nothing lost in the hand-over

    # ...and the assistant's device finds out on its next save and drops to watching.
    page.click("#btn-timer-pause")
    expect(page.locator("#control-banner-text")).to_have_text("● Sam is running this match")
    expect(page.locator("#end-match-bar")).to_be_hidden()
    expect(page.locator("#btn-take-control")).to_be_visible()  # and could take it back
    head.context.close()


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

    teaser = page.locator("#btn-coach-teaser")
    expect(teaser).to_be_visible()
    page.click("#btn-coach-teaser")
    expect(page.locator("#screen-settings")).to_be_visible()
    expect(page.locator("#settings-assistants-empty")).to_be_visible()
    expect(page.locator("#settings-assisting")).to_be_hidden()
    page.click("#btn-assistant-invite-create")
    link = page.locator("#assistant-invite-link")
    expect(link).to_be_visible()
    assert "assist=" in link.input_value()

    # Opened once → the landing card is retired, and stays gone after a reload.
    page.reload()
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(teaser).to_be_hidden()


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


def test_assistant_browsing_a_finished_match_never_tries_to_save(auth_server, page: Page):
    """Regression: leaving a finished match (back or Done) used to re-save the goals,
    which 403s for an assistant and showed "Couldn't save — check your connection"."""
    base = auth_server
    token = _head_coach_with_plans(base, "head-report@example.com")
    _join_as_assistant(base, page, token, "asst-report@example.com")
    writes: list[str] = []
    page.on("request", lambda r: writes.append(f"{r.method} {r.url}") if r.method != "GET" else None)

    page.click("#btn-season-mode")
    page.locator("#match-list .match-item", has_text="Wolves").locator(".match-item-main").click()
    expect(page.locator("#screen-fulltime")).to_be_visible()
    expect(page.locator("#ft-scorers-list")).to_contain_text("Ben")
    expect(page.locator(".ft-opp-goals-row")).to_be_hidden()

    page.click("#btn-ft-pitch")
    expect(page.locator("#screen-pitch")).to_be_visible()
    for _ in range(3):
        page.click("#btn-next")
    page.click("#btn-prev")
    page.click("#btn-pitch-back")
    expect(page.locator("#screen-home")).to_be_visible()

    page.locator("#match-list .match-item", has_text="Wolves").locator(".match-item-main").click()
    page.click("#btn-ft-done")
    expect(page.locator("#screen-home")).to_be_visible()

    expect(page.locator(".toast", has_text="Couldn't save")).to_have_count(0)
    assert [w for w in writes if "/api/" in w] == []
