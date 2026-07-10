# Gaffer — Squad Rotation Manager
**Project:** Football (Soccer) Squad Rotation Manager
**Owner:** Personal project — grassroots youth football coaches
**Tech Stack:** Python/FastAPI backend, Vanilla JS PWA frontend
**Development Approach:** TDD with pytest + BDD with pytest-bdd (Gherkin scenarios)

---

## 1. Problem Statement

A youth football coach needs to manage fair and balanced playing time across a squad during a match, whilst:
- Ensuring all children play equal (or near-equal) time
- Respecting player GK capability tiers and position restrictions
- Maintaining a competitively balanced outfield team across the match
- Giving players experience across a range of positions over time

---

## 2. Match Structure

Matches are configurable by team size. Sub limits and period structure vary:

| Size | Formation options | Structure | Mid-period subs | Break subs |
|------|-------------------|-----------|-----------------|------------|
| 5v5  | 1-2-1, 2-1-1 | 4 quarters × 2 slots = 8 slots | 2 | 5 |
| 6v6  | 1-3-1, 2-2-1, 1-2-2 | 4 quarters × 2 slots = 8 slots | 2 | 5 |
| 7v7  | 2-3-1, 1-3-2, 2-2-2 | 4 quarters × 2 slots = 8 slots | 3 | 4 |
| 9v9  | 3-3-2, 2-4-2, 3-2-3, 3-4-1, 4-3-1 | 2 halves × 2 slots = 4 slots | 4 | full squad |

- Slot = one half-period (~5 mins)
- GK never changes mid-period
- Playing time equality measured in slots assigned

### Equal Time
- Max 1 slot difference between any two available players
- When exact equality is impossible: extra slots go first to players who covered non-specialist GK

---

## 3. Positions & Formations

### 3.1 Formation-Derived Position Names

Position names are derived from formation shape, not hardcoded:

| Role | 1 player | 2 players | 3 players | 4 players |
|------|----------|-----------|-----------|-----------|
| DEF  | CB       | CB CB     | LB CB RB  | LB CB CB RB |
| MID  | CM       | LM RM     | LM CM RM  | LM CM CM RM |
| MID (5) | — | — | — | LM CM CAM RM + extra CM |
| FWD  | CF       | CF CF     | LW CF RW  | — |

### 3.2 Position Rules
- Each lineup: 1 GK + outfield players per formation
- DEF-restricted players never assigned to DEF
- Each player: max 2 different position types per match
- Algorithm respects `preferred_positions` hard constraint — never assigns outside it (when set)

---

## 4. Player Model

| Attribute | Type | Description |
|-----------|------|-------------|
| name | string | Unique within squad (duplicates rejected at API) |
| shirt_number | int \| null | Optional squad number (1–99); conflict shown in UI if duplicate |
| gk_status | enum | GK tier (see §4.1) |
| def_restricted | boolean | Must not be assigned DEF; derived from position prefs |
| skill_rating | integer (1–5) | Coach-only, never displayed in match UI |
| preferred_positions | list[str] | Positions the player CAN play: GK, DEF, MID, FWD (empty = any) |
| best_position | str \| null | Their strongest position from the above list |

### 4.1 GK Status Tiers (derived from position preferences)
| Tier | Value | Meaning |
|------|-------|---------|
| 1 | `specialist` | GK only — preferred_positions = [GK] only |
| 2 | `preferred` | GK is best_position |
| 3 | `can_play` | GK in preferred_positions among others |
| 4 | `emergency_only` | GK not in preferred_positions |

---

## 5. Fairness & Rotation

### Playing Time Fairness (0–100 slider)
- 0–15 (Equal): max 1 slot difference between any two players
- 16–100 (Competitive): skill_rating weighted distribution; everyone gets minimum ≥ floor(total/n)−1

### Position Rotation Intensity (0–100 slider)
- 0 (Specialist): players stay in best_position, max 1 position type per match
- 50 (Balanced): rotate through preferred positions
- 100 (All-rounder): experience all preferred positions

---

## 6. Team Balance (Skill)

- Skill ratings apply to outfield players only — GK slot is neutral
- Each slot's outfield skill total balanced as soft preference across the match
- Optimised via iterative pairwise swaps; not a hard constraint

---

## 7. Tinkering Mode (Manual Override)

Coach can enter Tinkering mode at any point during a match to adjust the plan:

- **Drag-and-drop** to swap two on-pitch players within a slot
- **Tap a player** to open swap picker (choose any squad player)
- **Slot locking** — edited slots are locked; re-calculation only adjusts unlocked future slots
- **Fairness warnings** — system shows which players gain/lose time (non-blocking)
- Previous and Next buttons disabled while tinkering
- Visual: paper texture + amber SVG wobble rings + "Tinkering" pill (Cabin Sketch font)
- Voice: "Tinker" to enter, "Done" to commit

---

## 8. Match Day Features

