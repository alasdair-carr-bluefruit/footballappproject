"""#4 — live browse: preview future slots without advancing; tinker stays available.

The reported problem: flicking forward in a live match advanced it, so going back
left earlier slots locked. Now Next only browses; the match progresses via the
explicit "Start period" prompt. Verifies: browse forward/back freely, Tinker stays
available where it should, goals are refused off the live period, committing a
period is what actually advances play, and the live-slot indicator + jump-back.

Every test runs against BOTH season and tournament (parity — the pitch view is one
shared surface). Tournament matches are single-period by default, so these enable
half-time (2 halves) to exercise the same multi-period "Start period" flow.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _season_to_live(page: Page, seeded_squad) -> None:
    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    page.fill("#opponent-input", "Browsers United")
    page.click("#btn-select-players")
    page.click("#btn-generate")
    expect(page.locator("#screen-review")).to_be_visible()
    page.click("#btn-review-start")
    expect(page.locator("#live-badge")).to_be_visible()


def _tournament_to_live(page: Page, seeded_squad) -> None:
    page.goto(seeded_squad + "/")
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    page.fill("#tournament-name-input", "Browse Cup")
    page.check("#tournament-halftime")  # 2 periods → the "Start period" banner applies
    page.click("#btn-create-tournament")
    page.click("#btn-generate-all-matches")
    page.locator("#lobby-match-list .match-item-main").first.click()
    expect(page.locator("#screen-review")).to_be_visible()
    page.click("#btn-review-start")
    expect(page.locator("#live-badge")).to_be_visible()


_LIVE_NAV = {"season": _season_to_live, "tournament": _tournament_to_live}


def _browse_to_next_period_prompt(page: Page) -> None:
    """Click Next (browsing, not advancing) until the 'Start period' prompt shows."""
    hint = page.locator("#new-period-hint")
    for _ in range(12):
        if hint.is_visible():
            return
        page.click("#btn-next")
    raise AssertionError("never reached the next-period prompt while browsing")


def _long_press(page: Page, locator) -> None:
    locator.dispatch_event("pointerdown")
    page.wait_for_timeout(750)
    locator.dispatch_event("pointerup")


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_browse_does_not_advance_and_tinker_stays_available(seeded_squad, page: Page, flow):
    _LIVE_NAV[flow](page, seeded_squad)

    # Browse forward into the next period → "Start period" prompt (don't commit it).
    _browse_to_next_period_prompt(page)
    expect(page.locator("#new-period-hint")).to_be_visible()

    # Rewind all the way to slot 0.
    prev = page.locator("#btn-prev")
    for _ in range(12):
        if prev.is_disabled():
            break
        prev.click()

    # Slot 0 is still the live period (we never committed) → Tinker still offered.
    # Under the old bug, browsing forward would have locked this slot.
    expect(page.locator("#slot-counter")).to_contain_text("Slot 1 of")
    expect(page.locator("#btn-adjust")).to_be_visible()


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_goals_only_on_the_live_period(seeded_squad, page: Page, flow):
    _LIVE_NAV[flow](page, seeded_squad)

    # Sit at the next period's start WITHOUT committing it.
    _browse_to_next_period_prompt(page)

    # A long-press here records NO goal — we're browsing a non-live period.
    _long_press(page, page.locator("#pitch .player-circle").first)
    expect(page.locator("#pitch .goal-badge")).to_have_count(0)

    # Commit the period ("Start period") → now it's live and goals are accepted.
    page.click("#btn-new-period-reset")
    expect(page.locator("#new-period-hint")).to_be_hidden()
    _long_press(page, page.locator("#pitch .player-circle").first)
    expect(page.locator("#pitch .goal-badge")).to_have_count(1)


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_live_slot_indicator_and_jump_back(seeded_squad, page: Page, flow):
    _LIVE_NAV[flow](page, seeded_squad)

    # On the live slot: a LIVE badge marks it and there's nothing to jump to.
    expect(page.locator("#slot-label .slot-live-badge")).to_be_visible()
    expect(page.locator("#btn-jump-live")).to_be_hidden()

    # Browse away → a "Back to live" affordance appears.
    _browse_to_next_period_prompt(page)
    expect(page.locator("#btn-jump-live")).to_be_visible()
    expect(page.locator("#slot-label .slot-live-badge")).to_have_count(0)

    # Tap it → straight back to the live slot; badge returns, jump button gone.
    page.click("#btn-jump-live")
    expect(page.locator("#slot-counter")).to_contain_text("Slot 1 of")
    expect(page.locator("#slot-label .slot-live-badge")).to_be_visible()
    expect(page.locator("#btn-jump-live")).to_be_hidden()
