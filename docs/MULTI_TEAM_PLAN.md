# Multi-team mode (T1.1) — implementation plan

> Status: **planned, ready to execute.** Decisions locked with the owner 2026-07-20.
> One coach account can own **many teams (squads)**, know which one they're on at a
> glance, switch between them, add a new one, and remove one. Co-coach roles and
> "export a team to another coach" are explicitly **out of scope** (future work).

## Decisions (locked)
- **Switcher UI:** a persistent **team-name pill + dropdown** in the home-screen
  headers (`.home-title-row`), so the coach always sees which team they're on.
  Settings "Teams" section becomes a secondary path (list + manage), not the primary.
- **Sign-in landing:** drop straight into the **last-used (active) team**. No picker gate.
- **Scope:** add / switch / remove. Owner-per-squad only (no membership/roles table,
  no ownership transfer yet).

---

## Why this is low-risk (the load-bearing insight)

The session cookie carries **only `account_id`** (`backend/auth/session.py`), and
`get_current_squad` (`backend/api/deps.py:48-64`) resolves the working squad **fresh
each request** as `session.get(SquadDB, account.squad_id)`. So:

- "Which team is active" = the value of **`AccountDB.squad_id`** (a single column).
- **Switching teams = updating that one column.** No cookie re-issue, no session
  juggling, no change to `get_current_squad`, the `owned_*` IDOR guards, or any of
  the ~40 squad-scoped endpoints across `squad.py` / `matches.py` / `tournaments.py`.
- The only genuinely new concept is **squad ownership** so we can (a) list "my teams"
  and (b) refuse to switch/remove a squad that isn't mine.

We therefore **keep `AccountDB.squad_id` and repurpose it as the "active squad"
pointer**, and add **`SquadDB.account_id`** as the owner FK. That's the whole model change.

---

## Data model change (one migration)

**Add `SquadDB.account_id: int | None`** (owner; nullable so the auth-off dev default
squad and any legacy row stay valid). `AccountDB.squad_id` keeps its name but its
meaning becomes "the account's **active** squad".

### Alembic migration
- New revision in `backend/db/migrations/versions/`, `down_revision = "a8d3e6f1c2b4"` (current head).
- Follow the **inspection-guarded, idempotent** pattern from
  `f7c2d9a4b8e1_account_session_epoch.py` (must coexist with `create_all()`):
  - `upgrade()`: if `"account_id"` not in inspector columns of `squads` → `op.add_column("squads", sa.Column("account_id", sa.Integer(), nullable=True))`.
  - **Backfill** (raw SQL, portable across SQLite + Postgres):
    `UPDATE squads SET account_id = (SELECT a.id FROM accounts a WHERE a.squad_id = squads.id) WHERE account_id IS NULL;`
  - `downgrade()`: `op.drop_column("squads", "account_id")`.
- Update the model in `backend/db/models.py:6-12`:
  ```python
  class SquadDB(SQLModel, table=True):
      __tablename__ = "squads"
      id: int | None = Field(default=None, primary_key=True)
      account_id: int | None = Field(default=None, foreign_key="accounts.id", index=True)  # owner
      name: str = "My Squad"
      team_name: str = ""
      team_logo: str = ""
  ```
  (Comment on `AccountDB.squad_id` should be changed from `# 1:1 for now` to
  `# the account's ACTIVE squad (it may own several via SquadDB.account_id)`.)

### Onboarding must set the owner
In `redeem_invite` (`backend/api/routers/auth.py:96-108`), after both rows exist, set
`squad.account_id = account.id` and commit. Every squad created from now on has an owner.

---

## Backend — new endpoints

Add a small **`teams` router** (`backend/api/routers/teams.py`, prefix `/api/teams`),
mounted in `main.py` alongside the others. All endpoints depend on
`get_current_account` (auth required — the feature is a no-op in auth-off dev mode).

Add one ownership helper in `deps.py`:
```python
def owned_squad(squad_id: int, account: AccountDB, session: Session) -> SquadDB:
    squad = session.get(SquadDB, squad_id)
    if not squad or squad.account_id != account.id:
        raise HTTPException(status_code=404, detail="Team not found")
    return squad
```

