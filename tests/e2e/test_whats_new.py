"""What's new: a returning coach sees it once on their next visit; skipping it
lights up Settings until they've looked; finishing it clears everything."""
import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = [pytest.mark.e2e, pytest.mark.show_whats_new]

ADMIN_HEADERS = {"X-Admin-Key": "e2e-admin"}


def _returning_coach(base: str, email: str) -> dict:
    with httpx.Client(base_url=base, timeout=20) as api:
        r = api.post("/api/admin/invites", headers=ADMIN_HEADERS, json={"note": email})
        token = r.json()["link"].split("invite=")[1]
        api.post("/api/auth/redeem", json={"token": token, "email": email,
                                           "display_name": "Sam"}).raise_for_status()
        api.put("/api/squad/info", json={"team_name": "Owls"}).raise_for_status()
        return dict(api.cookies)


def _sign_in(page: Page, base: str, cookies: dict) -> None:
    page.context.add_cookies([{"name": k, "value": v, "url": base} for k, v in cookies.items()])
    page.add_init_script("localStorage.setItem('gaffer_multiteam_seen', '1')")
    page.goto(base + "/")


def test_skip_lights_up_settings_until_viewed(auth_server, page: Page):
    _sign_in(page, auth_server, _returning_coach(auth_server, "wn-skip@example.com"))
    overlay = page.locator("#whats-new")
    expect(overlay).to_be_visible()
    expect(page.locator("#wn-count")).to_have_text("1 of 6")
    expect(page.locator("#wn-why")).not_to_be_empty()
    expect(page.locator("#btn-wn-back")).to_be_hidden()

    page.click("#btn-wn-skip")
    expect(overlay).to_be_hidden()
    expect(page.locator(".toast")).to_contain_text("Settings")
    expect(page.locator("#btn-settings.has-news")).to_be_visible()

    # Not shown again on the next visit — the lit-up button is the way back in.
    page.reload()
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(overlay).to_be_hidden()
    expect(page.locator("#btn-settings.has-news")).to_be_visible()

    page.click("#btn-settings")
    expect(page.locator("#btn-settings-whats-new.has-news")).to_be_visible()
    page.click("#btn-settings-whats-new")
    expect(overlay).to_be_visible()
    page.click("#btn-wn-skip")  # even skipping from Settings counts as looked
    expect(page.locator("#btn-settings-whats-new.has-news")).to_have_count(0)
    expect(page.locator("#btn-settings.has-news")).to_have_count(0)


def test_finishing_clears_it_for_good(auth_server, page: Page):
    _sign_in(page, auth_server, _returning_coach(auth_server, "wn-done@example.com"))
    for _ in range(5):
        page.click("#btn-wn-next")
    expect(page.locator("#wn-count")).to_have_text("6 of 6")
    expect(page.locator("#btn-wn-skip")).to_be_hidden()
    expect(page.locator("#btn-wn-next")).to_have_text("Got it")
    page.click("#btn-wn-next")
    expect(page.locator("#whats-new")).to_be_hidden()
    expect(page.locator("#btn-settings.has-news")).to_have_count(0)
    page.reload()
    expect(page.locator("#screen-landing")).to_be_visible()
    expect(page.locator("#whats-new")).to_be_hidden()

    # ?whatsnew=reset brings it back (for re-testing), and tidies the URL.
    page.goto(auth_server + "/?whatsnew=reset")
    expect(page.locator("#whats-new")).to_be_visible()
    assert "whatsnew" not in page.url
