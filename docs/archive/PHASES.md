# Development Phases

> [!WARNING]
> **ARCHIVED (2026-07-13) — do not trust for status.** This is the original
> phase-by-phase plan, kept only as a historical log; it lags behind what's
> shipped and is no longer maintained. For current status and what's next use
> `CLAUDE.md` ("Current Phase") and `docs/refactor/NEXT_STEPS.md`; for the
> forward roadmap, `DEVELOPMENT_PLAN.md`.

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

## v0.7 — Match Day Polish ✓ DONE (2026-05-23/24)
**Goal:** Lock match state, handle mid-match disruptions, and track player history.

Delivered:
- **Start Match** — explicit "Start Match ▶" button; past slots auto-locked, not editable
- **Mid-match player removal** — mark player unavailable from a slot onward, re-calculate remaining slots
- **Player reinstatement** — restore removed player and re-calculate
- **Player history** — per-player summary view: positions played, slots, goals across matches

Not delivered (still open): CSV/Google Sheets export (added in v0.6, removed again; revisit after the plan-review screen).

---

## v0.8 — Tournament Mode ✓ DONE (2026-05-24 → 2026-05-31)
**Goal:** Manage back-to-back short matches at tournament days with cross-match minute tracking.

Delivered:
- Tournament entity grouping multiple matches (`TournamentDB`, tournaments router, 12 endpoints)
- Cross-match cumulative slot tracking (`prior_slots` in time_balancer)
- Guest players scoped to a tournament (`source_tournament_id`)
- Tournament-scoped position overrides, manual rotation mode, tournament stats overlay
- Knockout matches can be added individually from the lobby

Not delivered (still open):
- 8-a-side preset
- Knockout bracket structure (configurable count)
- **Known defect:** no consecutive sit-out constraint — cumulative fairness balances totals only, so a player can be benched for two consecutive matches (user-reported; see Issue1/ screenshots). Fixed in v0.9.

---

> The roadmap from here is maintained in **DEVELOPMENT_PLAN.md** (2026-07-10), which
> consolidates user feedback, the audit findings, and the multi-user plan. Summary:

## v0.9 — Fairness & Trust ✓ DONE (2026-07-10)
- Consecutive sit-out hard constraint + validator check (BDD + integration tests)
- Match timer: count-up, localStorage-persisted per match, pause/reset, new-quarter prompt
- Fairness impact surfaced on player removal/reinstatement (warnings in response)
- In-app bug reporting (`POST /api/feedback` → GitHub issue server-side; no GitHub account needed)
- Rotating light-hearted max-competitive slider quips; tournament add-match opponent optional
- All-rounder default rotation; Fixed-only warning on select; inspection-based DB migrations (Postgres-safe)
- CSS `[hidden]` attribute override fix (display:flex/inline-flex conflicts)

**Known limitation:** countdown timer not implemented (count-up only, by design — avoids edge cases).

---

## Refactor Phase (pre-v1.0)
- Split `frontend/app.js` (~3,000 lines) into ES modules with a shared season/tournament setup form
- Playwright smoke suite asserting season/tournament parity — lands first so subsequent changes are regression-safe
- CSS/HTML unit tests (Playwright assertions on hidden/visible state) and Vitest unit tests for pure JS functions
- Mutation testing (`mutmut`) on algorithm modules; seed `random.shuffle` to fix flaky tests first
- **Service layer extraction**: `match_service.py`, `tournament_service.py` — routers become thin HTTP adapters
- **Schema normalisation**: replace `slots_json`, `goals_json`, `removed_players_json` blobs with proper tables (`SlotDB`, `SlotAssignmentDB`, `GoalRecordDB`, `MatchAvailabilityDB`); migrate via Alembic
- Replace silent frontend `.catch()`s with toast/retry; fix SW cache strategy

Acceptance: smoke suite green in both modes; no behaviour change; Alembic migration runs cleanly on existing data.

---

## v1.0 — Plan Review UX
- "Review the match plan" screen after generation (season *and* tournament — same component)
- Table view: slots × GK/DEF/MID/ATT, changes highlighted, per-player slot-count summary
- Actions: Tinker / Save changes / Start match / Back; edits already persist server-side
- Tinkering undo/redo command stack
- Revisit CSV/Sheets export once review screen exposes the data

**Why here:** first real feature on the new modular structure — validates the refactor and gives the Playwright suite a meaningful new golden path.

Acceptance: plan review works identically in season and tournament; tinkering round-trips correctly; existing tests still green.

---

## v1.1 — Multi-User & Auth (email + magic link + co-coach)
**Goal:** One always-on deployment serving many coaches, each isolated to their own squad, with co-coach support from day one.

- `AccountDB`, `InviteDB`, `LoginTokenDB` (hashed one-time tokens), **`SquadMembershipDB`** (account, squad, role: owner/coach/viewer)
- Sign up / log in via emailed magic link (Resend or Postmark); invite-only onboarding
- Co-coach invited by email → gets their own identity → role revocable without affecting other members
- Signed HttpOnly session cookie; `get_current_account` / `get_current_squad` dependencies
- `owned_*()` IDOR guards on every id-path route + isolation tests
- PostgreSQL (Neon), Railway Hobby; retire Render instances once coaches migrated

Acceptance: two coaches manage independent squads; coach A cannot read coach B's data; co-coach can be added and removed without credential rotation.

---

## v1.2 — Co-coach Plan Proposals
**Goal:** A co-coach can tinker a plan and put it in front of the head coach for sign-off before it goes live.

- `PlanProposalDB`: match_id, proposed_by (account), slot assignment snapshot, status (pending/accepted/rejected), optional note
- Co-coach uses Plan Review screen → "Propose to head coach" instead of "Start match"
- Head coach sees notification on that match; opens Plan Review with current plan vs proposed plan side-by-side, changes highlighted
- Actions: Accept (proposed slots become live) / Request changes / Reject
- Requires Phase C schema normalisation (proposals are relational diffs, not JSON blob copies) and Phase D Plan Review UI

Acceptance: proposal round-trip works; accepting a proposal updates the live plan correctly; rejection leaves current plan untouched.

---

## Later (decision points — DEVELOPMENT_PLAN.md Phase G)
- Open self-serve signup (drop invite gate) — only after magic link + rate limiting proven
- Multi-squad per account; 8-a-side preset; knockout bracket structure
- Local-first sync / monetization: only if real usage demands them
- Developer back-end view for support/onboarding troubleshooting

- 8-a-side preset; knockout brackets