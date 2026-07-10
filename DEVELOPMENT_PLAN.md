# Gaffer — Codebase Analysis & Forward Development Plan

> Produced 2026-07-10 from a full audit of the codebase, git history, all requirements
> documents, and the latest user feedback. This document consolidates the findings and
> proposes a concrete roadmap, including the multi-user (email + magic link) release
> and a rebuild-vs-evolve decision.

---

## Part 1 — State of the Project

### 1.1 What has actually been built (vs what the docs say)

Git history shows the project is **two full phases ahead of its own documentation**:

| Phase | Docs say | Reality (git evidence) |
|---|---|---|
| v0.7 Start Match / removal / history | "← NEXT" (CLAUDE.md, PHASES.md) | **Shipped 2026-05-23/24** (`dd0452d`, `da1e369`, `e026b07`) |
| v0.8 Tournament mode | "Planned" | **Shipped 2026-05-24 onwards** — 35+ commits, `tournaments.py` router (~700 lines), 12 endpoints, 19 integration tests, cross-match fairness via `prior_slots` |
| v0.8 8-a-side | Planned | **Not built** — no 8v8 in `PRESET_CONFIGS` |
| v0.8 knockout | Planned | Partially built — knockout matches can be added from the lobby; no bracket structure |
| CSV/Sheets export | "re-add when stable" | Added in v0.6, removed again (`46e7851`) — still out |

### 1.2 Documentation inconsistencies & contradictions

1. **CLAUDE.md "Current Phase" is ~6 weeks stale** — says v0.7 is next; v0.7 and v0.8 are live.
2. **CLAUDE.md: "Goal counts keyed by player name"** — outdated. Goals are now keyed by
   `str(player_id)` (`matches.py` converts names → IDs before storing). This is good news
   for multi-user; the doc should be corrected.
3. **CLAUDE.md flaky test names don't exist** — `test_players_with_no_specialist` and
   `test_7v7_mid_period_sub_limit` are not found under those names in the test tree
   (likely renamed). The flakiness itself (randomised selection + over-budget fallback)
   is real and still present.
4. **Test count**: docs say ~105; there are ~115 `def test_` functions.
5. **requirements.md §11 declares "Countdown timer" out of scope** — users are now
   explicitly asking for a match timer. Needs moving into scope.
6. **requirements.md has no tournament FRs at all** despite tournament mode being live.
7. **Two competing futures on disk**: `V1_MULTIUSER_PLAN.md` (evolve in place, PIN-first,
   invite-only, Railway, magic-link *deferred*) vs `V2_Requirements.md` +
   `V2_UI_Requirements.md` (full rebuild: React, UUID/RLS Postgres schema, local-first
   sync engine, ads & subscription tiers). They contradict each other on auth method,
   schema, frontend technology, and business model. §3 below reconciles them.
8. **V1_Improvements.md refactor tasks: none done yet** — app.js is still one file
   (2,843 lines), the duplicate prior-slot trackers still exist
   (`matches.py:_compute_prior_tournament_slots` vs `tournaments.py:_compute_prior_slots`),
   migrations still run inside blanket `try/except: pass`.
9. **Planning artefacts are untracked in git** — `V1_MULTIUSER_PLAN.md`, `V1_Improvements.md`,
   both V2 docs, and `Issue1/` screenshots are not committed. One lost laptop loses the plan.
10. **Deploy Guide institutionalises the problem multi-user solves** — "repeat both steps
    per coach" is the ~£25/mo, N-instances model that v1.0 exists to replace.
11. **`TournamentDB.squad_id` FK deliberately not enforced** at DB level (noted in code);
    fine today, must be fixed in the multi-user schema.
12. **`docs/adr/` is empty** — decisions (e.g. Railway, magic-link-ready identity) live in
    prose docs instead; worth capturing the big ones as ADRs when v1.0 starts.

### 1.3 Code health summary

