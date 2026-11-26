"""The new-coach walkthrough (docs/archive/WALKTHROUGH_PLAN.md), auth on, in a real browser.

A new head coach gets the 4-card welcome tour before naming their team (Skip or
finish both land on the team-name screen); it's remembered on the account, so a
second device never shows it again; Settings replays it. Each screen's first-use
intro shows once, in both flows (season ⇄ tournament parity). A new assistant
gets the assistant welcome instead of the head coach's tour.
"""
import httpx
import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_assistant_e2e import _head_coach_with_plans, _join_as_assistant

pytestmark = [pytest.mark.e2e, pytest.mark.show_intros]

ADMIN_HEADERS = {"X-Admin-Key": "e2e-admin"}
MULTITEAM_SEEN = "localStorage.setItem('gaffer_multiteam_seen', '1')"


def _mint_invite(base: str) -> str:
    r = httpx.post(base + "/api/admin/invites", headers=ADMIN_HEADERS, json={"note": "e2e"}, timeout=10)
    r.raise_for_status()
    return r.json()["link"].split("invite=")[1]


def _join_new_head(page: Page, base: str, email: str) -> None:
    page.add_init_script(MULTITEAM_SEEN)
    page.goto(base + f"/?invite={_mint_invite(base)}")
    page.fill("#join-email", email)
    page.fill("#join-name", "Coach")
    page.click("#btn-join-create")


def _expect_intro(page: Page, kicker: str) -> None:
    expect(page.locator("#whats-new")).to_be_visible()
    expect(page.locator("#wn-kicker")).to_have_text(kicker)
    expect(page.locator("#wn-why")).not_to_be_empty()


def _dismiss(page: Page, kicker: str) -> None:
    """Esc = Skip (works on single-card intros too, which have no Skip button)."""
    _expect_intro(page, kicker)
    page.keyboard.press("Escape")
    expect(page.locator("#whats-new")).to_be_hidden()


def test_welcome_tour_skip_lands_on_team_setup(auth_server, page: Page):
    _join_new_head(page, auth_server, "tour-skip@example.com")
    _expect_intro(page, "Welcome to Level")
    expect(page.locator("#wn-count")).to_have_text("1 of 4")
    expect(page.locator("#wn-title")).to_have_text("Fair time, done for you")
    page.click("#btn-wn-next")
    page.click("#btn-wn-next")
    expect(page.locator("#wn-count")).to_have_text("3 of 4")
    page.click("#btn-wn-skip")
    expect(page.locator("#whats-new")).to_be_hidden()
    expect(page.locator("#screen-tutorial")).to_be_visible()

    page.reload()
    expect(page.locator("#screen-tutorial")).to_be_visible()
    expect(page.locator("#whats-new")).to_be_hidden()


def test_welcome_tour_finish_follows_the_account_and_replays(auth_server, browser, page: Page):
    base = auth_server
    _join_new_head(page, base, "tour-done@example.com")
    _expect_intro(page, "Welcome to Level")
    for _ in range(3):
        page.click("#btn-wn-next")
    expect(page.locator("#btn-wn-skip")).to_be_hidden()
    expect(page.locator("#btn-wn-next")).to_have_text("Set up my team →")
    page.click("#btn-wn-next")
    expect(page.locator("#whats-new")).to_be_hidden()
    expect(page.locator("#screen-tutorial")).to_be_visible()

    # Another device, same account (cookies only, empty storage): no tour again.
    ctx = browser.new_context(service_workers="block")
    try:
        ctx.add_cookies(page.context.cookies())
        other = ctx.new_page()
        other.add_init_script(MULTITEAM_SEEN)
        other.goto(base + "/")
        expect(other.locator("#screen-tutorial")).to_be_visible()
        other.wait_for_timeout(500)
        expect(other.locator("#whats-new")).to_be_hidden()
    finally:
        ctx.close()

    # Naming the team opens the first Add Player form → the squad intro, once.
    page.fill("#tutorial-team-name", "Owls")
    page.click("#btn-tutorial-start")
    expect(page.locator("#player-form")).to_be_visible()
    _dismiss(page, "Adding players")
    page.click("#btn-cancel-player")
    page.click("#btn-squad-back")
    expect(page.locator("#screen-landing")).to_be_visible()

    # Settings replays the tour (and it's switch-off-able tips live there too).
    page.click("#btn-settings")
    expect(page.locator("#settings-show-tips")).to_be_checked()
    page.click("#btn-settings-replay-tour")
    _expect_intro(page, "Welcome to Level")
    expect(page.locator("#wn-count")).to_have_text("1 of 4")
    page.keyboard.press("Escape")
    expect(page.locator("#whats-new")).to_be_hidden()


