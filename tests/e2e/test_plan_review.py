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
    """Both flows land on #screen-review showing the compact position grid
    (position rows), a per-player slots strip, and the single-match actions."""
    _NAV[flow](page, seeded_squad)

    expect(page.locator("#screen-review")).to_be_visible()
    expect(page.locator("#screen-pitch")).to_be_hidden()

    # Compact position grid: a GK row + outfield position rows.
    expect(page.locator("#review-grid .plan-grid")).to_have_count(1)
    expect(page.locator("#review-grid .plan-rowlabel").first).to_have_text("GK")
    # Per-player slots strip preserves the fairness overview.
    expect(page.locator("#review-grid .plan-count-chip")).not_to_have_count(0)

    # Actions offered on a single-match review.
    expect(page.locator("#review-actions-single")).to_be_visible()
    expect(page.locator("#btn-review-start")).to_be_visible()
    expect(page.locator("#btn-review-view")).to_be_visible()


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_review_browse_tinker_and_start(seeded_squad, page: Page, flow):
    """'View on pitch' browses slots read-only (Prev/Next work); the pitch's
    Tinker toggles editing; '◀ Plan' returns; Start goes live."""
    _NAV[flow](page, seeded_squad)
    expect(page.locator("#screen-review")).to_be_visible()

    # View on pitch → browse mode (edit OFF), so slot nav works.
    page.click("#btn-review-view")
    expect(page.locator("#screen-pitch")).to_be_visible()
    expect(page.locator("#edit-mode-badge")).to_be_hidden()

    # Flick to the next slot — the counter advances (no sub interstitial in the way).
    expect(page.locator("#slot-counter")).to_contain_text("Slot 1 of")
    page.click("#btn-next")
    expect(page.locator("#slot-counter")).to_contain_text("Slot 2 of")

    # Tinker toggles the editor on/off on the pitch.
    page.click("#btn-adjust")
    expect(page.locator("#edit-mode-badge")).to_be_visible()
    page.click("#btn-adjust")
    expect(page.locator("#edit-mode-badge")).to_be_hidden()

    # "◀ Plan" pill returns to the review grid.
    page.click("#btn-review-plan")
    expect(page.locator("#screen-review")).to_be_visible()

    # Start from the review screen → live pitch.
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

    # Combined page: at least one match card, each with a position grid;
    # single-match actions hidden (you start matches individually from their own review).
    cards = page.locator("#review-grid .review-card")
    expect(cards).not_to_have_count(0)
    expect(cards.first.locator(".plan-grid")).to_have_count(1)
    expect(page.locator("#review-actions-single")).to_be_hidden()

    # Open ▶ → that match's single review, where Start Match is offered.
    cards.first.locator(".review-open-btn").click()
    expect(page.locator("#screen-review")).to_be_visible()
    expect(page.locator("#review-actions-single")).to_be_visible()
    expect(page.locator("#btn-review-start")).to_be_visible()