**Backend — healthy.** Clean layering (models → algorithm → repositories → routers),
the algorithm is pure Python with no I/O and ~28 unit + ~20 BDD tests, API error handling
is consistent, and all 34 endpoints have integration coverage. Known debts:

- `get_or_create_squad()` (`repositories.py:14`) is the single-tenant seam — every router
  goes through it, which is exactly what makes multi-user tractable.
- 9 accumulated `ALTER TABLE` migrations in `database.py` inside blanket try/except —
  replace with inspection-based checks (or Alembic) before v1.0.
- ~50 lines of duplicated tournament prior-slot logic across two routers.
- Intentional randomness (4 `random.shuffle` sites) → the two accepted flaky tests.
- **No consecutive-sit-out constraint exists anywhere in the algorithm** — cross-match
  fairness only balances *totals*, so a child can sit out two whole matches in a row
  (confirmed by user feedback and the Issue1 screenshots: 12 slots vs 3 slots on a
  "mostly fair" setting).

**Frontend — the problem child.**

- `app.js`: 330 → 2,843 lines in two months, 27 mutable globals, zero tests, no modules.
  Churn clusters in history (3 consecutive `available_player_ids` fixes, 4 consecutive
  tinkering-styling commits) show change here is already error-prone.
- ~200 lines of duplicated season/tournament setup-form logic (`selectSize` vs
  `tournamentSelectSize`, two formation-picker functions, duplicated player-form
  derivation). Pitch view, tinkering, goals and full-time **are** shared — good.
- 10+ silent `.catch(() => {})` handlers — e.g. a failed `/progress` call is swallowed,
  so the coach's phone thinks the slot advanced but the server doesn't.
- Service worker is network-first with no timeout and doesn't cache SVGs/fonts —
  offline is weaker than NFR-02 claims, and slow networks hang the shell.
- No input sanitisation on player/opponent names rendered into HTML.
- No match timer of any kind (`match_duration_mins` is stored but never used live).
- Bug report = GitHub issue link on the landing page only — users without GitHub
  accounts couldn't report anything (confirmed by feedback).

### 1.4 User feedback mapped to root causes

| Feedback item | Root cause in code |
|---|---|
| "Unexpected messages about other players gaining/losing slots when tinkering" | Warnings are backend diffs shown without context; removals recalc silently and the impact only surfaces on the *next* swap. No before/after view of the whole plan. |
| Child sat out two tournament matches in a row | No consecutive-bench constraint; `prior_slots` balances totals only. Issue1 screenshots show 12-vs-3 slot spread. |
| Confusion adding tournament matches (opponent name before "add match") | Lobby form ordering/affordance; no inline validation hint. |
| Wants "Review the match plan" table view + per-player slot counts + save/start | No plan-review screen exists; plan goes straight to pitch view. |
| Match timer (count-up default, countdown from slot length, alert/vibration) | Not implemented at all. |
| Season and tournament flows should share components + tests should assert parity | ~200 duplicated frontend lines; no frontend tests at all. |
| Bug reporting requires GitHub | Hard-coded GitHub issues link in `index.html`. |
| Fun rotating messages on max-competitive slider | Single static warning today. |

---

## Part 2 — Rebuild vs Evolve

**Recommendation: evolve, don't rebuild.** Specifically:

- **Backend: keep.** The layering is genuinely good, the rotation algorithm is the
  crown jewel (isolated, tested, hard to reproduce quickly), and multi-tenancy is a
  medium-sized mechanical change because isolation already flows through one function.
  A rebuild throws away ~115 passing tests and a battle-tested algorithm for zero
  user-visible gain.
- **Frontend: restructure in place, no framework rebuild.** The pain is *monolith +
  no tests*, not *vanilla JS*. Splitting app.js into modules (state, screens, pitch
  renderer, season flow, tournament flow, shared components) with a thin Playwright
  smoke suite fixes the fragility for a fraction of a React rewrite's cost — and a
  rewrite would freeze user-facing progress for weeks and re-introduce bugs the current
  UI has already burned down.
