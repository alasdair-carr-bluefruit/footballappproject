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
   `validator`). Surviving mutants mean hollow assertions — strengthen them,
   don't just add tests. **In progress:**
   - **Determinism (done).** `tests/unit/conftest.py` seeds `random` (seed 1234)
     autouse before every unit test, so the suite is a stable mutation oracle.
     This also kills the ~10% flakiness in `test_9_players_no_specialist_max_diff_1`
     and `test_7v7_mid_period_max_3_subs`.
   - **mutmut config (done).** mutmut 3.6, config in `[tool.mutmut]` (pyproject).
     Run: `.venv/bin/mutmut run` then `.venv/bin/mutmut results` /
     `mutmut show <mutant>`. Mutates `backend/algorithm`, oracle is `tests/unit`.
     To iterate on one module fast, temporarily add `only_mutate = [".../foo.py"]`.
     NB: `mutants/` is the working copy (gitignored); `mutmut results` lists only
     the non-killed mutants.
   - **Baseline (full algorithm, first run):** 1707 mutants → **826 killed,
     670 survived, 211 no-tests (uncovered)** ≈ 55% score on covered code.
   - **`validator` (done).** Root cause: the old `test_validator.py` re-checked
     constraints inline against engine output and never called `validate()`, so
     the validator itself was untested. New `test_validator_direct.py` (17 tests)
     drives `validate()` on hand-built valid/invalid plans + boundary cases:
     **60 → 20 survivors, and all 20 remaining are equivalent mutants**
     (redundant `break` guards behind `range(0, n-1, 2)`; `//3`≡`//4`≡`/3` for
     every real `total_slots∈{2,4,8}`; the unused `players` param; and the
     position-variety check, which is unreachable because only 4 normalised
     position categories exist so `len(types) > max_types(=4)` can never hold).
   - **`rotation_engine` (partial).** 842 mutants → **376 killed / 255 survived
     / 211 uncovered** (was 344/287 before). New `test_rotation_engine_behaviors.py`
     (8 tests) pins the stable coach-facing guarantees: squad-size threshold
     (`n < players_per_slot`), equal-vs-competitive fairness incl. the 0→60
     `fairness_value` derivation, and rotation-intensity→positional-spread
     (`spread(100) > spread(0)`, seed-independent). Deliberately stopped there:
     the remaining 255 are dominated by equivalent mutants (unused param
     defaults, dead `outfield_count` assignment, randomised tie-breaks like
     `min(..., key=len(position_sets[p]))`) and the multi-tier last-resort
     fallback ladders in `_select_outfield_mid_period` (78 alone) — low ROI, no
     robust assertion exists for a randomised best-effort heuristic.
     - **Skipped by design:** `adjust_rotation` (0 survivors — entirely
       uncovered/"no tests"). Its auto-recalc-of-following-slots is slated to be
       reworked to coach-triggered-only, so pinning it now would just create
       churn. See the adjust-plan-rework memory.
     - **Finding (not fixed — product code):** `preferred_positions` is
       documented in CLAUDE.md as a hard constraint ("never assigns a player
       outside their preferred_positions") but the assigner's `pool_for` fallback
       (`return p if p else unassigned`) ignores it once the preferred pool
       empties — a MID-only player lands in DEF/FWD in ~60% of seeds. Worth a
       decision: tighten the code, or soften the doc.
   - **`time_balancer` (partial).** 265 mutants → **178 killed / 87 survived**
     (was 128/137). New `test_time_balancer_crossmatch.py` (7 tests) covers the
     previously-untested cross-match (tournament) fairness — no existing test
     passed `prior_slots`: equal-mode deficit ordering (players behind on minutes
     get the extra slots), must_play outranking deficit (both the prior and
     non-prior priority branches), competitive cross-match surplus reduction,
     equal-mode dispatch ignoring `fairness_value`, competitive skill
     monotonicity, and the single-player edge. Module is pure/deterministic so
     exact-value asserts are stable. Remaining 87 are equivalents (get-defaults
     with all keys present, GK tiebreaks with no GK in scope, `>0`/`>1` guards at
     fixed n) and low-ROI: the `_enforce_must_play_floor` steal branch (31) is
     only reachable in degenerate over-subscribed squads (can't be satisfied
     anyway), and a few competitive-weight formula mutants survive via
     normalisation sign-flips that make them fragile to pin.
   - **Remaining modules (next):** `skill_balancer` (~130), `gk_selector` (~65),
     plus the rotation_engine tail if worthwhile. Same approach — call units
     directly with crafted inputs; expect equivalents.
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