def _coach_with_squad(base: str, email: str) -> dict:
    with httpx.Client(base_url=base, timeout=20) as api:
        token = api.post("/api/admin/invites", headers=ADMIN_HEADERS,
                         json={"note": email}).json()["link"].split("invite=")[1]
        api.post("/api/auth/redeem", json={"token": token, "email": email,
                                           "display_name": "Sam"}).raise_for_status()
        api.put("/api/squad/info", json={"team_name": "Owls"}).raise_for_status()
        for i, name in enumerate(["Ava", "Ben", "Cal", "Dan", "Eve", "Fay", "Gus"]):
            api.post("/api/squad/players", json={
                "name": name, "gk_status": "preferred" if i == 0 else "can_play",
            }).raise_for_status()
        return dict(api.cookies)


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_first_use_intros_show_once(auth_server, page: Page, flow: str):
    base = auth_server
    cookies = _coach_with_squad(base, f"first-use-{flow}@example.com")
    page.context.add_cookies([{"name": k, "value": v, "url": base} for k, v in cookies.items()])
    page.add_init_script(MULTITEAM_SEEN)
    page.on("dialog", lambda d: d.accept())
    page.goto(base + "/")
    expect(page.locator("#screen-landing")).to_be_visible()

    if flow == "season":
        page.click("#btn-season-mode")
        page.click("#btn-go-new-match")
        _dismiss(page, "Your first plan")
        page.fill("#opponent-input", "City")
        page.click("#btn-select-players")
        expect(page.locator("#screen-match-squad")).to_be_visible()
        _dismiss(page, "Who's coming?")
        page.click("#btn-generate")
    else:
        page.click("#btn-tournament-mode")
        page.click("#btn-new-tournament")
        _dismiss(page, "Your first plan")
        page.fill("#tournament-name-input", "Sixes")
        page.click("#btn-create-tournament")
        expect(page.locator("#screen-tournament-squad")).to_be_visible()
        page.click("#btn-generate-all-matches")
        expect(page.locator("#screen-tournament-lobby")).to_be_visible()
        _dismiss(page, "Tournament day")
        page.locator("#lobby-match-list .match-item-main").first.click()

    expect(page.locator("#screen-review")).to_be_visible()
    _dismiss(page, "Your first plan")
    page.click("#btn-review-view")
    page.click("#btn-adjust")
    _dismiss(page, "Tinker")
    page.click("#btn-adjust")
    page.click("#btn-start-match-cta")
    _dismiss(page, "Match day")
    expect(page.locator("#slot-label .slot-live-badge")).to_be_visible()

    # Shown once: the same screens again bring no intros.
    page.reload()
    expect(page.locator("#screen-landing")).to_be_visible()
    if flow == "season":
        page.click("#btn-season-mode")
        page.click("#btn-go-new-match")
        expect(page.locator("#screen-new-match")).to_be_visible()
    else:
        page.click("#btn-tournament-mode")
        page.click("#btn-new-tournament")
        expect(page.locator("#screen-new-tournament")).to_be_visible()
    page.wait_for_timeout(300)
    expect(page.locator("#whats-new")).to_be_hidden()


def test_tips_switch_turns_first_use_intros_off(auth_server, page: Page):
    base = auth_server
    cookies = _coach_with_squad(base, "tips-off@example.com")
    page.context.add_cookies([{"name": k, "value": v, "url": base} for k, v in cookies.items()])
    page.add_init_script(MULTITEAM_SEEN)
    page.goto(base + "/")
    page.click("#btn-settings")
    page.click(".settings-intros .switch-row")
    expect(page.locator("#settings-show-tips")).not_to_be_checked()
    page.click("#btn-settings-back")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    expect(page.locator("#screen-new-match")).to_be_visible()
    page.wait_for_timeout(300)
    expect(page.locator("#whats-new")).to_be_hidden()


def test_new_assistant_gets_the_assistant_welcome(auth_server, page: Page):
    token = _head_coach_with_plans(auth_server, "head-intro@example.com")
    _join_as_assistant(auth_server, page, token, "asst-intro@example.com")
    _expect_intro(page, "Welcome to Tigers")
    expect(page.locator("#wn-count")).to_have_text("1 of 3")
    for _ in range(2):
        page.click("#btn-wn-next")
    expect(page.locator("#btn-wn-next")).to_have_text("Let's go")
    page.click("#btn-wn-next")
    expect(page.locator("#whats-new")).to_be_hidden()
    # Shown once: nothing pops up on the next visit.
    page.reload()
    expect(page.locator("#screen-landing")).to_be_visible()
    page.wait_for_timeout(300)
    expect(page.locator("#whats-new")).to_be_hidden()


def test_every_card_follows_the_copy_rules(live_server, page: Page):
    """Title (≤5 words) · what · Why on every card, ids unique, coach language only."""
    page.goto(live_server + "/")
    result = page.evaluate("""async () => {
        const m = await import('/intros.js');
        return { ids: m.INTRO_IDS, slides: m.ALL_SLIDES() };
    }""")
    assert len(result["ids"]) == len(set(result["ids"]))
    for s in result["slides"]:
        assert s["title"] and s["body"] and s["why"] and s["demo"], s
        assert len(s["title"].split()) <= 5, s["title"]
        text = " ".join((s["title"], s["body"], s["why"])).lower()
        for word in ("violation", "algorithm", "slot", "database", "spell"):
            assert word not in text, (word, s["title"])
