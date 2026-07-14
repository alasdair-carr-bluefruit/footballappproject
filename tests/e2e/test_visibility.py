"""C.3 — CSS/HTML visibility tests.

Guards the `display:flex` / `[hidden]` class of bug: an element that JS "hides"
by setting the `hidden` attribute (or that CSS hides via a class like
`.edit-mode-badge` → `.visible`) must actually stop rendering. Because `.screen`
and most controls set `display:flex`, a missing `[hidden] { display:none
!important }` rule — or a class toggle that never fires — would leave a
"hidden" element on screen while every state-machine assertion still passed.

Playwright's `to_be_visible` / `to_be_hidden` assert *rendered* visibility
(computed style), not just the presence of the attribute, so they catch exactly
that regression. The two flows share the pitch renderer, so each pitch-state
test runs against both season and tournament.
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


# ── Navigation helpers: land on the pitch in plan-review (pre-Start) state ──────

def _goto_landing(page: Page, base: str) -> None:
    page.goto(base + "/")
    expect(page.locator("#screen-landing")).to_be_visible()


def _season_to_plan_review(page: Page, base: str) -> None:
    _goto_landing(page, base)
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    page.fill("#opponent-input", "Rovers")
    page.click("#btn-select-players")
    page.click("#btn-generate")
    expect(page.locator("#screen-pitch")).to_be_visible()


def _tournament_to_plan_review(page: Page, base: str) -> None:
    _goto_landing(page, base)
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    page.fill("#tournament-name-input", "Summer Cup")
    page.click("#btn-create-tournament")
    page.click("#btn-generate-all-matches")
    page.locator("#lobby-match-list .match-item-main").first.click()
    expect(page.locator("#screen-pitch")).to_be_visible()


_PLAN_REVIEW_NAV = {
    "season": _season_to_plan_review,
    "tournament": _tournament_to_plan_review,
}


# ── The core [hidden] vs display:flex invariant ────────────────────────────────

def test_hidden_screen_computes_to_display_none(seeded_squad, page: Page):
    """A `.screen` (author rule `display:flex`) that is hidden must compute to
    `display:none` — proving `[hidden] { display:none !important }` wins."""
    _goto_landing(page, seeded_squad)

    hidden_display = page.eval_on_selector(
        "#screen-home", "el => getComputedStyle(el).display")
    assert hidden_display == "none", (
        f"a hidden .screen must be display:none, got {hidden_display!r} — "
        "the [hidden] !important rule is not winning over .screen's display:flex")

    # Sanity check the assertion has teeth: the visible screen really is flex.
    visible_display = page.eval_on_selector(
        "#screen-landing", "el => getComputedStyle(el).display")
    assert visible_display == "flex", (
        f"the active .screen should be display:flex, got {visible_display!r}")


# ── Pitch state machine: which controls show in each phase ─────────────────────

@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_plan_review_controls_visibility(seeded_squad, page: Page, flow):
    """Before Start: Start-Match CTA + Tinker are offered; live-only chrome is
    hidden."""
    _PLAN_REVIEW_NAV[flow](page, seeded_squad)

    # Offered while reviewing the plan.
    expect(page.locator("#start-match-bar")).to_be_visible()
    expect(page.locator("#btn-start-match-cta")).to_be_visible()
    expect(page.locator("#btn-adjust")).to_be_visible()
    expect(page.locator("#manual-assign-bar")).to_be_visible()

    # Live-only chrome must stay hidden until the match starts.
    expect(page.locator("#live-badge")).to_be_hidden()
    expect(page.locator("#end-match-bar")).to_be_hidden()
    expect(page.locator("#match-timer")).to_be_hidden()
    expect(page.locator("#edit-mode-badge")).to_be_hidden()


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_edit_mode_toggles_visibility(seeded_squad, page: Page, flow):
    """Tinker on: the amber badge shows (via `.visible` class, not `hidden`), the
    Start bar hides and navigation is locked; toggling off restores review."""
    _PLAN_REVIEW_NAV[flow](page, seeded_squad)

    page.click("#btn-adjust")
    expect(page.locator("#edit-mode-badge")).to_be_visible()
    expect(page.locator("#start-match-bar")).to_be_hidden()
    expect(page.locator("#btn-prev")).to_be_disabled()
    expect(page.locator("#btn-next")).to_be_disabled()

    page.click("#btn-adjust")
    expect(page.locator("#edit-mode-badge")).to_be_hidden()
    expect(page.locator("#start-match-bar")).to_be_visible()


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_live_controls_visibility(seeded_squad, page: Page, flow):
    """After Start: live badge, End-Match bar and match timer appear; the
    Start-Match CTA is gone."""
    _PLAN_REVIEW_NAV[flow](page, seeded_squad)
    page.click("#btn-start-match-cta")

    expect(page.locator("#live-badge")).to_be_visible()
    expect(page.locator("#end-match-bar")).to_be_visible()
    expect(page.locator("#match-timer")).to_be_visible()
    expect(page.locator("#start-match-bar")).to_be_hidden()


# ── Overlays: default-hidden, and hidden while the pitch is up ─────────────────

@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_overlays_hidden_on_pitch(seeded_squad, page: Page, flow):
    """The swap picker and end-match confirm overlays must not be showing until
    explicitly opened."""
    _PLAN_REVIEW_NAV[flow](page, seeded_squad)

    expect(page.locator("#swap-overlay")).to_be_hidden()
    expect(page.locator("#end-match-overlay")).to_be_hidden()
    expect(page.locator("#new-period-hint")).to_be_hidden()


# ── Timer controls render at their intended tap-target size ────────────────────

def test_timer_pause_button_is_full_size(seeded_squad, page: Page):
    """Regression guard: an unclosed CSS comment once swallowed `.timer-btn`, so the
    pause button collapsed to the tiny browser default. Assert it renders at its
    intended ~56px tap target (proving the rule is live, not commented out)."""
    _season_to_plan_review(page, seeded_squad)
    page.click("#btn-start-match-cta")

    pause = page.locator("#btn-timer-pause")
    expect(pause).to_be_visible()
    box = pause.bounding_box()
    assert box is not None
    assert box["width"] >= 44 and box["height"] >= 44, f"pause button too small: {box}"
