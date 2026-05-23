# Development Phases

## v0.1 — Core Rotation Algorithm ✓ DONE
**Goal:** Algorithm works correctly for a 10-player squad with full quarters only.

Deliverables:
- `backend/models/` — Player, Match, RotationPlan, SlotAssignment data models
- `backend/algorithm/` — rotation_engine, gk_selector, time_balancer, validator
- `tests/unit/algorithm/` — unit tests for all algorithm modules
- `tests/bdd/features/rotation_generation.feature` — core BDD scenarios pass

Acceptance: All BDD scenarios in `rotation_generation.feature` and `gk_priority.feature` pass.

---

## v0.2 — Half-Quarter Substitution Support ✓ DONE
**Goal:** Mid-quarter sub limits and GK lock enforced.

New:
- Mid-quarter substitution (max 2 players changed)
- GK never changes mid-quarter
- Squad size 6–12 handled correctly

Acceptance: `substitution_rules.feature` BDD scenarios pass.

---

## v0.3 — Skill Balancing ✓ DONE
**Goal:** Outfield skill totals balanced as soft preference.

New:
- `backend/algorithm/skill_balancer.py`
- Skill balance optimisation in rotation engine

Acceptance: `team_balance.feature` BDD scenario passes.

---

## v0.4 — Web UI + Pitch View ✓ DONE
**Goal:** Usable on a coach's phone on the pitch.

New:
- `frontend/` — Vanilla JS PWA, Pico.css
- Pitch graphic with player positions
- Manual slot advancement (single tap)
- Incoming sub indicators
- Service worker for offline use

Acceptance: Manual browser test on mobile. App usable offline.

---

## v0.5 — FastAPI + SQLite Persistence ✓ DONE
**Goal:** Data survives browser close / phone restart.

New:
- `backend/api/` — FastAPI routers for squads, matches, rotations
- `backend/db/` — SQLite via SQLModel
- `tests/integration/` — DB + HTTP endpoint tests
- Render deployment

Acceptance: Integration tests green. Data persists across sessions.

---

## v0.6 — Multi-Size, Formations, Fairness & Match Day ✓ DONE
**Goal:** Support team sizes beyond 5v5, configurable match structure, and a polished match-day experience.

New:
- **Multi-size rotation** — 5v5 through 9v9 with configurable formations (1-2-1, 2-3-1, 3-3-2, etc.)
- **Formation model** — `GameConfig`, `Formation`, `PRESET_CONFIGS` with per-size sub limits
- **Position names** — LB/CB/RB, LM/CM/RM, CAM, LW/CF/RW (derived from formation shape)
- **Fairness slider** — equal (0-15) → competitive (16-100) with skill-weighted distribution
- **Rotation intensity slider** — specialist (0) → balanced (50) → all-rounder (100)
- **Player position preferences** — `preferred_positions`, `best_position` (hard constraints)
- **Tinkering mode** — manual override with paper texture, SVG wobble rings, drag-and-drop position swaps, slot locking, partial re-calculation
- **Shirt numbers** — optional per player, displayed in tokens, conflict detection for duplicates
- **Match-day features** — goal recording (long-press), home/away, opponent goals
- **Full Time share image** — canvas-rendered PNG with team logo, score, scorers (Web Share API)
- **Season mode stats** — cumulative slots, goals per player
- **Branding** — Gaffer identity, brand guidelines (BRAND.md), icon, wordmark
- **Duplicate name rejection** — API returns 422 for same-name players
- **105 tests** — unit, BDD, integration

Acceptance: Multi-size BDD scenarios pass. Real-world match tested at 7v7.

---

## v0.7 — Match Day Polish ← NEXT
**Goal:** Lock match state, handle mid-match disruptions, and track player history.

Planned:
- **Start Match** — explicit "Start Match ▶" button; past slots auto-locked, not editable
- **Mid-match player removal** (FR-30-34) — mark player unavailable from a slot onward, re-calculate remaining slots
- **Player reinstatement** (FR-35) — restore removed player and re-calculate
- **Player history** — per-player summary view: positions played, slots, goals across matches
- **Export** — CSV/Google Sheets from season mode (re-add once stable)

Acceptance: Start Match locks past slots. Removal/reinstatement produces valid plans. History view shows cumulative stats.

---

## v0.8 — Tournament Mode
**Goal:** Manage back-to-back short matches at tournament days with cross-match minute tracking.

Planned:
- Tournament entity grouping multiple matches
- Cross-match cumulative minutes tracking
- "Start strong" competitive default for short matches
- Knockout stage support (configurable count)
- 8-a-side support

Acceptance: Tournament day with 4+ group matches produces fair cumulative minutes.

---

## v1.0 — Multi-User & Auth
**Goal:** Multiple coaches, multiple teams, shared access.

Planned:
- User accounts (email/password or OAuth)
- User → Team → Squad → Players/Matches data model
- Invite-based team sharing (edit access for all coaches)
- JWT/session auth middleware on all API endpoints
- PostgreSQL migration (SQLite → Postgres for concurrent access)
- Hosting: evaluate Render Postgres vs Supabase/Railway/Fly.io
- Data migration for existing single-squad data

Acceptance: Two coaches can independently manage their own teams. Invited coaches see shared squad/matches.
