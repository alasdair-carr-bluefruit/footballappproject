"""Nov 2026 quick wins: remembered settings, "N of M coming", live tap menu,
period auto-start once the clock has run, plain-language plan grid, squad entry.

Season ⇄ tournament parity: shared behaviours run against both flows.
"""

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.test_live_browse import _LIVE_NAV

pytestmark = pytest.mark.e2e


# ── Remembered settings ──────────────────────────────────────────────────────

def test_season_new_match_remembers_last_settings(seeded_squad, page: Page):
    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    expect(page.locator("#size-picker .size-btn.active")).to_have_attribute("data-size", "5")
    page.click('#size-picker .size-btn[data-size="7"]')
    page.click("#match-show-timer + .switch-slider")  # switch off
    page.fill("#opponent-input", "Memory FC")
    page.click("#btn-select-players")
    page.click("#btn-generate")
    expect(page.locator("#screen-review")).to_be_visible()

    page.click("#btn-review-back")
    page.click("#btn-go-new-match")
    expect(page.locator("#size-picker .size-btn.active")).to_have_attribute("data-size", "7")
    expect(page.locator("#match-show-timer")).not_to_be_checked()
    expect(page.locator("#match-length")).to_have_value("12.5")
    expect(page.locator("#opponent-input")).to_have_value("")  # per-match fields stay fresh


def test_tournament_new_remembers_last_settings(seeded_squad, page: Page):
    page.goto(seeded_squad + "/")
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    page.fill("#tournament-name-input", "Memory Cup")
    page.click('#tournament-size-picker .size-btn[data-size="7"]')
    page.check("#tournament-halftime")
    page.click("#btn-create-tournament")
    expect(page.locator("#screen-tournament-squad")).to_be_visible()

    page.click("#btn-tournament-squad-back")
    page.click("#btn-new-tournament")
    expect(page.locator("#tournament-size-picker .size-btn.active")).to_have_attribute("data-size", "7")
    expect(page.locator("#tournament-halftime")).to_be_checked()
    expect(page.locator("#tournament-name-input")).to_have_value("")


def test_size_buttons_show_age_groups(seeded_squad, page: Page):
    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    expect(page.locator('#size-picker .size-btn[data-size="7"] .size-age')).to_have_text("U10–U11")


# ── "N of M coming" ──────────────────────────────────────────────────────────

