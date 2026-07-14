"""Playwright smoke suite — drives both flows through the same golden path.

Season and tournament share the setup form, pitch renderer and full-time screen,
so exercising both here is the regression net for the Phase C module split: if a
cross-module wiring breaks, one of these fails.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def advance_to_report(page: Page) -> None:
    """Play the match through to the last-slot report — Next then reads 'End Match'.

    Next only BROWSES now; the match progresses via the "Start period" prompt, so
    at each period boundary we commit the period before moving on. (#report-section
    is reused by the intermediate sub-changes view, so button text is the
    unambiguous signal that we're actually on the final report.)
    """
    btn = page.locator("#btn-next")
    for _ in range(40):
        if "End Match" in (btn.text_content() or ""):
            return
        # At the start of the next period? Commit it so the match actually advances.
        if page.locator("#new-period-hint").is_visible():
            page.click("#btn-new-period-reset")
        btn.click()
    raise AssertionError("never reached the match report after 40 Next clicks")


def test_season_golden_path(seeded_squad, page: Page):
    """create match → generate → start → advance to report → full time."""
    page.goto(seeded_squad + "/")
    expect(page.locator("#screen-landing")).to_be_visible()

    # Enter season mode and start a new match.
    page.click("#btn-season-mode")
    expect(page.locator("#screen-home")).to_be_visible()
    page.click("#btn-go-new-match")
    expect(page.locator("#screen-new-match")).to_be_visible()

    # Config form: default 5v5, just name the opponent, then pick players.
    page.fill("#opponent-input", "Rovers")
    page.click("#btn-select-players")
    expect(page.locator("#screen-match-squad")).to_be_visible()

    # All available players are pre-checked — generate → land on plan review.
    page.click("#btn-generate")
    expect(page.locator("#screen-review")).to_be_visible()
    expect(page.locator("#review-grid .plan-grid")).to_have_count(1)

    # View on pitch (browse), then tinker on/off there.
    page.click("#btn-review-view")
    expect(page.locator("#screen-pitch")).to_be_visible()
    expect(page.locator("#edit-mode-badge")).to_be_hidden()
    page.click("#btn-adjust")
    expect(page.locator("#edit-mode-badge")).to_be_visible()
    page.click("#btn-adjust")
    expect(page.locator("#edit-mode-badge")).to_be_hidden()

    # "◀ Plan" returns to the review screen, then start from there.
    page.click("#btn-review-plan")
    expect(page.locator("#screen-review")).to_be_visible()
    page.click("#btn-review-start")
    expect(page.locator("#live-badge")).to_be_visible()
    advance_to_report(page)

    # End the match → full-time screen with our team named.
    page.click("#btn-end-match")
    expect(page.locator("#screen-fulltime")).to_be_visible()
    expect(page.locator("#ft-home-name")).to_have_text("Testers FC")

    # Done returns to the season home.
    page.click("#btn-ft-done")
    expect(page.locator("#screen-home")).to_be_visible()


def test_tournament_golden_path(seeded_squad, page: Page):
    """create tournament → squad → generate matches → open match → play → full time.

    Also covers the §1d fix: full-time 'Done' on a tournament match returns to the
    tournament lobby (not the season home), via openMatch(id, "tournament").
    """
    page.goto(seeded_squad + "/")
    expect(page.locator("#screen-landing")).to_be_visible()

    page.click("#btn-tournament-mode")
    expect(page.locator("#screen-tournament-home")).to_be_visible()
    page.click("#btn-new-tournament")
    expect(page.locator("#screen-new-tournament")).to_be_visible()

    # Name it and create (default 5v5, default match count) → squad screen.
    page.fill("#tournament-name-input", "Summer Cup")
    page.click("#btn-create-tournament")
    expect(page.locator("#screen-tournament-squad")).to_be_visible()

    # All players pre-checked → generate all planned matches → lobby.
    page.click("#btn-generate-all-matches")
    expect(page.locator("#screen-tournament-lobby")).to_be_visible()

    # Open the first match (planned → generates a rotation → plan review),
    # then start it from the review screen and play it out.
    page.locator("#lobby-match-list .match-item-main").first.click()
    expect(page.locator("#screen-review")).to_be_visible()
    page.click("#btn-review-start")
    expect(page.locator("#live-badge")).to_be_visible()
    advance_to_report(page)
    page.click("#btn-end-match")
    expect(page.locator("#screen-fulltime")).to_be_visible()

    # §1d: Done routes back to the tournament lobby, not the season home.
    page.click("#btn-ft-done")
    expect(page.locator("#screen-tournament-lobby")).to_be_visible()


def test_failed_save_surfaces_retry_toast(seeded_squad, page: Page):
    """C.7: a failed write shows a retryable toast instead of vanishing silently.

    Aborts the goals-save request on end-match and asserts the toast (with a
    Retry action) appears — the golden paths only cover the success case where
    the toast never fires.
    """
    page.goto(seeded_squad + "/")
    expect(page.locator("#screen-landing")).to_be_visible()
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    page.fill("#opponent-input", "Rovers")
    page.click("#btn-select-players")
    page.click("#btn-generate")
    expect(page.locator("#screen-review")).to_be_visible()
    page.click("#btn-review-start")
    expect(page.locator("#live-badge")).to_be_visible()
    advance_to_report(page)

    # Make the goals save fail, then end the match.
    page.route("**/api/matches/*/goals", lambda route: route.abort())
    page.click("#btn-end-match")

    # A toast with a Retry action appears; the flow still completes to full time.
    expect(page.locator(".toast")).to_be_visible()
    expect(page.locator(".toast .toast-action")).to_have_text("Retry")
    expect(page.locator("#screen-fulltime")).to_be_visible()


def test_screens_are_mutually_exclusive(seeded_squad, page: Page):
    """Guards the [hidden]/display-flex class of bug: only one screen visible."""
    page.goto(seeded_squad + "/")
    expect(page.locator("#screen-landing")).to_be_visible()
    for hidden in ("#screen-home", "#screen-pitch", "#screen-review", "#screen-new-match",
                   "#screen-fulltime", "#screen-tutorial"):
        expect(page.locator(hidden)).to_be_hidden()
