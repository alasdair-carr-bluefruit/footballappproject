"""Duplicate player names are caught in the form, not by a browser alert.

Two players can't share a name (case and spaces don't count). The squad form and
the tournament "temporary player" form both keep the form open with everything
the coach typed and say so under the name field. Neither test saves a clashing
player, so the shared seeded squad is left as it was.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _no_dialogs(page: Page) -> list[str]:
    seen: list[str] = []
    page.on("dialog", lambda d: (seen.append(d.message), d.dismiss()))
    return seen


def _open_squad(page: Page, base: str) -> None:
    page.goto(base + "/")
    expect(page.locator("#screen-landing")).to_be_visible()
    page.click("#btn-squad-management")
    expect(page.locator("#screen-squad")).to_be_visible()


def test_add_player_with_taken_name_keeps_form_open(seeded_squad, page: Page):
    dialogs = _no_dialogs(page)
    _open_squad(page, seeded_squad)

    page.click("#btn-add-player")
    page.fill("#input-name", "  gary keeper ")  # a different case + spaces is still Gary
    page.locator("#position-checkboxes .pos-mid").click()
    page.fill("#input-shirt-number", "42")
    page.click("#player-form [type=submit]")

    err = page.locator("#input-name-error")
    expect(err).to_be_visible()
    expect(err).to_contain_text("already got a player called 'Gary Keeper'")
    expect(page.locator("#player-form")).to_be_visible()
    # Nothing the coach typed is lost.
    expect(page.locator("#position-checkboxes input[value=MID]")).to_be_checked()
    expect(page.locator("#input-shirt-number")).to_have_value("42")

    # Typing clears the message.
    page.fill("#input-name", "Gary K")
    expect(err).to_be_hidden()
    page.click("#btn-cancel-player")
    assert dialogs == []


def test_renaming_a_player_to_a_taken_name_is_refused(seeded_squad, page: Page):
    dialogs = _no_dialogs(page)
    _open_squad(page, seeded_squad)

    page.locator("#player-list li", has_text="Bob Wing").locator("[data-edit]").click()
    page.fill("#input-name", "CARL MID")
    page.click("#player-form [type=submit]")
    expect(page.locator("#input-name-error")).to_contain_text("'Carl Mid'")
    expect(page.locator("#player-form")).to_be_visible()

    # Saving a player under their own name is fine.
    page.fill("#input-name", "Bob Wing")
    page.click("#player-form [type=submit]")
    expect(page.locator("#player-form")).to_be_hidden()
    expect(page.locator("#player-list")).to_contain_text("Bob Wing")
    assert dialogs == []


def test_temporary_player_from_player_list_opens_and_checks_names(seeded_squad, page: Page):
    """The pre-generate "+ Add temporary player" button opens the form (it used to
    throw before opening), refuses a squad player's name inline, and a new guest
    lands back on the same player list."""
    dialogs = _no_dialogs(page)
    page.goto(seeded_squad + "/")
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    page.fill("#tournament-name-input", "Name Cup")
    page.click("#btn-create-tournament")
    expect(page.locator("#screen-tournament-squad")).to_be_visible()

    page.click("#btn-tournament-add-guest")
    expect(page.locator("#guest-form-overlay")).to_be_visible()
    page.fill("#guest-name", "alan back")
    page.click("#btn-add-guest-confirm")
    expect(page.locator("#guest-name-error")).to_contain_text("'Alan Back'")
    expect(page.locator("#guest-form-overlay")).to_be_visible()

    page.fill("#guest-name", "Leo Guest")
    expect(page.locator("#guest-name-error")).to_be_hidden()
    page.click("#btn-add-guest-confirm")
    expect(page.locator("#guest-form-overlay")).to_be_hidden()
    expect(page.locator("#screen-tournament-squad")).to_be_visible()
    expect(page.locator(".avail-item-guest", has_text="Leo Guest")).to_be_visible()
    assert dialogs == []
