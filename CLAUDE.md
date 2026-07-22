# Level — CLAUDE.md

> **Rebranded Gaffer → "Level" (2026-07-16).** New palette (Studio Green /
> Signal Lime), Space Mono + VT323 typography, spirit-level identity, and a
> re-derived Tinker mode. Brand source of truth: `BRAND.md` + `assets/brand/tokens.json`
> (mirrored by `frontend/style.css` `:root`). Internal `localStorage` keys keep
> their `gaffer_` prefix on purpose (renaming resets live coaches' onboarding/timers).

> This is the primary context file for AI-assisted development.
> Edit this file freely as the project evolves.

---

## Project Summary

A mobile-first Progressive Web App for grassroots youth football coaches to manage fair player rotation across a match. The system generates a full rotation plan (who plays where, when) across configurable match structures, enforcing GK tier priorities, DEF restrictions, position preferences, equal/competitive playing time, and soft skill-balance goals.

**Owner:** Personal project — multiple grassroots coaches. No login required for current versions.

---

## Current Phase

**Multi-user (v1.1) — SHIPPED & LIVE on `feat/multi-user`.** Magic-link auth (no
PIN), invite-only onboarding, `AccountDB`/`InviteDB`/`LoginTokenDB`, the `deps.py`
isolation seam (`get_current_account`/`get_current_squad` + `owned_*` IDOR guards),
early-access capture + Resend email, and a separate static marketing site
(`marketing/`, Cloudflare Pages, `keepthingslevel.com`) with the app on
`app.keepthingslevel.com`. **Scope note:** the shipped model is now **1 account ↔ N
squads** — `SquadDB.account_id` is the owner FK, `AccountDB.squad_id` is the *active*
squad pointer, and the `teams` router (list/create/activate/delete) manages them. The
`SquadMembershipDB` join + roles are still deferred, so **co-coach (multiple accounts
per squad) depends on adding that membership layer next** (single access point:
`owned_squad` in `deps.py`).

Earlier: the **Refactor Phase (C.1–C.7)** and **Phase D.1 "Review the plan" screen**
are done; D.2 (tinker undo/redo) + D.3 (export revisit) remain (now tracked as
Forward Roadmap **T3.3**).

**Tier 1 progress: COMPLETE ✅** — T1.1 multi-team ✅ (shipped 2026-07-21 — `SquadDB.account_id`
owner + `teams` router + header pill switcher; wider pill visibility + landing callout 2026-07-22),
T1.2 signed-out→marketing link ✅ (live), T1.3 Settings + account self-service ✅ (update-email
2026-07-20, **invite-a-friend shipped 2026-07-22**), T1.4 clear-squad-&-data ✅ (2026-07-20).
**Next up = Tier 2** (share-image/growth surfaces, FA-season SEO content). See DEVELOPMENT_PLAN.md
(reprioritised 2026-07-18); the roadmap is ordered by value × effort × demand (Tiers 1–4), not by
dependency phases.
**Live refactor tracker: `docs/refactor/NEXT_STEPS.md`.**

Completed phases:
- v0.1: Core rotation algorithm (Python only)
- v0.2: Half-quarter subs, mid-quarter lock
- v0.3: Skill balancing
- v0.4: Web UI, pitch view, match day controls
- v0.5: FastAPI backend, SQLite persistence (SQLModel), Render deployment, integration tests
- v0.6: Multi-size (5v5–9v9), formations, fairness slider, rotation intensity, player position preferences, tinkering mode, shirt numbers, goal recording, share image, season stats, branding
- v0.7: Start Match lock, mid-match player removal/reinstatement, player history view (shipped 2026-05-23/24)
- v0.8: Tournament mode — tournament entity, cross-match cumulative fairness (`prior_slots`), guest players, manual rotation mode, tournament stats (shipped 2026-05-24 onwards). Not built: 8-a-side preset, knockout bracket structure.
- v0.9: Consecutive sit-out constraint, match timer (count-up, persistent), fairness impact on removal/reinstatement, in-app bug reporting, All-rounder default rotation, inspection-based DB migrations (shipped 2026-07-10)

- v1.1: Multi-user — magic-link auth, invite-only, per-account squad isolation, marketing site + early-access (shipped on `feat/multi-user`; 1 account ↔ 1 squad).

Next significant work: **Forward Roadmap Tier 1** (DEVELOPMENT_PLAN.md, reprioritised 2026-07-18) — **T1.1 multi-team** + T1.3 invite-a-friend remain (T1.2, T1.4, and T1.3 settings/update-email shipped 2026-07-20).

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI |
| Algorithm | Pure Python, no I/O dependencies |
| Database | SQLModel — SQLite locally/tests, **Neon PostgreSQL in production** (Alembic migrations) |
| Frontend | Vanilla JS (ES modules), Pico.css, PWA/Service Worker |
| Testing | pytest + pytest-bdd (Gherkin), pytest-asyncio |
| Linting | ruff, mypy |
| Hosting | **Live: Railway + Neon Postgres + Cloudflare** (app.keepthingslevel.com), single shared multi-user instance. Old Render single-user clones retained as fallback until each coach is migrated. |

---

## Key Commands

```bash
pip install -e ".[dev]"
pytest                    # all tests (~316)
pytest -m unit            # fast, no DB/server
pytest -m bdd             # Gherkin BDD scenarios
pytest -m integration     # DB + HTTP tests
pytest -m e2e             # Playwright browser smoke suite (season + tournament golden paths)
pytest -m "not e2e"       # everything except the browser suite
ruff check .

# First-time e2e setup (Playwright browser binary):
playwright install chromium
```

The e2e suite (`tests/e2e/`) launches the real app in a uvicorn subprocess
against a throwaway SQLite DB, seeds a squad via the API, then drives a real
Chromium through create → generate → tinker → start → advance → full time for
both season and tournament. Service workers are blocked so a stale SW cache
never masks a real change.

---

## Repository Layout

```
football-app-project/
├── CLAUDE.md
├── BRAND.md              ← Brand guidelines (v1.4) — Level identity, Tinkering mode spec
├── requirements.md
├── DEVELOPMENT_PLAN.md   ← Forward roadmap (refactor → v1.0 → v1.1)
├── docs/
│   ├── refactor/NEXT_STEPS.md ← Live refactor-phase (C.4) tracker
│   └── adr/              ← Architecture decision records
├── pyproject.toml
├── main.py               ← FastAPI app entry point
│
├── assets/brand/
│   ├── tokens.json       ← Design tokens (Level palette, typography, tinker spec) — mirrors style.css :root
│   ├── icon-app.svg / icon-app.png     ← App icon (spirit-level mark)
│   ├── LevelLinesTransparent.png       ← Wide spirit-level lockup (landing screen)
│   └── wordmark.svg     ← Wordmark vector (app renders live Space Mono text; raster wordmarks removed)
│
├── backend/
│   ├── models/
│   │   ├── player.py     ← Player, GKTier, preferred_positions, best_position
│   │   ├── match.py      ← Match, Squad, game_config, fairness
│   │   ├── rotation.py   ← Position enum, SlotAssignment, RotationPlan, normalize_position
│   │   └── game_config.py ← Formation, GameConfig, PRESET_CONFIGS
│   ├── algorithm/
│   │   ├── rotation_engine.py ← generate_rotation (parameterised for any team size)
│   │   ├── gk_selector.py
│   │   ├── time_balancer.py   ← equal + competitive modes
│   │   ├── skill_balancer.py
│   │   └── validator.py       ← configurable sub limits, position variety
│   ├── api/              ← FastAPI routers (thin HTTP adapters)
│   ├── services/         ← match_service, tournament_service (C.5), analytics (C.7)
│   └── db/               ← SQLite repositories, additive migration pattern
│
├── frontend/            ← ES modules (no framework); app.js is a thin entry point
│   ├── index.html
│   ├── app.js            ← Entry point — side-effect imports of the modules below
│   ├── state.js          ← Shared mutable `state` object + ensureGameConfigs/refreshShirtNumbers
│   ├── pitch.js          ← Pitch render, tinkering, match-day controls, timer, full-time
│   ├── setup-form.js     ← Size/formation/fairness config form (shared season+tournament)
│   ├── season.js         ← Season flow (home, new match, stats, history, export)
│   ├── tournament.js     ← Tournament flow (create, squad, lobby, guests)
│   ├── screens.js        ← Onboarding, landing, squad management, bug report
│   ├── api.js            ← Fetch wrappers
│   ├── toast.js          ← Toast notifications + withSaveToast retry helper (C.7)
│   ├── style.css
│   └── sw.js             ← Service Worker
│
└── tests/
    ├── unit/
    │   ├── algorithm/    ← test_multi_size.py, test_fairness.py
    │   └── models/       ← test_game_config.py
    ├── e2e/              ← Playwright browser smoke suite (season + tournament)
    ├── integration/      ← test_squad.py, test_matches.py
    └── bdd/
        ├── features/     ← multi_size.feature, rotation_generation.feature, etc.
        └── steps/
```

---

## Supported Team Sizes

| Size | Formation options | Match structure | Mid-period subs | Break subs |
|------|-------------------|-----------------|-----------------|------------|
| 5v5  | 1-2-1, 2-1-1 | 4 quarters × 2 = 8 slots | 2 | 5 |
| 6v6  | 1-3-1, 2-2-1, 1-2-2 | 4 quarters × 2 = 8 slots | 2 | 5 |
| 7v7  | 2-3-1, 1-3-2, 2-2-2 | 4 quarters × 2 = 8 slots | 3 | 4 |
| 9v9  | 3-3-2, 2-4-2, 3-2-3, 3-4-1, 4-3-1 | 2 halves × 2 = 4 slots | 4 | full squad |

---

## Algorithm Constraints

### Position naming
- Formation-derived: DEF → LB/CB/RB, MID → LM/CM/RM/CAM, FWD → LW/CF/RW
- Internal codes: DEF, DEF2, DEF3, DEF4 / MID1, MID2, MID3, MID4, MID5 / FWD, FWD2, FWD3
- All normalize via `normalize_position()` to "DEF"/"MID"/"FWD"/"GK" for variety checking

### Player position preferences (soft / best-effort)
- `preferred_positions: list[str]` — positions the player CAN play (empty = any)
- `best_position: str` — their strongest position
- Algorithm strongly prefers to keep a player within their preferred_positions,
  but this is best-effort, not a hard guarantee: when the preferred pool for a
  slot empties, the position assigner falls back to any eligible player rather
  than leave a position unfilled (`_assign_outfield_positions` → `pool_for`).
  DEF restriction (`def_restricted`) and GK specialist status ARE hard.
- `def_restricted` and `gk_status` are derived from position selections in the UI

### Shirt numbers
- Optional `shirt_number: int | None` stored on PlayerDB
- Displayed in player token instead of initials when set
- Duplicate detection: second player with same number shown with red token/badge
- API rejects duplicate player names (422); goal counts are stored keyed by player id (names are only used in the UI and converted to ids at the API boundary)

### Position rotation intensity (configurable, 0-100)
- 0 (Specialist): players stay in best_position, max 1 position type
- 50 (Balanced): regular rotation through preferred positions
- 100 (All-rounder): experience all preferred positions
- Controls `max_pos_types` and whether algorithm prefers variety vs consistency

### Playing time fairness (configurable, 0-100)
- 0-15 (Equal): max 1 slot difference between any two players
- 16-100 (Competitive): skill_rating weighted distribution, guaranteed minimum ~floor(total/n)-1

### GK tier priority (derived from position preferences)
1. `specialist` — only GK checked, never outfield
2. `preferred` — GK is best_position
3. `can_play` — GK checked among other positions
4. `emergency_only` — GK not checked

### Specialist-GK time sharing (`share_gk`, per match/tournament)
- A specialist never plays outfield, so in a small squad they'd otherwise be in
  goal every slot and play ~2× everyone else. The `share_gk` flag (setup-form
  switch "Rotate keeper?", **default on**) controls this:
  - **on** — the keeper splits goal duty (plays alternate periods, rests the
    rest while a backup covers) so their total time matches the squad.
  - **off** — keeper stays in goal all match (traditional; plays more).
  - Forced **off** automatically when `squad_size <= players_per_slot` (no bench
    to cover goal). Domain default `None` = legacy "share only at 10+ players"
    heuristic, kept so bare `Match()` unit tests are unaffected.
- Threads through the same layers as `rotation_intensity`; mirror both flows.

### Substitution rules (configurable per team size via GameConfig)
- Mid-period: `config.mid_period_subs` (2 for 5/6v5, 3 for 7v7, 4 for 9v9)
- Period break: `config.break_subs` (5 for 5/6v5, 4 for 7v7, unlimited for 9v9)
- GK never changes mid-period

### Skill balance (soft)
- Outfield skill total balanced across slots via iterative pairwise swaps
- GK excluded from skill calculation

---

## Tinkering Mode

"Modulation, not replacement" (see BRAND.md §6). When `editMode` is active:
- Pitch gets `.whiteboard` class → tints one step lighter to Ghost Green (`--tinker-surface: #4E7E4A`). No paper, no `mix-blend-mode`, no SVG wobble filters (all removed in the Level rebrand).
- Player coins **invert**: dark fill (`--pitch-deep`) + chalk text + a chunky **dashed Provisional-Chalk outline** (`--provisional`). GK/incoming keep their identity colour but still get the dashed outline. Bench stays crisp (off-pitch).
- "TINKERING" pill top-right: Signal-Lime fill, Studio-Green text, Space Mono, blinking terminal `_` cursor.
- Prev/Next disabled while tinkering; exiting toasts "Sorted. Plan updated."
- Drag-and-drop to swap players within a slot; tap to open swap picker
- Slot locked after any edit; re-calculation adjusts only unlocked future slots

---

## Data Model Summary

```
Player (PlayerDB)
  name: str                   ← unique within squad
  shirt_number: int | None    ← optional squad number
  gk_status: str              ← GKTier value
  def_restricted: bool        ← derived from position prefs
  skill_rating: int (1–5)
  preferred_positions: str    ← JSON list e.g. '["DEF","MID"]'
  best_position: str          ← e.g. "MID" or ""

Match (MatchDB)
  date, opponent, home_away, opponent_goals
  quarters, quarter_length_mins
  team_size: int, formation: str
  fairness: str, fairness_value: int (0-100)
  rotation_intensity: int (0-100)

Squad (SquadDB)
  team_name: str, team_logo: str  ← base64 DataURL

Formation
  defense: int, midfield: int, forward: int
  → outfield_positions(), team_size, notation

GameConfig
  team_size, formation, periods, period_length_mins
  mid_period_subs, break_subs, period_label
```

---

## Non-Obvious Conventions

- `slot_index` runs 0–N. Period boundary = `slot_index % 2 == 0`. Mid-period = `slot_index % 2 == 1`.
- Period labels: "Quarter" for 5/6/7v7, "Half" for 9v9
- Position codes vary by formation — always use `config.formation.outfield_positions()`
- `normalize_position()` converts DEF2→"DEF", MID3→"MID", etc.
- Goal counts keyed by `str(player_id)`, now in the relational `GoalRecordDB` table (JSON blobs `goals_json`/`slots_json`/`removed_players_json`/`available_player_ids_json` were normalised into `GoalRecordDB`/`SlotDB`/`SlotAssignmentDB`/`MatchAvailabilityDB` in Phase C.6); the frontend sends names which the API converts to ids (duplicate names rejected at creation)
- DB migrations: **Alembic** is the tool for schema changes since Phase C.6 (`backend/db/migrations/`). The legacy additive `ALTER TABLE ... ADD COLUMN` bridge (wrapped in try/except) still exists for older columns; new tables/columns go through an Alembic revision.
- **Season ⇄ tournament parity (important):** the two flows must not drift. They
  share the setup form, pitch renderer, tinkering, goals and full-time by design;
  but `season.js` and `tournament.js` still hold separate list/load entry points and
  some flow-specific handlers. When you fix a bug or add UX in one flow, mirror it in
  the other **in the same change** (e.g. `loadHome` ⇄ `loadTournamentHome`, `openMatch`
  ⇄ `loadTournamentLobby`), and prefer a parity e2e test that parametrizes
  `["season","tournament"]` (see `tests/e2e/`). Do not ship a one-sided fix.
- Keep commit messages to terse one-line comments
- Push directly to main — no PRs unless explicitly requested

---

## Known Limitations / Flaky Tests

- **Test flakiness — FIXED (RNG now seeded).** The rotation algorithm shuffles
  candidates (`gk_selector`/`rotation_engine`), which used to make a few edge-case
  assertions (`test_players_with_no_specialist`, `test_9_players_no_specialist_max_diff_1`,
  `test_7v7_mid_period_max_3_subs`) flake ~10% when a draw hit the accepted
  over-budget fallback. Both suites now seed `random` before every test — autouse
  fixtures in `tests/unit/conftest.py` and `tests/bdd/conftest.py` (seed 1234) — so
  the tests are deterministic. NB: this pins the RNG to a passing draw; it does not
  change the underlying algorithm behaviour (below), which is still an accepted
  limitation. If either seed file changes, re-verify those cases.
- **Algorithm limitation (accepted, not a test bug):** for 9-player no-specialist
  squads the over-budget fallback can redistribute time unevenly (one player a slot
  over) and position variety (≤2 types) can be violated. Surfaced as an algorithm
  warning; tightening it is a future engine change, not required for v1.0.

---

## Phase Gates

| Phase | What's built | Tests |
|---|---|---|
| v0.1–v0.3 | Algorithm + models + skill balance | unit + BDD ✓ |
| v0.4 | Web UI + pitch view | Manual browser test ✓ |
| v0.5 | FastAPI + SQLite | integration tests ✓ |
| v0.6 | Multi-size, tinkering, shirt numbers, match day | 105 tests ✓ |
| v0.7 | Start Match, removal/reinstatement, history | integration ✓ |
| v0.8 | Tournament mode | integration (test_tournaments.py) ✓ |
| v0.9 | Consecutive sit-out constraint, timer, tinkering clarity, in-app bug report | BDD + integration ✓ |
| refactor | app.js modularisation, Playwright smoke suite, CSS/HTML unit tests | Playwright parity tests |
| v1.0 | Plan Review UX (table view, per-player counts, tinker/undo) | Playwright golden path |
| v1.1 | Multi-user, email + magic-link auth, PostgreSQL | All tests green + isolation/IDOR tests |
