"""Granular positions: a coach can switch detailed positions on, set a few,
switch back to DEF/MID/ATT and on again without losing anything."""

import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def _toggle(page: Page):
    page.click("#input-granular + .switch-slider")


def test_granular_toggle_is_reversible(seeded_squad, page: Page):
    try:
        page.goto(seeded_squad + "/")
        page.click("#btn-squad-management")
        expect(page.locator("#input-granular")).not_to_be_checked()

        # On → asked first; cancel leaves it off.
        _toggle(page)
        expect(page.locator("#granular-overlay")).to_be_visible()
        page.click("#btn-granular-cancel")
        expect(page.locator("#input-granular")).not_to_be_checked()
        _toggle(page)
        page.click("#btn-granular-confirm")
        expect(page.locator("#input-granular")).to_be_checked()

        # Detailed picks in the player form.
        page.click("#btn-add-player")
        page.fill("#input-name", "Wing Kid")
        expect(page.locator('#position-checkboxes input[value="DEF"]')).to_have_count(0)
        page.click('#position-checkboxes .pos-check:has(input[value="LW"])')
        page.click("#player-form [type=submit]:not(#btn-save-add-another)")
        row = page.locator(".player-item", has_text="Wing Kid")
        expect(row.locator(".badge-pos")).to_have_text(["LW"])

        # Off → shown by line; editing and saving keeps the detail.
        _toggle(page)
        expect(page.locator("#input-granular")).not_to_be_checked()
        expect(row.locator(".badge-pos")).to_have_text(["ATT"])
        row.locator("[data-edit]").click()
        expect(page.locator('#position-checkboxes input[value="FWD"]')).to_be_checked()
        page.click("#player-form [type=submit]:not(#btn-save-add-another)")
        expect(row.locator(".badge-pos")).to_have_text(["ATT"])

        # On again → LW is still there.
        _toggle(page)
        page.click("#btn-granular-confirm")
        expect(row.locator(".badge-pos")).to_have_text(["LW"])
    finally:
        with httpx.Client(base_url=seeded_squad, timeout=10) as api:
            api.put("/api/squad/info", json={"granular_positions": False})
            for p in api.get("/api/squad/players").json():
                if p["name"] == "Wing Kid":
                    api.delete(f"/api/squad/players/{p['id']}")
