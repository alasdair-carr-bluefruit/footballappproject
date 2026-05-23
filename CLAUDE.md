# Football Squad Rotation Manager — CLAUDE.md

> This is the primary context file for AI-assisted development.
> Edit this file freely as the project evolves.

---

## Project Summary

A mobile-first Progressive Web App for grassroots youth football coaches to manage fair player rotation across a match. The system generates a full rotation plan (who plays where, when) across configurable match structures, enforcing GK tier priorities, DEF restrictions, position preferences, equal/competitive playing time, and soft skill-balance goals.

**Owner:** Personal project — multiple grassroots coaches, no login required for v1.

---

## Current Phase

**v0.6 in progress — Multi-size support, configurable fairness & rotation**

Completed phases:
- v0.1: Core rotation algorithm (Python only)
- v0.2: Half-quarter subs, mid-quarter lock
- v0.3: Skill balancing
- v0.4: Web UI, pitch view, match day controls
- v0.5: FastAPI backend, SQLite persistence (SQLModel), Render deployment, integration tests
- v0.6 (partial): Multi-size (5v5–9v9), formations, fairness slider, position rotation slider, player position preferences

Next: **v0.6 completion — edge cases, real-world testing**

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI |
| Algorithm | Pure Python, no I/O dependencies |
| Database | SQLite via SQLModel |
| Frontend | Vanilla JS (ES modules), Pico.css, PWA/Service Worker |
| Testing | pytest + pytest-bdd (Gherkin), pytest-asyncio |
| Linting | ruff, mypy |

---

## Key Commands

```bash
pip install -e ".[dev]"
pytest                    # all tests
pytest -m unit            # fast, no DB/server
pytest -m bdd             # Gherkin BDD scenarios
ruff check .
```

---

## Repository Layout

```
football-rotation/
├── CLAUDE.md
├── requirements.md
├── PHASES.md
├── pyproject.toml
├── main.py                    ← FastAPI app entry point
│
├── backend/
│   ├── models/
│   │   ├── player.py          ← Player, GKTier, preferred_positions, best_position
│   │   ├── match.py           ← Match, Squad, game_config, fairness
│   │   ├── rotation.py        ← Position enum, SlotAssignment, RotationPlan, normalize_position
│   │   └── game_config.py     ← Formation, GameConfig, PRESET_CONFIGS
│   ├── algorithm/
│   │   ├── rotation_engine.py ← generate_rotation (parameterised for any team size)
│   │   ├── gk_selector.py
│   │   ├── time_balancer.py   ← equal + competitive modes
│   │   ├── skill_balancer.py
│   │   └── validator.py       ← configurable sub limits, position variety
│   ├── api/                   ← FastAPI routers
│   └── db/                    ← SQLite repositories
│
├── frontend/                  ← Vanilla JS PWA
│
└── tests/
    ├── unit/
    │   ├── algorithm/         ← test_multi_size.py, test_fairness.py
    │   └── models/            ← test_game_config.py
    ├── integration/
    └── bdd/
        ├── features/          ← multi_size.feature
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
- DEF positions: DEF, DEF2, DEF3, DEF4
- MID positions: MID1, MID2, MID3, MID4, MID5 (always numbered)
- FWD positions: FWD, FWD2, FWD3
- All normalize via `normalize_position()` to "DEF"/"MID"/"FWD"/"GK" for variety checking

### Player position preferences (hard constraints)
- `preferred_positions: list[str]` — positions the player CAN play (empty = any)
- `best_position: str` — their strongest position
- Algorithm never assigns a player outside their preferred_positions (when set)
- `def_restricted` and `gk_status` are derived from position selections in the UI

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

## Data Model Summary

```
Player
  name, gk_status (derived), def_restricted (derived)
  skill_rating: int (1–5)
  preferred_positions: list[str]  ← ["DEF","MID","FWD"] etc.
  best_position: str | None

Match
  date, opponent, quarters, quarter_length_mins
  game_config: GameConfig | None
  fairness: str, fairness_value: int (0-100)
  rotation_intensity: int (0-100)

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
- Period labels: "Quarter" for 5/6/7v5, "Half" for 9v9
- Position codes vary by formation — always use `config.formation.outfield_positions()`
- `normalize_position()` converts DEF2→"DEF", MID3→"MID", etc.
- Keep commit messages to terse one line comments

---

## Phase Gates

| Phase | What's built | Tests |
|---|---|---|
| v0.1–v0.3 | Algorithm + models + skill balance | unit + BDD |
| v0.4 | Web UI + pitch view | Manual browser test |
| v0.5 | FastAPI + SQLite | integration tests |
| v0.6 | Multi-size, fairness, rotation, positions | multi_size.feature, test_fairness.py, test_multi_size.py |
| v1.0 | Stable for real match use | All tests green |