- Goal recording — long-press a player token (600ms) to record a goal
- Sub arrows (↑/↓) on player tokens at mid-period slots
- Home/away, opponent goals stored per match
- Full Time screen: enter opponent score, share result as PNG image (canvas, Web Share API)
- Share image includes team logo, team names, score, goalscorers

---

## 9. Functional Requirements

### 9.1 Squad Management
- FR-01: Coach adds a player with name, position preferences, shirt number (optional), skill rating
- FR-02: Duplicate player names rejected (API returns 422)
- FR-03: Shirt number shown on player token; duplicates flagged red
- FR-04: Skill rating not shown in match UI after setup
- FR-05: Coach can edit/delete players at any time

### 9.2 Match Setup
- FR-06: Coach creates a match (date, opponent, home/away, team size, formation, fairness, rotation intensity)
- FR-07: Coach selects available players for the match
- FR-08: System generates full rotation plan before match starts

### 9.3 Rotation Planning
- FR-09: Full plan generated (all slots) before match
- FR-10: Equal or near-equal playing time per fairness setting
- FR-11: GK tier priority respected
- FR-12: DEF-restricted players never assigned DEF
- FR-13: Each player max 2 position types per match
- FR-14: Skill balanced across slots (soft)
- FR-15: Sub limits per team size enforced (mid-period and break)
- FR-16: GK never changes mid-period
- FR-17: preferred_positions respected as hard constraint

### 9.4 Tinkering / Manual Override
- FR-18: Coach can drag-and-drop to swap two players in a slot
- FR-19: Coach can tap to open swap picker for any position
- FR-20: Edited slots are locked; re-calculation adjusts remaining unlocked slots
- FR-21: Fairness warning shown when edit causes playing time imbalance (non-blocking)

### 9.5 Match Day View
- FR-22: Current lineup shown on a visual pitch graphic (formation-aware)
- FR-23: Incoming subs visually indicated
- FR-24: Coach advances slots manually (Next button)
- FR-25: Goal recording via long-press
- FR-26: Full Time screen with score entry and share image

### 9.6 History & Development (delivered v0.7)
- FR-27: Per-player summary: positions played, slots, goals across matches
- FR-28: Mid-match player removal with re-calculation from specified slot
- FR-29: Player reinstatement and re-calculation

### 9.7 Tournament Mode (delivered v0.8)
- FR-30: Coach creates a tournament (name, date, team size, formation, match duration, half-time toggle, fairness, rotation intensity)
- FR-31: Tournament groups multiple short matches; matches added individually (group or knockout)
- FR-32: Cross-match cumulative slot tracking feeds rotation targets (`prior_slots`)
- FR-33: Guest players scoped to a tournament, excluded from the season squad list
- FR-34: Tournament-scoped position overrides per player (non-mutating)
- FR-35: Manual rotation mode — blank plan, all slots locked, coach assigns by hand
- FR-36: Tournament stats view — cumulative slots per player across the day
- FR-37 (v0.9): No player sits out two consecutive tournament matches when fairness ≤ 50; validator flags violations

### 9.8 Match Timer (planned v0.9)
- FR-38: Live match shows a timer; count-up by default, configurable countdown
- FR-39: Countdown starts from the slot length derived from match/tournament duration settings
- FR-40: Audible alert and/or vibration when the countdown reaches zero

### 9.9 Feedback (planned v0.9)
- FR-41: In-app bug report — no GitHub account required; report created server-side with app context

---

## 10. Non-Functional Requirements

- NFR-01: Mobile PWA — no app install required
- NFR-02: Offline capable via Service Worker
- NFR-03: Large, clear touch-friendly UI
- NFR-04: Data persists between sessions (SQLite, migrating to PostgreSQL for multi-user)
- NFR-05: Single-user v1 — no login required; multi-user planned for v1.0

---

## 11. Out of Scope (current)

- Auto-advance of slots (timer is now in scope — §9.8 — but never auto-advances the plan)
- Tactical formation drawing
- Player performance stats input during match
- Export (removed; revisit after the plan-review screen, v1.1)
- Local-first offline sync, ads/subscriptions (re-evaluate post-v1.0 only if usage demands)

---

## 12. Planned Future Phases

Roadmap detail lives in DEVELOPMENT_PLAN.md (2026-07-10).

| Phase | Scope | Status |
|-------|-------|--------|
| v0.7 | Start Match lock, mid-match removal/reinstatement, player history view | ✓ shipped 2026-05 |
| v0.8 | Tournament mode — cross-match slots, guest players, manual mode | ✓ shipped 2026-05 |
| v0.9 | Consecutive sit-out constraint, match timer, tinkering warning clarity, in-app bug report | next |
| refactor | app.js modularisation, shared season/tournament components, Playwright parity suite | pre-v1.0 |
| v1.0 | Multi-user — email + magic-link auth, invite-only, PostgreSQL (Neon), Railway | planned |
| v1.1 | Plan-review screen, tinkering undo/redo, export revisit | planned |
