"""#1 — goals on a finished match: restore on reopen + guarded editing.

A completed match must (a) show its stored scorers when reopened, and (b) refuse
silent goal edits — the coach has to confirm "edit the match report" first. The
restore half also closes a latent data-loss bug: before, reopening cleared
goalCounts, so any save overwrote the real tally with an empty one.

Uses a unique opponent and navigates back to slot 0 so the assertions are
deterministic under the session-scoped shared DB (other tests leave matches too).
"""

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

OPPONENT = "GoalGuard FC"  # unique so we reopen the right match from the list


def _long_press(page: Page, locator) -> None:
    """Simulate the 600ms long-press that records a goal on a player token."""
    locator.dispatch_event("pointerdown")
    page.wait_for_timeout(750)
    locator.dispatch_event("pointerup")


def _rewind_to_slot_0(page: Page) -> None:
    prev = page.locator("#btn-prev")
    for _ in range(20):
        if prev.is_disabled():
            return
        prev.click()
    raise AssertionError("never reached slot 0")


def test_completed_match_goals_restore_and_are_guarded(seeded_squad, page: Page):
    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    page.fill("#opponent-input", OPPONENT)
    page.click("#btn-select-players")
    page.click("#btn-generate")
    expect(page.locator("#screen-review")).to_be_visible()

    # Start the match and record one goal for the first on-pitch player at slot 0.
    page.click("#btn-review-start")
    expect(page.locator("#live-badge")).to_be_visible()
    _long_press(page, page.locator("#pitch .player-circle").first)
    expect(page.locator("#pitch .player-circle").first.locator(".goal-badge")).to_contain_text("1")

    # Play to the summary and end the match → goals persist, status=completed.
    # Next only browses now, so commit each period at its boundary to progress.
    # Final slot: Next reads "End Match" (opens summary); summary: Next reads
    # "Confirm ▶" (finalises to Full Time).
    btn = page.locator("#btn-next")
    for _ in range(40):
        txt = btn.text_content() or ""
        if "Confirm" in txt:
            break
        if "End Match" in txt:
            btn.click()
            continue
        if page.locator("#new-period-hint").is_visible():
            page.click("#btn-new-period-reset")
        btn.click()
    page.click("#btn-next")  # summary's "Confirm ▶" -> full time
    expect(page.locator("#screen-fulltime")).to_be_visible()
    page.click("#btn-ft-done")
    expect(page.locator("#screen-home")).to_be_visible()

    # Reopen the (now completed) match by its unique opponent name — a finished
    # match now lands on its Full Time result card (shareable summary), from which
    # "View on pitch" browses the slots.
    page.locator("#match-list .match-item", has_text=OPPONENT).first.locator(
        ".match-item-main"
    ).click()
    expect(page.locator("#screen-fulltime")).to_be_visible()
    page.click("#btn-ft-pitch")
    expect(page.locator("#screen-pitch")).to_be_visible()
    _rewind_to_slot_0(page)

    # (a) The stored goal is restored — reopening no longer shows an empty tally.
    first_token = page.locator("#pitch .player-circle").first
    expect(first_token.locator(".goal-badge")).to_contain_text("1")

    # (b) Editing is guarded: dismiss the confirm → goal unchanged.
    page.once("dialog", lambda d: d.dismiss())
    _long_press(page, first_token)
    expect(first_token.locator(".goal-badge")).to_contain_text("1")

    # Accept the confirm → the edit now goes through (same player → 2 goals).
    page.once("dialog", lambda d: d.accept())
    _long_press(page, first_token)
    expect(first_token.locator(".goal-badge")).to_contain_text("2")
