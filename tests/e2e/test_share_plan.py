"""Playwright e2e — "Share" the team sheet from the review screen (season +
tournament parity).

Coaches were screenshotting the plan grid and pasting it into their co-coaches'
WhatsApp group; this button renders that same grid as a PNG. Headless Chromium
has no native share sheet (`navigator.canShare` is false for files), so the
handler falls through to a download — which proves the button → canvas → file
wiring end to end. We assert a .png download with the plan's own filename.
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
    page.fill("#tournament-name-input", "Share Cup")
    page.click("#btn-create-tournament")
    page.click("#btn-generate-all-matches")
    page.locator("#lobby-match-list .match-item-main").first.click()


_NAV = {"season": _season_generate, "tournament": _tournament_open_first}


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_share_plan_downloads_png(seeded_squad, page: Page, flow):
    """Both single-match flows offer Share on the review screen and produce a PNG."""
    _NAV[flow](page, seeded_squad)
    expect(page.locator("#screen-review")).to_be_visible()
    expect(page.locator("#btn-review-share")).to_be_visible()

    with page.expect_download() as dl:
        page.click("#btn-review-share")
    name = dl.value.suggested_filename
    assert name.startswith("team-sheet-") and name.endswith(".png"), name
    # A real image, not an empty blob.
    assert dl.value.path().stat().st_size > 2000


def test_share_all_tournament_plans_downloads_png(seeded_squad, page: Page):
    """The combined "Review all plans" page shares every match in one image."""
    page.goto(seeded_squad + "/")
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    page.fill("#tournament-name-input", "Combined Cup")
    page.click("#btn-create-tournament")
    page.click("#btn-generate-all-matches")
    page.click("#btn-tournament-review")

    expect(page.locator("#screen-review")).to_be_visible()
    # Only offered once the plans have finished generating.
    expect(page.locator("#review-grid .review-card").first).to_be_visible()
    expect(page.locator("#btn-review-share")).to_be_visible()

    with page.expect_download() as dl:
        page.click("#btn-review-share")
    assert dl.value.suggested_filename == "team-sheets-combined-cup.png"
    assert dl.value.path().stat().st_size > 2000
