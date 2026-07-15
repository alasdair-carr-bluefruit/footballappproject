"""Playwright e2e — create/edit-match length, show-timer switch, validation."""
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _open_new_match(page: Page, base: str) -> None:
    page.goto(base + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    expect(page.locator("#screen-new-match")).to_be_visible()


def _create_planned_match(page: Page, base: str, opponent: str = "Rovers") -> None:
    """Create + generate a (planned) season match, leaving us on the review screen."""
    _open_new_match(page, base)
    page.fill("#opponent-input", opponent)
    page.click("#btn-select-players")
    page.click("#btn-generate")
    expect(page.locator("#screen-review")).to_be_visible()


def test_length_prefills_per_size(seeded_squad, page: Page):
    _open_new_match(page, seeded_squad)
    expect(page.locator("#match-length")).to_have_value("10")
    expect(page.locator("#match-length-label")).to_have_text("Minutes per quarter")
    page.click('#size-picker .size-btn[data-size="7"]')
    expect(page.locator("#match-length")).to_have_value("12.5")
    page.click('#size-picker .size-btn[data-size="9"]')
    expect(page.locator("#match-length")).to_have_value("30")
    expect(page.locator("#match-length-label")).to_have_text("Minutes per half")


def test_timer_is_a_switch_next_to_minutes(seeded_squad, page: Page):
    _open_new_match(page, seeded_squad)
    # The control is a sliding switch (checkbox inside .switch), not a bare tickbox.
    expect(page.locator(".inline-pair .switch #match-show-timer")).to_have_count(1)
    expect(page.locator("#match-show-timer")).to_be_checked()


def test_timer_hidden_when_switched_off(seeded_squad, page: Page):
    _open_new_match(page, seeded_squad)
    page.fill("#opponent-input", "Rovers")
    page.click("#match-show-timer + .switch-slider")  # toggle the switch off
    expect(page.locator("#match-show-timer")).not_to_be_checked()
    page.click("#btn-select-players")
    page.click("#btn-generate")
    page.click("#btn-review-start")
    expect(page.locator("#screen-pitch")).to_be_visible()
    expect(page.locator("#live-badge")).to_be_visible()
    expect(page.locator("#match-timer")).to_be_hidden()


def test_timer_shown_by_default(seeded_squad, page: Page):
    _create_planned_match(page, seeded_squad)
    page.click("#btn-review-start")
    expect(page.locator("#match-timer")).to_be_visible()


def test_length_over_cap_is_blocked(seeded_squad, page: Page):
    _open_new_match(page, seeded_squad)  # 5v5 → quarters, cap 22.5
    page.fill("#opponent-input", "Rovers")
    page.fill("#match-length", "30")
    messages: list[str] = []
    page.on("dialog", lambda d: (messages.append(d.message), d.accept()))
    page.click("#btn-select-players")
    # Blocked: stays on the config screen, doesn't advance to player selection.
    expect(page.locator("#screen-new-match")).to_be_visible()
    assert any("22.5" in m for m in messages)


def test_edit_pencil_prefills_form(seeded_squad, page: Page):
    _create_planned_match(page, seeded_squad, "EditMe FC")
    # Back to the season home; the planned match carries an edit pencil.
    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    item = page.locator("#match-list .match-item", has_text="EditMe FC").first
    expect(item.locator(".match-edit")).to_have_count(1)
    item.locator(".match-edit").click()
    expect(page.locator("#screen-new-match")).to_be_visible()
    expect(page.locator("#new-match-title")).to_have_text("Edit Match")
    expect(page.locator("#opponent-input")).to_have_value("EditMe FC")


def test_landing_export_bar_removed(seeded_squad, page: Page):
    _create_planned_match(page, seeded_squad)
    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    expect(page.locator("#match-list .match-item")).not_to_have_count(0)
    # The old match-list CSV export bar is gone.
    expect(page.locator("#export-bar")).to_have_count(0)


def test_tournament_show_timer_is_a_switch(seeded_squad, page: Page):
    page.goto(seeded_squad + "/")
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    expect(page.locator(".switch #tournament-show-timer")).to_have_count(1)
    expect(page.locator("#tournament-show-timer")).to_be_checked()