Endpoints:

1. **`GET /api/teams`** → list the account's squads.
   `select(SquadDB).where(SquadDB.account_id == account.id)`; for each return
   `{ id, team_name, team_logo, is_active: (id == account.squad_id), player_count }`
   (`player_count` = cheap `count(PlayerDB where squad_id==id)`; nice for the UI).
   Order by id. **Guarantee at least one** row (the active squad) even for legacy
   accounts whose squads predate `account_id` — belt-and-braces: if the active squad
   isn't in the list, adopt it (`squad.account_id = account.id`) then include it.

2. **`POST /api/teams`** `{ team_name?, team_logo? }` → create a new squad owned by the
   account and **make it active**.
   - `squad = SquadDB(account_id=account.id, team_name=team_name or "", ...)`, commit.
   - `account.squad_id = squad.id`, commit. Return the new squad (same shape as list row).
   - (Name/logo can be blank; the coach names it in the create flow — see frontend.)

3. **`POST /api/teams/{id}/activate`** → switch active team.
   - `squad = owned_squad(id, account, session)`; `account.squad_id = squad.id`; commit.
   - Return `{ ok: true, active_squad_id: squad.id }`.

4. **`DELETE /api/teams/{id}`** → remove a team + all its football data.
   - `owned_squad(id, account, session)`.
   - **Refuse if it's the account's last team** (`count(owned squads) <= 1` → 409
     `"Can't remove your only team"`).
   - Cascade-delete this squad's data, reusing the exact deletion set from
     `clear-data` (`auth.py:358-368`) **scoped to `squad.id`**: matches (+ their
     rotation_plans/slots/slot_assignments/goal_records/match_availability/removed_players),
     tournaments, players — **then delete the `SquadDB` row itself**.
   - If the removed squad was active, set `account.squad_id` to another owned squad
     (`min(id)`), commit.
   - Return `{ ok: true, active_squad_id }`.

**`/me` + `_account_public`** (`auth.py:65,384`) already expose scalar `squad_id`
(now = active). Keep it — the frontend reads it as the current team id. No change needed
to any existing squad-scoped router.

### Refactor note (small, do it while here)
Extract the cascade-delete body of `clear-data` into a helper
`delete_squad_data(session, squad_id, *, drop_squad_row: bool)` in a service module
(or `repositories.py`), so `clear-data` and `DELETE /api/teams/{id}` share one
correct deletion path. Prevents the two drifting.

---

## Frontend

### state (`frontend/state.js`)
- Add `state.teams = []` (list from `GET /api/teams`) and `state.activeSquadId = null`.
- Populate both in `bootApp()` right after `getTeamInfo()`, and expose a
  `refreshTeams()` helper (mirrors `refreshShirtNumbers`).

### The switcher pill (primary UI)
- New markup dropped into **`.home-title-row`** on **both** season home
  (`index.html:352-361`) **and** tournament home (`index.html:601-610`) — *parity is
  mandatory* (see CLAUDE.md season⇄tournament rule). A single shared render function
  `renderTeamPill(containerId)` so the two stay identical.
- Pill: `‹team_name› ▾`. Tap → a dropdown/bottom-sheet listing every team with a ✓ on
  the active one, then **`+ Add a team`** and **`Manage teams`**.
- Only render the pill when `state.account?.auth_enabled` and `state.teams.length >= 1`.
  (Auth-off dev mode has a single implicit squad — no pill.)
- Reuse the existing collapsible/menu styling idiom; keep it theme-aware.

### Switching a team (cache reset — no full reload)
On selecting a different team:
1. `await api.activateTeam(id)`.
2. **Reset in-memory caches** (mirror the clear-data handler `settings.js:95-99`):
   `state.teamInfo = null; state.shirtNumbers = {}; state.matchData = null;
   state.activeTournamentId = null; state.cachedSquadPlayers = null;`
