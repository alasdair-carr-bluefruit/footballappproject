# Gaffer — CLAUDE.md

> This is the primary context file for AI-assisted development.
> Edit this file freely as the project evolves.

---

## Project Summary

A mobile-first Progressive Web App for grassroots youth football coaches to manage fair player rotation across a match. The system generates a full rotation plan (who plays where, when) across configurable match structures, enforcing GK tier priorities, DEF restrictions, position preferences, equal/competitive playing time, and soft skill-balance goals.

**Owner:** Personal project — multiple grassroots coaches. No login required for current versions.

---

## Current Phase

**v0.9 — Fairness & Trust** (next; see DEVELOPMENT_PLAN.md for the full roadmap)

Completed phases:
- v0.1: Core rotation algorithm (Python only)
- v0.2: Half-quarter subs, mid-quarter lock
- v0.3: Skill balancing
- v0.4: Web UI, pitch view, match day controls
- v0.5: FastAPI backend, SQLite persistence (SQLModel), Render deployment, integration tests
- v0.6: Multi-size (5v5–9v9), formations, fairness slider, rotation intensity, player position preferences, tinkering mode, shirt numbers, goal recording, share image, season stats, branding
- v0.7: Start Match lock, mid-match player removal/reinstatement, player history view (shipped 2026-05-23/24)
- v0.8: Tournament mode — tournament entity, cross-match cumulative fairness (`prior_slots`), guest players, manual rotation mode, tournament stats (shipped 2026-05-24 onwards). Not built: 8-a-side preset, knockout bracket structure (knockout matches can be added individually).

Next significant work: v0.9 (consecutive sit-out constraint, match timer, tinkering warning clarity, in-app bug reporting), then refactor phase, then v1.0 multi-user with email + magic link (see V1_MULTIUSER_PLAN.md + DEVELOPMENT_PLAN.md Phase D).

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI |
| Algorithm | Pure Python, no I/O dependencies |
| Database | SQLite via SQLModel (PostgreSQL planned for v1.0 multi-user) |
| Frontend | Vanilla JS (ES modules), Pico.css, PWA/Service Worker |
| Testing | pytest + pytest-bdd (Gherkin), pytest-asyncio |
| Linting | ruff, mypy |
| Hosting | Render + Neon (single-user instances); DECIDED for v1.0 multi-user: Railway Hobby + fresh Neon Postgres (V1_MULTIUSER_PLAN.md §8) |

---

## Key Commands

```bash
pip install -e ".[dev]"
pytest                    # all tests (~115)
pytest -m unit            # fast, no DB/server
pytest -m bdd             # Gherkin BDD scenarios
pytest -m integration     # DB + HTTP tests
ruff check .
```

---

## Repository Layout

```
football-app-project/
├── CLAUDE.md
├── BRAND.md              ← Brand guidelines (v1.4) — Gaffer identity, Tinkering mode spec
├── requirements.md
├── PHASES.md
├── pyproject.toml
├── main.py               ← FastAPI app entry point
│
├── assets/brand/
│   ├── tokens.json       ← Design tokens (colours, typography, tinkering mode spec)
│   ├── texture-paper.jpg ← Paper texture for Tinkering mode
│   ├── icon-app.svg
│   ├── logo-gaffer-primary.svg
│   ├── logo-gaffer-reversed.svg
│   └── logo-gaffer-mono-light.svg
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
│   ├── api/              ← FastAPI routers (matches, squad, tournaments)
│   └── db/               ← SQLite repositories, additive migration pattern
│
├── frontend/
│   ├── index.html
│   ├── app.js            ← All UI logic (ES modules)
│   ├── api.js            ← Fetch wrappers
│   ├── style.css
│   └── sw.js             ← Service Worker
│
└── tests/
    ├── unit/
    │   ├── algorithm/    ← test_multi_size.py, test_fairness.py
    │   └── models/       ← test_game_config.py
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

### Player position preferences (hard constraints)
- `preferred_positions: list[str]` — positions the player CAN play (empty = any)
- `best_position: str` — their strongest position
- Algorithm never assigns a player outside their preferred_positions (when set)
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

### Substitution rules (configurable per team size via GameConfig)
- Mid-period: `config.mid_period_subs` (2 for 5/6v5, 3 for 7v7, 4 for 9v9)
- Period break: `config.break_subs` (5 for 5/6v5, 4 for 7v7, unlimited for 9v9)
- GK never changes mid-period

### Skill balance (soft)
- Outfield skill total balanced across slots via iterative pairwise swaps
- GK excluded from skill calculation

---

## Tinkering Mode

When `editMode` is active:
- Pitch gets `.whiteboard` class → paper texture (`texture-paper.jpg`) via `mix-blend-mode: multiply` over lighter green base (`#72C49A`)
- Player circles: normal border hidden; amber wobble ring via `::after` + SVG `pen-wobble` filter (scale 3.2)
- Bench stays crisp (no wobble off-pitch)
- "TINKERING" pill (Cabin Sketch font, amber fill) top-right of pitch
- Prev/Next buttons disabled while tinkering
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
- Goal counts stored keyed by `str(player_id)` in `goals_json`; the frontend sends names which the API converts to ids (duplicate names rejected at creation)
- DB migrations: additive only via `ALTER TABLE ... ADD COLUMN` in `create_db_and_tables()`; wrap in try/except for idempotency
- Keep commit messages to terse one-line comments
- Push directly to main — no PRs unless explicitly requested

---

## Known Limitations / Flaky Tests

- `test_players_with_no_specialist` (tests/bdd/steps/test_rotation.py) and `test_9_players_no_specialist_max_diff_1` (tests/unit/algorithm/test_validator.py) — ~10% failure rate; over-budget fallback redistributes time unevenly. Accepted.
- `test_7v7_mid_period_max_3_subs` (tests/unit/algorithm/test_multi_size.py) — ~5-10% failure rate. Accepted.
- Root cause for both: intentional `random.shuffle` in gk_selector/rotation_engine + over-budget fallback; consider seeding randomness in tests (DEVELOPMENT_PLAN.md Part 4).
- Position variety (≤2 types) can be violated for 9-player no-specialist squads. Accepted as algorithm warning.

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
| v0.9 | Consecutive sit-out constraint, timer, tinkering clarity, in-app bug report | BDD + integration |
| refactor | app.js modularisation, shared season/tournament components, Playwright smoke suite | Playwright parity tests |
| v1.0 | Multi-user, email + magic-link auth, PostgreSQL | All tests green + isolation/IDOR tests |