def _season_picker(page: Page, base: str) -> str:
    page.goto(base + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    page.click("#btn-select-players")
    return "#avail-list", "#avail-count"


def _tournament_picker(page: Page, base: str):
    page.goto(base + "/")
    page.click("#btn-tournament-mode")
    page.click("#btn-new-tournament")
    page.fill("#tournament-name-input", "Count Cup")
    page.click("#btn-create-tournament")
    return "#tournament-squad-list", "#tournament-avail-count"


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_availability_count(seeded_squad, page: Page, flow):
    list_sel, count_sel = (_season_picker if flow == "season" else _tournament_picker)(page, seeded_squad)
    boxes = page.locator(f"{list_sel} input[type=checkbox]")
    expect(boxes.first).to_be_visible()
    n = boxes.count()
    expect(page.locator(count_sel)).to_have_text(f"{n} of {n} coming")
    boxes.first.uncheck()
    expect(page.locator(count_sel)).to_have_text(f"{n - 1} of {n} coming")
    # Skill stars are not shown on the player picker.
    expect(page.locator(f"{list_sel} .avail-skill")).to_have_count(0)


# ── Live pitch tap menu ──────────────────────────────────────────────────────

@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_tap_player_opens_goal_injury_menu(seeded_squad, page: Page, flow):
    _LIVE_NAV[flow](page, seeded_squad)
    page.locator("#pitch .player-circle").first.click()
    expect(page.locator("#player-action-overlay")).to_be_visible()
    expect(page.locator("#btn-action-remove")).to_be_visible()
    page.click("#btn-action-goal")
    expect(page.locator("#pitch .goal-badge")).to_have_count(1)

    # Cancel closes it without doing anything.
    page.locator("#pitch .player-circle").nth(1).click()
    page.click("#btn-action-cancel")
    expect(page.locator("#player-action-overlay")).to_be_hidden()
    expect(page.locator("#pitch .goal-badge")).to_have_count(1)


# ── Next starts the next period once its time is up ──────────────────────────

@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_next_starts_period_when_time_is_up(seeded_squad, page: Page, flow):
    _LIVE_NAV[flow](page, seeded_squad)
    # Wind the stored match clock back an hour, as if the period has been played.
    page.evaluate("""() => {
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        try {
          const v = JSON.parse(localStorage.getItem(k));
          if (v && typeof v === "object" && "startedAt" in v) {
            v.startedAt -= 60 * 60 * 1000;
            localStorage.setItem(k, JSON.stringify(v));
          }
        } catch (_) { /* not JSON */ }
      }
    }""")
    page.click("#btn-next")   # mid-period slot (browse)
    page.click("#btn-next")   # next period's first slot → starts it, no prompt
    expect(page.locator("#new-period-hint")).to_be_hidden()
    expect(page.locator("#slot-label .slot-live-badge")).to_be_visible()
    expect(page.locator("#btn-jump-live")).to_be_hidden()


# ── Plain-language plan grid ─────────────────────────────────────────────────

def test_plan_grid_plain_headers_and_skill_toggle(seeded_squad, page: Page):
    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    page.click("#btn-select-players")
    page.click("#btn-generate")
    grid = page.locator("#review-grid")
    expect(grid.locator(".plan-head").first).to_contain_text("start")
    expect(grid.locator(".plan-head").nth(1)).to_contain_text("mid")
    expect(grid.locator(".plan-skill").first).to_be_visible()  # shown by default
    page.click(".plan-skill-toggle")
    expect(grid.locator(".plan-skill")).to_have_count(0)


# ── Squad entry ──────────────────────────────────────────────────────────────

def test_save_and_add_another_and_position_hint(seeded_squad, page: Page):
    page.goto(seeded_squad + "/")
    page.click("#btn-squad-management")
    expect(page.locator("#btn-squad-back")).to_have_text("◀ Home")
    page.click("#btn-add-player")
    page.fill("#input-name", "Quickwin Keeper")
    page.click('#position-checkboxes .pos-check:has(input[value="GK"])')
    # Only GK ticked → asked outright whether they're keeper-only.
    expect(page.locator("#keeper-only-row")).to_be_visible()
    page.click("#input-keeper-only + .switch-slider")
    page.click("#btn-save-add-another")
    # Form stays open, cleared, for the next player; the list behind has the new one.
    expect(page.locator("#player-form")).to_be_visible()
    expect(page.locator("#input-name")).to_have_value("")
    page.click("#btn-cancel-player")
    row = page.locator(".player-item", has_text="Quickwin Keeper")
    expect(row.locator(".badge-gk")).to_have_text("Keeper only")
    # Clean up so other tests' squads are unaffected.
    row.locator("[data-del]").click()
    page.click("#btn-delete-player-confirm")
    expect(page.locator(".player-item", has_text="Quickwin Keeper")).to_have_count(0)


@pytest.mark.parametrize("flow", ["season", "tournament"])
def test_injury_sub_keeps_rest_of_lineup(seeded_squad, page: Page, flow):
    """Injured on the pitch → pick who comes on; nobody else in the slot moves."""
    _LIVE_NAV[flow](page, seeded_squad)
    names = page.locator("#pitch .circle-name")
    before = names.all_inner_texts()
    victim = before[0]
    page.locator("#pitch .player-circle").first.click()
    page.click("#btn-action-remove")
    expect(page.locator("#swap-title")).to_have_text(f"Who comes on for {victim}?")
    sub = page.locator("#swap-list .swap-item .swap-name").first.inner_text()
    page.locator("#swap-list .swap-item").first.click()
    expect(page.locator("#pitch .circle-name", has_text=sub)).to_have_count(1)
    after = names.all_inner_texts()
    assert after == [sub] + before[1:]  # same positions, only the injured child replaced
    # ...and they're out of the re-planned rest of the match.
    page.wait_for_timeout(300)
    if page.locator("#fairness-overlay").is_visible():  # time-impact note after a removal
        page.click("#btn-fairness-confirm")
    page.click("#btn-next")
    expect(page.locator("#pitch .circle-name", has_text=victim)).to_have_count(0)


def test_rested_player_shows_as_owed_next_time(seeded_squad, page: Page):
    """Untick → Rested; once that match is played, next week's picker shows time owed."""
    import httpx

    page.goto(seeded_squad + "/")
    page.click("#btn-season-mode")
    page.click("#btn-go-new-match")
    page.click("#btn-select-players")
    first = page.locator("#avail-list .avail-item").first
    name = first.locator(".avail-name").inner_text()
    first.locator("input[type=checkbox]").uncheck()
    expect(first.locator(".avail-reason")).to_be_visible()
    first.locator('.reason-chip[data-reason="rested"]').click()
    expect(page.locator("#avail-count")).to_contain_text("· 1 rested")
    expect(first.locator("input[type=checkbox]")).not_to_be_checked()  # chip didn't re-tick
    page.click("#btn-generate")
    expect(page.locator("#screen-review")).to_be_visible()

    # Finish that match (API shortcut), then start next week's.
    with httpx.Client(base_url=seeded_squad, timeout=10) as api:
        mid = api.get("/api/matches/").json()[0]["id"]
        api.post(f"/api/matches/{mid}/progress", json={"current_slot": 7, "status": "completed"})
    page.click("#btn-review-back")
    page.click("#btn-go-new-match")
    page.click("#btn-select-players")
    row = page.locator("#avail-list .avail-item", has_text=name)
    expect(row.locator(".avail-owed")).to_contain_text("owed")
    page.click("#btn-generate")
    expect(page.locator("#review-owed")).to_contain_text(name)
