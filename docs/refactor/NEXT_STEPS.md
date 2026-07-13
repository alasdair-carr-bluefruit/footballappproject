# Refactor phase — next steps

_Live tracker for the pre-v1.0 refactor phase (DEVELOPMENT_PLAN.md "Phase C").
Read this first at the start of a session; it's the current source of truth for
what's done and what's next. Last updated 2026-07-13._

## Done & on `main`

- **C.1 — app.js modularisation** (`f35492a`). 3,085 → 16-line entry point;
  six ES modules: `state.js`, `pitch.js`, `setup-form.js`, `season.js`,
  `tournament.js`, `screens.js`. All former globals live on a single shared
  `state` object (`state.x = y` — no per-variable setters). Module boundaries
  and the rationale are in [`app-js-dependency-map.md`](./app-js-dependency-map.md)
  (a pre-refactor snapshot, kept for reference). Two fixes rode along:
  - the latent pitch back-context bug (season match opened after a tournament
    match mis-routed the back/done buttons) — fixed with an explicit
    `openMatch(id, backContext)` param instead of a sticky global;
  - the duplicated season/tournament size+formation pickers, merged into shared
    `highlightActiveSize()` / `buildFormationOptions()` helpers.
- **C.2 — Playwright e2e smoke suite** (`b5cc20f`). `tests/e2e/` drives a real
  Chromium through create → generate → tinker → start → advance → full time for
  **both** season and tournament, against a real uvicorn subprocess on a
  throwaway SQLite DB. Service workers blocked so a stale cache can't mask a
  change. Run with `.venv/bin/python -m pytest -m e2e` (`playwright install
  chromium` once first). See CLAUDE.md "Key Commands".
- **C.3 — CSS/HTML visibility tests.** `tests/e2e/test_visibility.py` (9 tests).
  Directly asserts the `[hidden] { display:none !important }` invariant beats
  `.screen`'s `display:flex` (computed-style check), then walks the pitch state
  machine across **both** flows: plan-review vs live controls (Start CTA, live
  badge, End-Match bar, timer), the edit-mode badge toggle (`.visible` class,
  not `hidden`) with nav locked, and default-hidden overlays. Uses Playwright's
  rendered-visibility asserts, so a class toggle that never fires or a lost
  `!important` fails the test.
- **C.6 — Schema normalisation** (`c9340a5`, `5d67a08`). Relational rotation
  storage (SlotDB / SlotAssignmentDB / GoalRecordDB / MatchAvailabilityDB /
  removed_players) via Alembic; done & deployed to the live Neon DB. The
  original `*_json` columns remain dormant as a rollback net. Migration
  playbook preserved in
  [`postgres-neon-migration-testing.md`](./postgres-neon-migration-testing.md)
  and the read-only checker in [`verify_backfill.py`](./verify_backfill.py).

## Remaining Phase C work (suggested order)

1. **C.4 — Mutation testing (mutmut)** against the pure algorithm modules
   (`rotation_engine`, `time_balancer`, `gk_selector`, `skill_balancer`,
   `validator`). **First** seed `random.shuffle` in the algorithm unit tests so
   runs are deterministic (see "Known flaky tests" in CLAUDE.md). Surviving
   mutants mean hollow assertions — strengthen them, don't just add tests.
2. **C.5 — Service layer extraction.** Pull orchestration out of
   `backend/api/routers/matches.py` and `tournaments.py` into
   `backend/services/match_service.py` / `tournament_service.py`; routers become
   thin HTTP adapters, repositories keep the queries. Makes endpoint logic
   unit-testable without a full DB.
3. **C.7 — Backend tidy-ups.** Extract stats/history aggregation into
   `analytics.py` (V1_Improvements Task 1); replace silent frontend `.catch()`s
   with a toast/retry helper; fix the SW cache file list (now that frontend is
   multiple modules, `sw.js` must cache all of them — check it lists
   state/pitch/setup-form/season/tournament/screens, not just app.js).
   *Optional:* encapsulate DB→domain mapping as `.to_domain()` methods
   (V1_Improvements Task 5) instead of free functions in `repositories.py`.

## After Phase C

**Phase D — v1.0 "Plan Review" UX** (first feature built on the new module
structure; see DEVELOPMENT_PLAN.md Part 3 / Phase D). Then **Phase E — v1.1
multi-user** (magic link + co-coach; `V1_MULTIUSER_PLAN.md`).

## Env reminder

The `.venv` is **uv-managed and has no `pip`**. Use `.venv/bin/python -m <tool>`
to run things (pytest, uvicorn, alembic), and `VIRTUAL_ENV=.venv uv pip install
<pkg>` to add a dependency. The system `python3` won't work (Homebrew,
externally-managed; alembic missing).
