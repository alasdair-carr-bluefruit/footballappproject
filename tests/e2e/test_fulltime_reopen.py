"""Playwright e2e — reopening a FINISHED match + the "hide score" toggle.

A completed match now reopens onto its Full Time result card (the shareable
summary), not the live pitch — coaches reopen finished matches mainly to share
the result. From the card, "View on pitch" browses the slots reliably from the
start. The card also carries an FA "hide score" slider (sub-U12 guidance): it
masks the scoreline to "X – X" (scorers stay) and persists per match. Parity is
exercised across both season and tournament.
"""

import pytest
from playwright.sync_api import Page, expect

from test_smoke import advance_to_report

pytestmark = pytest.mark.e2e

def _play_to_fulltime(page: Page, base: str, flow: str, opponent: str) -> None:
    """Create + play a match to full time; ends on #screen-fulltime.

    The e2e session shares one DB, so the caller passes a unique season opponent
    to reopen exactly the right match from the (global) season list.
    """
    page.goto(base + "/")
    if flow == "season":
        page.click("#btn-season-mode")
        page.click("#btn-go-new-match")
        page.fill("#opponent-input", opponent)
        page.click("#btn-select-players")
        page.click("#btn-generate")
    else:
        page.click("#btn-tournament-mode")
        page.click("#btn-new-tournament")
        page.fill("#tournament-name-input", opponent)  # tournament name; lobby is scoped to it
        page.click("#btn-create-tournament")
        page.click("#btn-generate-all-matches")
        page.locator("#lobby-match-list .match-item-main").first.click()

    expect(page.locator("#screen-review")).to_be_visible()
    page.click("#btn-review-start")
    expect(page.locator("#live-badge")).to_be_visible()
    advance_to_report(page)
    page.click("#btn-next")  # summary's "Confirm ▶" -> full time
    expect(page.locator("#screen-fulltime")).to_be_visible()


def _reopen(page: Page, flow: str, opponent: str) -> None:
    if flow == "season":
        page.locator("#match-list .match-item", has_text=opponent).first.locator(
            ".match-item-main"
        ).click()
    else:
        # Tournament lobby is scoped to the tournament we just played, so the
        # completed match is its first (and only played) item.
        page.locator("#lobby-match-list .match-item-main").first.click()


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_finished_match_reopens_to_fulltime_and_browses_pitch(seeded_squad, page: Page, flow):
    opponent = f"Reopen United {flow}"
    _play_to_fulltime(page, seeded_squad, flow, opponent)
    page.click("#btn-ft-done")

    # Reopen the finished match → lands on the Full Time card, NOT the pitch.
    _reopen(page, flow, opponent)
    expect(page.locator("#screen-fulltime")).to_be_visible()
    expect(page.locator("#screen-pitch")).to_be_hidden()

    # "View on pitch" browses the slots reliably from the start (Prev disabled at
    # slot 0; the old bug landed on wherever current_slot was frozen).
    page.click("#btn-ft-pitch")
    expect(page.locator("#screen-pitch")).to_be_visible()
    expect(page.locator("#slot-counter")).to_contain_text("Slot 1 of")
    expect(page.locator("#btn-prev")).to_be_disabled()

    # The "◀ Full Time" pill returns to the result card.
    page.click("#btn-fulltime-pill")
    expect(page.locator("#screen-fulltime")).to_be_visible()


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_hide_score_masks_and_persists(seeded_squad, page: Page, flow):
    opponent = f"Hidden Rovers {flow}"
    _play_to_fulltime(page, seeded_squad, flow, opponent)

    # Scoreline visible by default (numeric), no FA caption.
    expect(page.locator("#ft-hidden-note")).to_be_hidden()
    expect(page.locator("#ft-our-score")).not_to_have_text("X")

    # Toggle hide → both numbers mask to "X", caption appears (scorers unaffected).
    page.click(".ft-hide-row .switch-slider")  # the input is visually hidden
    expect(page.locator("#ft-our-score")).to_have_text("X")
    expect(page.locator("#ft-their-score")).to_have_text("X")
    expect(page.locator("#ft-hidden-note")).to_be_visible()

    page.click("#btn-ft-done")

    # Reopen → the masked state persisted: still on the card, still hidden, toggle on.
    _reopen(page, flow, opponent)
    expect(page.locator("#screen-fulltime")).to_be_visible()
    expect(page.locator("#ft-hidden-note")).to_be_visible()
    expect(page.locator("#ft-our-score")).to_have_text("X")
    expect(page.locator("#ft-hide-score")).to_be_checked()

    # Toggle back off → the real scoreline returns and the caption hides.
    page.click(".ft-hide-row .switch-slider")  # the input is visually hidden
    expect(page.locator("#ft-hidden-note")).to_be_hidden()
    expect(page.locator("#ft-our-score")).not_to_have_text("X")
