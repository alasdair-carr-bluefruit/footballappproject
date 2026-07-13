# Relational storage migration — ✅ DONE & DEPLOYED (2026-07-13)

> **This work is complete.** Committed as `c9340a5`, pushed to `main`, and live on
> the `titansgaffer` Render instance. Startup migration ran on the live Neon DB,
> backfilled cleanly, and production serves rotation plans off the relational tables
> (verified: 10 players, 2 tournaments, match 29 → 2 slots / 7-player lineup, no errors).
> The original `*_json` columns remain intact as a same-day rollback net.
>
> **Remaining follow-ups (not blocking):**
> - Delete any leftover Neon rehearsal branch (had live creds).
> - Later cleanup migration to drop the dormant `*_json` columns once fully confident.
>
> **Next actual work** (fresh thread): continue the refactor phase — app.js
> modularisation (see `app-js-dependency-map.md`), Playwright smoke suite, CSS/HTML
> unit tests — then v1.0 Plan Review UX. See `DEVELOPMENT_PLAN.md`.
>
> _Everything below is the historical playbook for the migration, kept for reference._

---

_Last updated 2026-07-13 (post-restart prep pass). Local rehearsal is done; the only
remaining gate is the Neon branch run, which needs a connection string from you._

## Where we are

The JSON-blobs → relational-tables refactor is **code-complete and verified locally**.
Nothing is committed yet — it's all in the working tree.

- **159 tests pass** (~2.3s; 2 algo tests are ~10% flaky, unrelated).
- **Lint:** the refactor adds **0 new** ruff errors — it's net **−15** vs HEAD. There
  are ~71 *pre-existing* repo-wide style issues (E402 from pytest-bdd `scenarios()`
  ordering, long lines, unused test imports) across files this work never touched.
  ("ruff clean" in the earlier version of this note only held for the diff, not the
  whole repo.) Not a blocker for this refactor; separate cleanup if desired.

## ✅ Local prep done (2026-07-13)

Everything rehearseable without a live Neon URL has been run and is green:

- `psycopg2-binary` installed via `pip install -e ".[api]"`.
- Alembic graph confirmed: `base → 4cf63d43cd4c (baseline) → 57b6bfa73768 (head)`.
- `verify_backfill.py` on local `football.db`: **ROUND-TRIP CLEAN** (31 plans).
- **Full deploy path rehearsed** on a throwaway copy of the real `football.db` with
  the relational tables + `alembic_version` stripped off (simulating a pre-Alembic
  coach DB): `create_db_and_tables()` correctly stamped baseline → upgraded → backfilled,
  **ROUND-TRIP CLEAN**, and a second startup was **idempotent** (backfill skipped, still clean).
- App boots against that DB and serves relational-backed reads (match 25 → 8 slots,
  5-player lineups) with no errors.

### ⚠️ Gotcha found: stale venv shebang
This venv was created under the old path (`/Users/ali/Projects/Football App Project`),
so `.venv/bin/uvicorn` and `.venv/bin/alembic` have a broken shebang and fail silently.
**Use the module form instead** everywhere below:
`.venv/bin/python -m uvicorn …` / `.venv/bin/python -m alembic …`. (`.venv/bin/python -m pytest`
works fine.) A clean fix is to recreate the venv, but the module form is enough to proceed.

Four stages, all done:

1. **Repository layer** — all rotation-plan JSON access goes through `backend/db/repositories.py`; routers no longer parse JSON.
2. **Alembic adopted** — `alembic.ini` + `backend/db/migrations/`, baseline matches current schema.
3. **Relational tables + backfill** — `slots`, `slot_assignments`, `goal_records`, `match_availability`, `removed_players`; startup auto-migrates + backfills idempotently. Verified against the real 31-plan `football.db`.
4. **Cutover** — repository reads/writes the tables; routers unchanged; JSON columns left **dormant** (not dropped).

## ⚠️ Before you do anything else

- **Do NOT deploy this code to a real coach instance yet.** On startup the app
  auto-runs the migration against whatever `DATABASE_URL` points to — including a
  live Neon DB. Rehearse on a Neon branch first (see below).
