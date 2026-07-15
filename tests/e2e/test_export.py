"""Playwright e2e — D.3 stats spreadsheet export (season + tournament parity).

Headless Chromium can't drive the native share sheet, but `navigator.canShare`
returns false for files there, so the export falls through to a download — which
proves the button → fetch → file wiring end to end. We assert an .xlsx download.
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
    expect(page.locator("#screen-review")).to_be_visible()


def _make_tournament(page: Page, base: str, name: str) -> None:
    page.goto(base + "/")
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    page.fill("#tournament-name-input", name)
    page.click("#btn-create-tournament")
    page.click("#btn-generate-all-matches")
    expect(page.locator("#screen-tournament-lobby")).to_be_visible()


def test_season_stats_export_downloads_xlsx(seeded_squad, page: Page):
    _season_generate(page, seeded_squad)

    # Back to the season home, into Season Stats — the Export button appears.
    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-stats")
    expect(page.locator("#screen-stats")).to_be_visible()
    expect(page.locator("#btn-export-stats")).to_be_visible()

    with page.expect_download() as dl:
        page.click("#btn-export-stats")
    assert dl.value.suggested_filename.endswith(".xlsx")


def test_single_tournament_stats_export_downloads_xlsx(seeded_squad, page: Page):
    _make_tournament(page, seeded_squad, "Parity Cup")

    page.click("#btn-tournament-stats")
    expect(page.locator("#tournament-stats-overlay")).to_be_visible()
    with page.expect_download() as dl:
        page.click("#btn-export-tournament-stats")
    assert dl.value.suggested_filename.endswith(".xlsx")


def test_all_tournament_stats_export_from_landing(seeded_squad, page: Page):
    _make_tournament(page, seeded_squad, "Aggregate Cup")

    # Back to the tournament landing page → All Tournament Stats → Export.
    page.click("#btn-lobby-back")
    expect(page.locator("#screen-tournament-home")).to_be_visible()
    expect(page.locator("#btn-all-tournament-stats")).to_be_visible()

    page.click("#btn-all-tournament-stats")
    expect(page.locator("#all-tournament-stats-overlay")).to_be_visible()
    with page.expect_download() as dl:
        page.click("#btn-export-all-tournament-stats")
    assert dl.value.suggested_filename.endswith(".xlsx")
