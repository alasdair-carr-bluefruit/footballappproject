# Development Phases

## v0.1 — Core Rotation Algorithm ← CURRENT
**Goal:** Algorithm works correctly for a 10-player squad with full quarters only.

Deliverables:
- `backend/models/` — Player, Match, RotationPlan, SlotAssignment data models
- `backend/algorithm/` — rotation_engine, gk_selector, time_balancer, validator
- `tests/unit/algorithm/` — unit tests for all algorithm modules
- `tests/bdd/features/rotation_generation.feature` — core BDD scenarios pass

Acceptance: All BDD scenarios in `rotation_generation.feature` and `gk_priority.feature` pass.

---

## v0.2 — Half-Quarter Substitution Support
**Goal:** Mid-quarter sub limits and GK lock enforced.

New:
- Mid-quarter substitution (max 2 players changed)
- GK never changes mid-quarter
- Squad size 6–12 handled correctly

Acceptance: `substitution_rules.feature` BDD scenarios pass.

---

## v0.3 — Skill Balancing
**Goal:** Outfield skill totals balanced as soft preference.

New:
- `backend/algorithm/skill_balancer.py`
- Skill balance optimisation in rotation engine

Acceptance: `team_balance.feature` BDD scenario passes.

---

## v0.4 — Web UI + Pitch View
**Goal:** Usable on a coach's phone on the pitch.

New:
- `frontend/` — Vanilla JS PWA, Pico.css
- Pitch graphic with player positions
- Manual slot advancement (single tap)
- Incoming sub indicators
- Service worker for offline use

Acceptance: Manual browser test on mobile. App usable offline.

---

## v0.5 — FastAPI + SQLite Persistence
**Goal:** Data survives browser close / phone restart.

New:
- `backend/api/` — FastAPI routers for squads, matches, rotations
- `backend/db/` — SQLite via SQLModel
- `tests/integration/` — DB + HTTP endpoint tests

Acceptance: Integration tests green. Data persists across sessions.

---

## v0.6 — Player History & Manual Override
**Goal:** Coach can track development and override plans.

New:
- Position history tracking per player per match + cumulative
- Minutes played counter
- Per-player summary view
- Manual override with rule-violation warnings
- `tests/bdd/features/squad_management.feature`

Acceptance: History BDD scenarios pass. Override warnings shown correctly.

---

## v1.0 — Stable for Real Match Use
**Goal:** Reliable enough to use every match week.

New:
- Bug fixes from real-world use
- UI polish
- All BDD + integration tests green
- No known data-loss scenarios

Acceptance: Full test suite green. Used successfully in at least one real match.
