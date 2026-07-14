"""Playwright e2e — Phase D "Review the plan" screen (season + tournament).

Generating a plan now lands on the dedicated #screen-review (a per-player
rotation grid + Tinker/Start/Back), rather than dropping straight onto the pitch.
Parity is exercised across both flows; the tournament also gets a combined
"Review all plans" page that stacks one grid per match.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _season_generate(page: Page, base: str) -> None:
    page.goto(base + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    page.fill("#opponent-input", "Rovers")
    page.click("#btn-select-players")
    page.click("#btn-generate")


def _tournament_open_first(page: Page, base: str) -> None:
    page.goto(base + "/")
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    page.fill("#tournament-name-input", "Summer Cup")
    page.click("#btn-create-tournament")
    page.click("#btn-generate-all-matches")
    page.locator("#lobby-match-list .match-item-main").first.click()


_NAV = {"season": _season_generate, "tournament": _tournament_open_first}


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_generation_lands_on_review_with_grid(seeded_squad, page: Page, flow):
    """Both flows land on #screen-review showing a per-player grid with slot
    totals + a skill-total row, and the single-match actions."""
    _NAV[flow](page, seeded_squad)

    expect(page.locator("#screen-review")).to_be_visible()
    expect(page.locator("#screen-pitch")).to_be_hidden()

    # Per-player rows (each with a slot total) + exactly one skill-total row.
    expect(page.locator("#review-grid .report-row")).not_to_have_count(0)
    expect(page.locator("#review-grid .report-row-skill")).to_have_count(1)
    expect(page.locator("#review-grid .report-slots").first).to_contain_text("slot")

    # Actions offered on a single-match review.
    expect(page.locator("#review-actions-single")).to_be_visible()
    expect(page.locator("#btn-review-start")).to_be_visible()
    expect(page.locator("#btn-review-tinker")).to_be_visible()


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_review_tinker_roundtrip_then_start(seeded_squad, page: Page, flow):
    """Tinker opens the pitch editor; '◀ Plan' returns to the grid; Start goes
    live — the read-only-grid / edit-on-pitch model from the plan."""
    _NAV[flow](page, seeded_squad)
    expect(page.locator("#screen-review")).to_be_visible()

    # Tinker → pitch editor (edit mode on).
    page.click("#btn-review-tinker")
    expect(page.locator("#screen-pitch")).to_be_visible()
    expect(page.locator("#edit-mode-badge")).to_be_visible()

    # Done editing → the "◀ Plan" pill returns to the review grid.
    page.click("#btn-adjust")
    expect(page.locator("#btn-review-plan")).to_be_visible()
    page.click("#btn-review-plan")
    expect(page.locator("#screen-review")).to_be_visible()

    # Start the match from the review screen → live pitch.
    page.click("#btn-review-start")
    expect(page.locator("#screen-pitch")).to_be_visible()
    expect(page.locator("#live-badge")).to_be_visible()


def test_tournament_review_all_plans_stacks_a_grid_per_match(seeded_squad, page: Page):
    """The lobby's 'Review all plans' generates any missing rotations and shows
    one read-only card (with its own grid) per match; 'Open ▶' drops into that
    match's own review where Start lives."""
    page.goto(seeded_squad + "/")
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    page.fill("#tournament-name-input", "Cup Review")
    page.click("#btn-create-tournament")
    page.click("#btn-generate-all-matches")
    expect(page.locator("#screen-tournament-lobby")).to_be_visible()

    page.click("#btn-tournament-review")
    expect(page.locator("#screen-review")).to_be_visible()

    # Combined page: at least one match card, each with a grid; single-match
    # actions are hidden (you start matches individually from their own review).
    cards = page.locator("#review-grid .review-card")
    expect(cards).not_to_have_count(0)
    expect(cards.first.locator(".report-row")).not_to_have_count(0)
    expect(page.locator("#review-actions-single")).to_be_hidden()

    # Open ▶ → that match's single review, where Start Match is offered.
    cards.first.locator(".review-open-btn").click()
    expect(page.locator("#screen-review")).to_be_visible()
    expect(page.locator("#review-actions-single")).to_be_visible()
    expect(page.locator("#btn-review-start")).to_be_visible()
