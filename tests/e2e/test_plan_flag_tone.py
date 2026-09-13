"""Plan flags are quiet on a generated plan, loud once the coach has tinkered.

A plan straight out of the engine is its best effort — goal periods spread, bench
runs broken where they can be, game time level — so whatever it still flags is
usually the squad's arithmetic rather than a mistake. A ⚠ banner there teaches
coaches to scroll past. After a manual edit the same facts matter: that's the
change that can quietly cost a child minutes, so the warning tone returns.
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


def test_generated_plan_flags_are_quiet(seeded_squad, page: Page):
    _season_generate(page, seeded_squad)

    banner = page.locator("#review-warning")
    if banner.is_hidden():
        pytest.skip("this squad generated a plan with nothing to flag")
    expect(banner).to_have_class("review-warning review-warning-info")
    expect(page.locator("#review-warning .review-warning-head")).not_to_contain_text("⚠")


def test_flags_regain_the_warning_tone_after_a_tinker_edit(seeded_squad, page: Page):
    _season_generate(page, seeded_squad)

    # Tinker: swap a bench player onto the pitch, then back to the review grid.
    page.click("#btn-review-view")
    page.click("#btn-adjust")
    bench_name = page.locator("#bench-list .bench-player .bench-name").first.inner_text().strip()
    page.locator("#pitch .player-circle").last.click()
    page.locator("#swap-list .swap-item", has_text=bench_name).first.click()
    expect(page.locator("#swap-overlay")).to_be_hidden()
    page.click("#btn-adjust")
    page.click("#btn-review-plan")
    expect(page.locator("#screen-review")).to_be_visible()

    banner = page.locator("#review-warning")
    if banner.is_hidden():
        pytest.skip("the edited plan had nothing to flag")
    # A coach-edited plan that still flags something says so properly.
    expect(banner).not_to_have_class("review-warning review-warning-info")
    expect(page.locator("#review-warning .review-warning-head")).to_contain_text("⚠")


def test_keeper_in_goal_all_match_does_not_raise_a_game_time_flag(seeded_squad, page: Page):
    """With "Rotate keeper?" off, the specialist plays every slot by design. The
    plan flags must not report that as a game-time gap — the coach asked for it
    and no rotation can close it. Mirrors the domain rule in
    `validator._always_in_goal`."""
    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    page.fill("#opponent-input", "Rovers")
    # The switch input is visually hidden behind its styled track — click the label.
    page.click("label[for='match-share-gk']")
    expect(page.locator("#match-share-gk")).not_to_be_checked()
    page.click("#btn-select-players")
    page.click("#btn-generate")
    expect(page.locator("#screen-review")).to_be_visible()

    # The keeper is indeed in goal for every slot.
    keepers = page.locator("#review-grid .plan-grid .plan-cell.pos-gk")
    expect(keepers).not_to_have_count(0)
    names = {keepers.nth(i).inner_text() for i in range(keepers.count())}
    assert len(names) == 1, f"expected one keeper all match, got {names}"

    banner = page.locator("#review-warning")
    if banner.is_visible():
        assert "gap to the most-used player" not in banner.inner_text()
