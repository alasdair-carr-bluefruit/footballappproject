# Football Squad Rotation Manager — CLAUDE.md

> This is the primary context file for AI-assisted development.
> Edit this file freely as the project evolves.

---

## Project Summary

A mobile-first Progressive Web App for a youth football coach to manage fair player rotation across a match. The system generates a full rotation plan (who plays where, when) across 8 half-quarter slots per match, enforcing GK tier priorities, DEF restrictions, equal playing time, and soft skill-balance goals.

**Owner:** Personal project — single coach, no login required for v1.

---

## Current Phase

**v0.1 — Core rotation algorithm (Python only, no UI, no API, no DB)**

Scope:
- Pure Python algorithm in `backend/algorithm/`
- Data models in `backend/models/`
- Unit tests in `tests/unit/algorithm/`
- BDD feature: `tests/bdd/features/rotation_generation.feature`

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI (v0.5+) |
| Algorithm | Pure Python, no I/O dependencies |
| Database | SQLite via SQLModel (v0.5+) |
| Frontend | Vanilla JS (ES modules), Pico.css, PWA/Service Worker (v0.4+) |
| Testing | pytest + pytest-bdd (Gherkin), pytest-asyncio |
| Linting | ruff, mypy |

---

## Key Commands

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run only unit tests (fast, no DB/server)
pytest -m unit

# Run BDD scenarios
pytest -m bdd

# Run linter
ruff check .
```

---

## Repository Layout

```
football-rotation/
├── CLAUDE.md                  ← YOU ARE HERE
├── requirements.md            ← Full functional + non-functional spec
├── PHASES.md                  ← Phase roadmap v0.1 → v1.0
├── pyproject.toml
│
├── backend/
│   ├── models/                ← Pure data shapes (Player, Match, RotationPlan…)
│   ├── algorithm/             ← Core engine — pure functions, zero I/O
│   ├── api/                   ← FastAPI routers (v0.5+)
│   └── db/                    ← SQLite repositories (v0.5+)
│
├── frontend/                  ← Vanilla JS PWA (v0.4+)
│
└── tests/
    ├── unit/                  ← Fast, isolated tests for algorithm + models
    ├── integration/           ← DB + HTTP endpoint tests (v0.5+)
    └── bdd/                   ← Gherkin feature files + step definitions
        ├── features/
        └── steps/
```

---

## Algorithm Constraints (critical — read before touching `algorithm/`)

### Match structure
- 4 quarters × 2 half-quarters = **8 slots** total
- 5 players on pitch per slot: 1 GK + 4 outfield (1 DEF, 2 MID, 1 FWD)
- Total player-slots per match: 8 × 5 = **40**

### Substitution rules (hard)
- Mid-quarter (between half-quarter 1→2 within a quarter): **max 2 player changes**
- Full quarter break (between quarter N→N+1): **max 5 player changes**
- GK **never** changes mid-quarter — only at full quarter breaks

### GK tier priority (hard)
1. `specialist` — GK only, never outfield
   - Squad = 10: plays 4 slots (2 full quarters), sits out 4 slots
   - Squad < 10: plays all 8 GK slots
2. `preferred` — first choice when specialist absent
3. `can_play` — second choice
4. `emergency_only` — last resort; system must warn the coach

### Playing time (hard, with tolerance)
- Target: equal half-quarter slots for all available players
- Max difference between most-played and least-played: **1 slot** (unless forced by GK constraints)
- Extra slots (when equal division is impossible): first to players who covered non-specialist GK slots that match

### Position rules (hard)
- `def_restricted = True` → player **never** assigned DEF
- Each player plays **≤ 2 different positions** in a single match

### Skill balance (soft)
- Outfield skill total should be as equal as possible across all 8 slots
- GK slot excluded from skill calculation
- Algorithm optimises for balance but does not reject unbalanceable solutions

---

## Data Model Summary

```
Player
  name: str
  gk_status: GKTier  (specialist | preferred | can_play | emergency_only)
  def_restricted: bool
  skill_rating: int (1–5)  ← never displayed in UI after setup
  position_history: dict   ← slots per position, per match and cumulative

Match
  date: date
  opponent: str (optional)
  quarters: int (default 4)
  quarter_length_mins: int (default 10)

RotationPlan
  match_id
  slots: list[SlotAssignment]  ← 8 items

SlotAssignment
  slot_index: int  (0–7; 0=Q1H1, 1=Q1H2, 2=Q2H1, …)
  lineup: dict[Position, Player]
```

---

## Non-Obvious Conventions

- `slot_index` runs 0–7. Quarter boundary = when `slot_index % 2 == 0` (start of a new quarter). Mid-quarter point = when `slot_index % 2 == 1` (second half of a quarter).
- Skill balance is computed over the **outfield 4** only; GK is excluded.
- "Quarter break" means the transition from slot 1→2, 3→4, 5→6 (i.e. between even-indexed slots).
- "Mid-quarter" means the transition from slot 0→1, 2→3, 4→5, 6→7.
- Position codes: `GK`, `DEF`, `MID`, `FWD`
- Formation is **1-2-1**: 1 DEF, 2 MID, 1 FWD outfield

---

## Phase Gates

| Phase | What's built | Tests required to pass |
|---|---|---|
| v0.1 | Algorithm + models | `tests/unit/algorithm/`, core BDD features |
| v0.2 | Half-quarter subs, mid-quarter lock | Sub limit + GK lock BDD scenarios |
| v0.3 | Skill balancing | Skill balance BDD scenario |
| v0.4 | Web UI + pitch view | Manual browser test |
| v0.5 | FastAPI + SQLite | `tests/integration/` |
| v0.6 | Manual override + warnings | Override BDD scenarios |
| v1.0 | Full stable product | All BDD + integration tests green |
