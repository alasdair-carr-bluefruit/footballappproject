# Testing the relational-storage migration on Postgres / Neon safely

This covers the `57b6bfa73768_relational_rotation_storage` migration (JSON blobs →
`slots` / `slot_assignments` / `goal_records` / `match_availability` /
`removed_players`). It has been verified on SQLite and on a copy of the real
`football.db` (row counts + full read round-trip, 0 mismatches). Postgres is a
different engine, so **rehearse on an isolated Neon branch before touching any
real user database.**

## Golden rule

**Never run this against a live coach's database first.** Rehearse on a Neon
branch (an instant, isolated copy), verify, delete the branch. Only deploy to a
real instance after the branch rehearsal passes.

## Why this needs care

On deploy the app **auto-migrates at startup**: `create_db_and_tables()` runs
`create_all` → the legacy additive-column bridge → `alembic stamp baseline` (if the
DB predates Alembic) → `alembic upgrade head`. So **pushing this code to a real
instance automatically runs the migration on that instance's Neon DB.** That is the
step we de-risk by rehearsing on a branch.

## What makes this relatively safe

1. **Transactional DDL on Postgres.** Alembic wraps the migration in a transaction
   on Postgres, so if the backfill fails partway it rolls back cleanly (unlike
   SQLite, which we only use locally).
2. **Idempotent.** The backfill skips if `slots` already has rows, so re-running or
   re-deploying is safe.
3. **Additive only.** The migration *creates* new tables and *copies* data. It never
   drops or edits the existing `*_json` columns — the original data stays intact.
4. **Neon branches** are copy-on-write, instant, and isolated — the ideal sandbox.

## Prerequisite: Postgres driver locally

The default local setup is SQLite. To talk to Neon you need psycopg2:

```bash
uv pip install -e ".[api]"     # installs psycopg2-binary (+ alembic)
```

Neon connection strings look like:
`postgresql://user:pass@ep-xxxx-pooler.<region>.aws.neon.tech/dbname?sslmode=require`

> If you hit connection issues with the `-pooler` host during migrations, use the
> **direct** (non-pooler) endpoint for the alembic run — pgbouncer pooling can
> interfere with multi-statement migrations.

## Approach A — Neon branch rehearsal (recommended)

1. **Create a branch** of the target project in the Neon console (Branches → New
   branch, from the branch that holds the real data). Call it e.g.
   `migrate-rehearsal`. It's an instant isolated copy with identical data.
2. **Grab the branch connection string** (Dashboard → Connection Details → the
   branch).
3. **Run the migration against the branch** (no app, just alembic):
   ```bash
   DATABASE_URL="postgresql://...MIGRATE-REHEARSAL-BRANCH..." \
     .venv/bin/python -m alembic upgrade head
   ```
   Expect: `Running upgrade 4cf63d43cd4c -> 57b6bfa73768, relational rotation storage`.
   (If the branch predates Alembic it has no `alembic_version`; stamp baseline first:
   `... -m alembic stamp 4cf63d43cd4c` then `upgrade head`. The app's startup does
   this automatically, but the bare `alembic` CLI does not.)
4. **Verify the backfill** (counts + read round-trip) against the branch:
   ```bash
   DATABASE_URL="postgresql://...MIGRATE-REHEARSAL-BRANCH..." \
     .venv/bin/python docs/refactor/verify_backfill.py
   ```
   (Script below — it compares every plan's relational rows against its JSON blobs
   and prints `ROUND-TRIP CLEAN` or the mismatches.)
5. **Smoke-test the app** against the branch:
   ```bash
   DATABASE_URL="postgresql://...MIGRATE-REHEARSAL-BRANCH..." \
     .venv/bin/uvicorn main:app --port 8001
   ```
   Open it, load an existing match → the plan/pitch should render, season & player
   stats should show, tournament stats should show. Try generating/adjusting a plan.
6. **Delete the branch** in Neon. Production is untouched throughout.

## Approach B — dump / restore (alternative)

```bash
pg_dump "postgresql://...PROD..." > prod.sql          # read-only on prod
# create a fresh empty Neon project, then:
psql "postgresql://...SCRATCH..." < prod.sql
DATABASE_URL="postgresql://...SCRATCH..." .venv/bin/python -m alembic upgrade head
# verify + smoke-test, then discard the scratch project
```

Branching (A) is easier and faster; use B only if you'd rather not branch.

## Rolling out to a real instance (after rehearsal passes)

1. **Snapshot first:** create a Neon branch of the real DB right before deploy — it's
   an instant restore point.
2. **Deploy the code.** Startup auto-runs the migration on that instance.
3. **Verify** the app works (load a match, check stats).
4. **If something's wrong:** roll back the code deploy **and** restore the DB from the
   pre-deploy branch. See the caveat below — don't rely on a delayed rollback.

## ⚠️ Caveat: the "dormant JSON" columns are a snapshot, not a live mirror

After this cutover the app writes new/changed rotation data to the **relational
tables only**. The `*_json` columns are frozen at migration time and are **not**
updated going forward. So:

- They are a reliable rollback source **only in the window right after deploy**,
  before the coach edits anything.
- Once a coach regenerates a plan / records goals / removes a player, the JSON is
  stale.
- **Practical rollback = revert the code deploy + restore the DB from the pre-deploy
  Neon branch.** Do not count on the JSON columns for a rollback hours/days later.

A later cleanup migration will drop these columns once we're confident.

## What NOT to do

- ❌ Don't `alembic upgrade head --sql` (offline) expecting a full preview. The
  backfill is a **Python data migration** that needs a live connection; offline mode
  only renders DDL and will skip/err on the data copy. Rehearse online on a branch.
- ❌ Don't point `DATABASE_URL` at prod "just to look" — both the app and alembic
  write on connect/startup.

## Postgres specifics already handled in the code

- `env.py` enables batch mode only for SQLite; Postgres uses native `ALTER`.
- Table creation is guarded (`if name not in existing`), so `create_all` (startup)
  and the migration's `create_table` never collide regardless of order.
- `inserted_primary_key` / `session.flush()` use `RETURNING` on Postgres.
- Column types map cleanly from the SQLModel definitions (int / varchar / bool).
