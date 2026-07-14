# Refactor phase — next steps

_Live tracker for the pre-v1.0 refactor phase (DEVELOPMENT_PLAN.md "Phase C").
Read this first at the start of a session; it's the current source of truth for
what's done and what's next. Last updated 2026-07-14._

> **▶ Resume here (next session): Phase C is COMPLETE.** C.1–C.7 all done & on
> `main`. Next is **Phase D — v1.0 "Plan Review" UX** (first feature built on
> the new module + service structure; see DEVELOPMENT_PLAN.md Part 3 / Phase D).
>
> One small, optional loose end from C.7: the batch match add/delete loops in
> `tournament.js` (`addTournamentMatch`/`deleteMatch` inside the tournament-edit
> save) still use bare `.catch(() => {})` — left silent because a single-
> iteration retry mid-batch is unsafe. If desired, wrap the whole batch save in
> one toast. Everything else (single-action writes) now uses `withSaveToast`.
>
> _mutmut workflow reminder (for future algorithm work):_ to re-check one
> module, set `only_mutate = ["backend/algorithm/<mod>.py"]` in `[tool.mutmut]`
> (keep `source_paths` on the whole package), `rm -rf mutants`,
> `.venv/bin/python -m mutmut run`, then `mutmut results` / `mutmut show
> <mutant>`. **Always `rm -rf mutants` when switching the `only_mutate`
> target** or the stale working copy silently re-runs the previous module.
> Remove `only_mutate` again before committing.

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
- **C.5 — Service layer extraction.** `backend/services/` now owns the
  orchestration that sat in the routers. `match_service` holds the shared
  rotation mechanics — `build_match_config`/`season_config` (the tournament-vs-
  season config branch that was duplicated 4×), `generate_and_save_rotation`
  (the domain-convert → prior-slots → must-play → generate → save → set-
  available flow, previously copy-pasted across 3 endpoints), and
  `reconstruct_plan`/`adjust_and_save` (the ~30-line stored-plan rebuild the
  adjust/remove/reinstate handlers each repeated). `tournament_service` holds
  tournament setup — `derive_period_structure`, `resolve_fairness`,
  `apply_position_overrides`. Routers are now thin HTTP adapters (matches.py
  815→665, tournaments.py 683→586); repositories still own the queries. The
  pure config/setup helpers are unit-tested with no DB
  (`tests/unit/services/`, 20 tests); the DB-coupled flows stay covered by the
  integration + e2e suites. All 244 tests green (232 non-e2e + 12 e2e).

## Remaining Phase C work (suggested order)

1. **C.4 — Mutation testing (mutmut)** against the pure algorithm modules
   (`rotation_engine`, `time_balancer`, `gk_selector`, `skill_balancer`,
   `validator`). Surviving mutants mean hollow assertions — strengthen them,
   don't just add tests. **DONE — all five modules hardened; each remaining
   survivor set is a documented equivalent tail:**
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
   - **`skill_balancer` (done).** 274 mutants → **134 → 54 survivors**
     (140→220 killed). New `test_skill_balancer_direct.py` (36 tests) calls the
     constraint helpers directly on hand-built slots — the existing suite only
     drove them through `generate_rotation`, so `_swap_is_valid`,
     `_all_mid_quarter_limits_ok`, `_transition_ok_after_swap`,
     `_effective_outfield_ids`, `_try_best_swap` and `balance_skills` were
     effectively untested. Pins: specialist/DEF/duplicate swap guards; the
     mid-quarter sub-limit incl. the odd-slot partner and out-of-range-partner
     branches; change-count boundary (`<=` vs `<`); locked-slot skip;
     variance-reducing best-swap selection incl. the strict `>` (a balanced
     plan is left untouched); and skip-invalid-vs-break ordering. Remaining 54
     are equivalents: `_position_variety_ok` provably always returns True
     (outfield normalises to ≤3 categories so `len ≤ 4` is unreachable — same
     story as the validator), the coupled two-pair mid-quarter/transition
     `None`-arg mutants that net the same change-count, `//2`≡`/2` under `<=`,
     and the `balance_skills` loop-counter tweaks (monotonic convergence →
     same fixpoint).
   - **`gk_selector` (done).** 47 survivors → **27**. New
     `test_gk_selector_direct.py` (6 tests) pin the previously-loose warnings
     (exact "No GK-capable…" and "Only emergency GK players…" strings) and the
     GK time budget: `max_gk_quarters = max(1, fair_share // 2)` caps a lone
     preferred keeper at 2 quarters (kills the `players_per_slot` default and
     `//2`→`/2`), the `max(1, …)` floor holds at 1 quarter for a huge squad,
     and the per-quarter usage counter must increment so Q2/Q4 use distinct
     keepers (kills the `+1`→`-1` mutant). Remaining 27 are the
     `_pick_gk_for_quarter` all-budget-exhausted fallback + `random.shuffle`
     tiebreak `id(None)`/get-default mutants — no stable oracle, same tail as
     `rotation_engine`.
2. **C.5 — Service layer extraction. DONE** — see the "Done & on `main`"
   section above for the summary.
3. **C.7 — Backend tidy-ups.** Mostly **done**:
   - **Stats/analytics extraction (done).** `backend/services/analytics.py` now
     owns the three read-only aggregations — `season_stats`, `player_history`
     (both were in `matches.py`) and `tournament_stats` (was in
     `tournaments.py`). Routers keep only the 404 lookups. Reuses
     `normalize_position` instead of the old inline position-map dict. Covered
     by the existing stats integration tests.
   - **SW cache list (done).** `sw.js` `SHELL` now lists all six frontend
     modules (state/pitch/setup-form/season/tournament/screens) plus app.js, not
     just app.js — a stale/offline load was previously served a broken app.
     Cache bumped v5→v6 so existing clients re-cache on activate. Guarded by
     `tests/unit/test_service_worker_cache.py`, which parses app.js's imports
     and asserts `SHELL` covers every module (can't silently drift again).
   - **Frontend toast/retry (done).** New `frontend/toast.js` — `showToast`
     (single transient toast, optional Retry action) and `withSaveToast(fn)`
     which surfaces a retryable toast when a write rejects instead of the old
     data-losing `.catch(() => {})`. Wired into the silent write-path saves:
     progress/goals in `pitch.js`, team-info in `screens.js`, guest-removal and
     position-overrides in `tournament.js`; the existing clipboard toast in
     `season.js` now uses the helper too (retired the one-off `.sheets-toast`).
     Reuses the trophy-amber accent for the Retry button. Verified end-to-end by
     `test_failed_save_surfaces_retry_toast` (aborts the goals save, asserts the
     toast + Retry appear and the flow still reaches full time). `toast.js` is in
     the SW SHELL and the guard test now asserts SHELL covers *every* frontend
     module.
   - *Optional (not started):* encapsulate DB→domain mapping as `.to_domain()`
     methods (V1_Improvements Task 5) instead of free functions in
     `repositories.py`.

## After Phase C

**Phase D — v1.0 "Plan Review" UX** (first feature built on the new module
structure; see DEVELOPMENT_PLAN.md Part 3 / Phase D). Then **Phase E — v1.1
multi-user** (magic link + co-coach; `V1_MULTIUSER_PLAN.md`).

## Env reminder

The `.venv` is **uv-managed and has no `pip`**. Use `.venv/bin/python -m <tool>`
to run things (pytest, uvicorn, alembic), and `VIRTUAL_ENV=.venv uv pip install
<pkg>` to add a dependency. The system `python3` won't work (Homebrew,
externally-managed; alembic missing).