3. `await refreshTeams()` + `await getTeamInfo()` (repopulate `state.teamInfo`).
4. Re-render the current home list: `loadHome()` or `loadTournamentHome()` depending
   on which screen we're on. Toast `"Switched to <team_name>"`.

### Add a team
- `+ Add a team` → `api.createTeam({})` (creates + activates a blank team) → reset
  caches → drop the coach into a **name-your-team step**. Simplest reuse: route to the
  **squad-management screen** (`loadSquad()`), which already edits team name/logo and
  players in place, with a first-run hint. (Optionally set `state.squadBackContext` so
  Back returns to landing.) This avoids building a bespoke create form.
- After they save the name, the pill reflects it automatically on next render.

### Remove a team
- `Manage teams` (or a trash affordance per row in the dropdown) → confirm modal.
  Reuse the **type-to-confirm** pattern from clear-data (`index.html:326-339`,
  `settings.js:68-104`) but simpler (a single "Remove" confirm is fine — data-loss
  warning copy). Call `api.deleteTeam(id)`.
- If the API 409s ("only team"), toast the message and abort.
- On success: reset caches, `refreshTeams()`, `getTeamInfo()`, re-render home. If the
  removed team was active the server already moved us to another; just reflect it.

### Settings "Teams" section (secondary path)
- Replace the static "Coming soon" teaser (`index.html:264-273`) with a **real list**:
  each owned team with team name + a ✓/Switch control, plus `+ Add a team`. This is the
  same data as the pill; factor the list render so Settings and the pill share it.
  Keep it lean — the header pill is the primary switcher; Settings is the "manage" home
  (rename, remove live here or link to squad-management).

### api.js
Add: `getTeams()` `GET /teams`, `createTeam(data)` `POST /teams`,
`activateTeam(id)` `POST /teams/{id}/activate`, `deleteTeam(id)` `DELETE /teams/{id}`.

### Service worker
Bump `CACHE` (currently `squad-rotation-v42` → **v43**) so the HTML/JS changes ship
past the SW cache. **Purge Cloudflare after deploy** (see memory: CDN serves stale JS 4h).

---

## Tests

- **Backend integration** (`tests/integration/test_teams.py`): create 2nd team → list
  shows both with correct `is_active`; activate switches which squad `GET /matches/`
  returns; **IDOR**: account B cannot activate/delete account A's squad (404);
  delete removes only that squad's players/matches/tournaments and leaves the other
  intact; **refuse deleting the last team** (409); deleting the active team re-points
  `account.squad_id`.
- **Isolation regression**: existing `test_squad`/`test_matches` stay green (proves the
  seam is untouched).
- **e2e parity** (`tests/e2e/`, parametrized `["season","tournament"]`): pill visible,
  switch team → home list changes, add team → name it → appears, per CLAUDE.md parity rule.
- Migration: run the suite against a fresh DB **and** a copied pre-migration DB to prove
  the backfill + idempotency.

---

## Execution order (press "Go")

1. Model + Alembic migration (+ backfill) + set `account_id` in `redeem_invite`.
2. `owned_squad` helper + `teams` router (4 endpoints) + mount in `main.py` +
   extract `delete_squad_data` helper and reuse in clear-data.
3. Backend integration tests → green.
4. api.js wrappers + state (`teams`, `activeSquadId`, `refreshTeams`).
5. Header pill (shared render, both homes) + switch/reset logic.
6. Add-team + remove-team flows.
7. Settings "Teams" section rebuild.
8. SW bump v43. e2e parity + full `pytest` green.
9. Update `DEVELOPMENT_PLAN.md` (T1.1 → done) and `CLAUDE.md` "Current Phase"
   (1 account ↔ N squads). Local test on phone → **push** → **purge Cloudflare**.

## Open/deferred (not tomorrow)
- Co-coach (multiple accounts per squad) → needs the real `SquadMembershipDB` + roles.
- Export/transfer a team to another coach → ownership handoff via invite.
- Per-team "active tournament"/draft state isolation beyond the cache reset (revisit if
  a bug shows switching mid-tournament leaks state).