- **V2 docs: treat as a parts bin, not a plan.** Adopt now: the normalized multi-tenant
  schema *direction* (per-user scoping, real FKs), the plan-review/manual-mode concepts,
  the tinkering undo/redo command stack. Defer indefinitely: local-first sync engine
  (high complexity, low current need — coaches use one device pitch-side), React
  rebuild, ads/subscription tiers (you have a handful of invited coaches; monetization
  machinery is premature).
- **Auth: go straight to magic link — skip the PIN stage.** `V1_MULTIUSER_PLAN.md` was
  deliberately architected so magic link is additive (Account is the identity, email
  column nullable, credential verification separated from session issuance). Since
  email + magic link is now the stated near-term goal, build that verifier first and
  never ship PIN code at all. Changes vs the written plan:
  - `AccountDB.email` becomes **required and unique** (it's the login handle).
  - Drop `pin_hash`, `failed_pin_attempts`, `locked_until`; add a `LoginTokenDB`
    (hashed one-time token, 15-min expiry, single-use) — same shape as `InviteDB`.
  - Needs a transactional email provider: **Resend or Postmark** free tier
    (~100 emails/day is far beyond a handful of coaches' login frequency).
  - Keep everything else: invite-only onboarding, HttpOnly signed session cookie,
    `get_current_account`/`get_current_squad` dependencies, `owned_*()` IDOR guards,
    CORS tightening, Railway single instance + fresh Neon Postgres, old Render
    instances untouched as fallback.

---

## Part 3 — Roadmap

Ordering rationale: fix the trust-damaging fairness bug and quick wins first (current
users are actively testing), do the refactors that both the UX work and multi-user
need next, then ship multi-user before the bigger UX build-out so new coaches onboard
onto the shared instance instead of yet more Render clones.

### Phase A — Housekeeping (hours, do immediately)
1. Update CLAUDE.md / PHASES.md / requirements.md to reflect v0.7+v0.8 shipped;
   fix the goals-keyed-by-name claim; correct flaky-test names; add tournament FRs;
   move the timer into scope.
2. `git add` the planning docs (V1/V2 docs, this file, Issue1 screenshots) so the
   plan is versioned.
3. Add the tournament fairness bug + feedback items to the bug kanban.

### Phase B — v0.9 "Fairness & Trust" (small, high value)
1. **Consecutive sit-out constraint** (algorithm): when computing tournament targets,
   add a hard rule — a player benched for all of match *N* is prioritised into match
   *N+1*'s first slots; validator emits `VIOLATION:` if anyone sits out two consecutive
   matches. Add BDD scenarios for the Issue1 case (12-vs-3 spread must be impossible
   on fairness ≤ 50).
2. **Tinkering warning clarity**: show warnings as a before→after per-player table
   (reuse the plan-review component from Phase D once it exists; interim: clearer copy).
   Surface recalculation impact on *player removal*, not just on the next swap.
3. **Match timer**: count-up default, optional countdown from slot length
   (`period_length_mins` / tournament `match_duration_mins`), vibration
   (`navigator.vibrate`, guarded) + audible cue at zero, visible on pitch view in both modes.
4. **Quick wins**: rotating light-hearted max-competitive messages (10 variants);
   tournament add-match form ordering/hint fix.
5. **In-app bug reporting**: tiny `POST /api/feedback` endpoint that creates the GitHub
   issue server-side via a repo-scoped token (users never see GitHub), including
   app-state context (screen, match id). Keep the existing link as a fallback.

### Phase C — Refactor for leverage
1. Split `frontend/app.js` into ES modules: `state.js`, `screens.js`, `pitch.js`,
   `setup-form.js` (shared season+tournament config form — kills the ~200 duplicated
   lines), `season.js`, `tournament.js`. No framework.
2. Add a **Playwright smoke suite** exercising both modes through the same flows
   (create → generate → tinker → start → advance → full time). Lands first so subsequent
   changes are regression-safe.
3. Add CSS/HTML unit tests to prevent recurrence of the `display:flex` / `[hidden]`
   class of bug (e.g. Playwright assertions that key elements are not visible when they
   should be hidden, across both season and tournament flows).
4. Add **mutation testing** (`mutmut`) against the pure algorithm modules
   (`rotation_engine`, `time_balancer`, `gk_selector`, `skill_balancer`, `validator`).
   Run after the module split so coverage is cleanly scoped. Surviving mutants reveal
   hollow tests — fix by strengthening assertions, not by adding more tests. Note: seed
   `random.shuffle` in algorithm unit tests first (see known flaky tests in CLAUDE.md)
   so mutation runs are deterministic.
5. Backend tidy-ups: extract stats/history aggregation out of `matches.py` into
   `analytics.py`; replace silent frontend `.catch()`s with a toast/retry helper;
   fix SW cache list + add a network timeout fallback.

### Phase D — v1.0 "Plan Review" UX (first feature on the new structure)
1. **Review the match plan** screen after generation (season *and* tournament — same
   component): simplified table of slots (GK/DEF/MID/ATT rows, changes highlighted),
   per-player slot-count summary underneath, actions: Tinker / Save changes /
   Start match / Back. All edits already persist server-side via `/adjust`.
2. Tinkering undo/redo command stack (adopt the V2 §6 spec).
3. Revisit export (CSV/Sheets) once the review screen exposes the same data.
4. This is the proving ground for the new module structure — if the component can be
   shared cleanly between season and tournament, the refactor worked.

### Phase E — v1.1 Multi-user (magic link)
Follow `V1_MULTIUSER_PLAN.md` §5–§10 with the magic-link substitutions from Part 2:
1. Tables: `AccountDB` (email required/unique), `InviteDB`, `LoginTokenDB`.
2. Auth core: token gen/hash/verify, signed session cookie, email send via Resend/Postmark.
3. `deps.py`: `get_current_account`, `get_current_squad`, `owned_match/tournament/player`
   — audit every id-path route (IDOR list already enumerated in the plan doc).
4. Swap `get_or_create_squad()` → injected `current_squad` across all routers.
5. Frontend: `credentials:"include"`, 401 → login screen ("enter your email, we'll send
   a link"), `/join` invite redemption, account menu; move `gaffer_onboarded` server-side.
6. Harden: CORS to real origin, secrets fail-fast, rate-limit `/auth/*`.
7. Tests: authenticated-client fixture for the existing suite; isolation/IDOR tests;
   `multi_user.feature` BDD.
8. Deploy: Dockerfile, Railway + fresh Neon Postgres; invite the existing coaches;
   retire Render clones once they've migrated (manual data re-entry or a one-off
   export/import script per squad — decide per coach).

### Phase F — Later / decision points
- Multiple squads per account, co-coach sharing & roles (join-table design already in
  V1 plan §11).
- Open self-serve signup (drop invite gate) — only after magic link + rate limiting
  proven.
- 8-a-side preset; knockout bracket structure.
- Local-first/offline sync and any monetization: **re-evaluate only if** real usage
  shows offline failures or hosting costs bite. Not before.

---

## Part 4 — Risks

| Risk | Mitigation |
|---|---|
| Refactor (Phase C) breaks live testers | Playwright smoke suite lands *first* (C.2 before C.1 completes); one module extracted per commit; per user's rule, nothing pushed until locally tested |
| Magic-link email deliverability (spam folders) | Postmark/Resend with verified domain; invite flow doubles as fallback login ("send me a fresh link") |
| Existing coaches' data stranded on old instances | Instances stay live until each coach confirms migration; squads are small — worst case is 10 minutes of re-entry |
| Consecutive-sit-out fix destabilises the rotation engine | It's an additive constraint + validator check; BDD scenarios pin current good behaviour before the change |
| Flaky tests erode trust in CI | While touching time_balancer for sit-outs, seed randomness in tests (inject `random.Random(seed)`) — removes flakiness without removing variety in production |
