"""Connection-lost banner: entering Season with no server reachable must say so.

Before, loadHome swallowed the failure (`.catch(() => [])`), so an unreachable
server looked identical to "no matches yet". Now it surfaces a retryable toast and
an explanatory empty state.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_match_list_failure_shows_connection_toast(seeded_squad, page: Page):
    page.goto(seeded_squad + "/")
    expect(page.locator("#screen-landing")).to_be_visible()

    # Make ONLY the match-list request fail (offline / server down), then enter
    # Season. The glob targets the list endpoint's exact trailing-slash path, so
    # sibling routes (/config/…, /stats/…, /{id}) are untouched.
    matches_list = "**/api/matches/"
    page.route(matches_list, lambda route: route.abort())
    page.click("#btn-season-mode")

    # A retryable "Connection lost" toast appears, and the list explains itself
    # rather than falsely reading "No matches yet".
    expect(page.locator(".toast")).to_be_visible()
    expect(page.locator(".toast .toast-action")).to_have_text("Retry")
    expect(page.locator("#match-list")).to_contain_text("Couldn't reach the server")

    # Clear the failure and hit Retry → the real list loads.
    page.unroute(matches_list)
    page.click(".toast .toast-action")
    expect(page.locator("#match-list")).not_to_contain_text("Couldn't reach the server")


def test_tournament_list_failure_shows_connection_toast(seeded_squad, page: Page):
    """Parity: tournament mode must surface the same connection-lost affordance as
    season mode, not a misleading empty list."""
    page.goto(seeded_squad + "/")
    expect(page.locator("#screen-landing")).to_be_visible()

    tournaments_list = "**/api/tournaments/"
    page.route(tournaments_list, lambda route: route.abort())
    page.click("#btn-tournament-mode")

    expect(page.locator(".toast")).to_be_visible()
    expect(page.locator(".toast .toast-action")).to_have_text("Retry")
    expect(page.locator("#tournament-list")).to_contain_text("Couldn't reach the server")

    page.unroute(tournaments_list)
    page.click(".toast .toast-action")
    expect(page.locator("#tournament-list")).not_to_contain_text("Couldn't reach the server")