- Running the test suite already migrated your local `football.db` (expected,
  idempotent). That's fine.

## What to do next (in order)

### 1. Re-verify locally after restart — ✅ done (159 passed)
```bash
cd ~/projects/football-app-project
.venv/bin/python -m pytest -q          # expect 159 passed (2 algo tests are ~10% flaky)
```

### 2. Rehearse on Postgres/Neon — ✅ DONE & CLEAN (2026-07-13)
Ran against a real Neon branch (Postgres 17.10, a pre-Alembic copy with 15 tournament
plans) via the faithful deploy path `create_db_and_tables()`:
- migration ran with `PostgresqlImpl` / **transactional DDL** (Postgres path exercised);
- `verify_backfill.py` → **ROUND-TRIP CLEAN** (15 plans); **idempotent** on 2nd startup;
- app booted against the branch and served relational-backed reads — tournament match 29
  → 2 slots / 7-player lineups / warnings intact; tournament 9 → 10 matches + stats; no errors.
- Note: `/api/matches/` was empty because every match on this branch belongs to a
  tournament (that endpoint lists standalone matches only) — expected, not a migration issue.

**→ Remember to DELETE the rehearsal branch in Neon; prod was untouched.**

Original playbook (for future rehearsals): **[`postgres-neon-migration-testing.md`](./postgres-neon-migration-testing.md)**

Create a Neon BRANCH of a real DB in the console, copy its connection string, then
(note: `-m alembic` / `-m uvicorn`, not the bin wrappers — see gotcha above):
```bash
export DATABASE_URL="postgresql://…BRANCH…?sslmode=require"   # use the DIRECT (non-pooler) host for alembic
.venv/bin/python -m alembic stamp 4cf63d43cd4c   # only if the branch predates Alembic (no alembic_version)
.venv/bin/python -m alembic upgrade head
.venv/bin/python docs/refactor/verify_backfill.py             # expect ROUND-TRIP CLEAN
.venv/bin/python -m uvicorn main:app --port 8001              # smoke-test the app
# delete the branch afterwards — prod untouched
```

### 3. Commit
Once you're happy locally. Suggested: one commit per stage, or one squashed commit.
Push straight to `main` (no PR) per the usual workflow.

### 4. Roll out to real instances
Only after the branch rehearsal passes. Snapshot each real DB (a Neon branch = instant
restore point) right before deploying. Rollback = revert code **and** restore the DB
snapshot — the dormant JSON columns are only a same-day safety net (see the caveat in
the testing doc).

### 5. Later cleanup (separate change, not now)
Once confident in production, drop the dormant `*_json` columns from `rotation_plans`
(`slots_json`, `goals_json`, `available_player_ids_json`, `removed_players_json`) via a
new Alembic migration. `warnings_json` stays.

## Reference docs
- **[`postgres-neon-migration-testing.md`](./postgres-neon-migration-testing.md)** — full safe-testing playbook + Postgres specifics + rollback caveats.
- **[`verify_backfill.py`](./verify_backfill.py)** — read-only checker; compares table data vs original JSON for any `DATABASE_URL`.
- `DEVELOPMENT_PLAN.md` (repo root) — Phase C item 6 is this work.

## Files changed (uncommitted working tree)
```
Modified:
  backend/api/routers/matches.py      routers call the repository, no inline JSON
  backend/api/routers/tournaments.py  "
  backend/db/repositories.py          owns all plan persistence; reads/writes tables
  backend/db/models.py                + 5 relational models
  backend/db/database.py              startup: create_all + legacy bridge + alembic upgrade
  pyproject.toml                      + alembic dep; migrations excluded from lint
New:
  alembic.ini
  backend/db/migrations/              env.py + baseline + relational-storage revision
  docs/refactor/postgres-neon-migration-testing.md
  docs/refactor/verify_backfill.py
  docs/refactor/NEXT_STEPS.md         (this file)
```
_(The `frontend/*.js` and other pre-existing untracked files are unrelated to this work.)_
