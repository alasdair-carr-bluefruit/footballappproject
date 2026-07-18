# Level — Codebase Analysis & Forward Development Plan

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
   invite-only, Railway, magic-link *deferred*) vs `docs/future/V2_Requirements.md` +
   `docs/future/V2_UI_Requirements.md` (full rebuild: React, UUID/RLS Postgres schema, local-first
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

> **Reprioritised 2026-07-18.** Multi-user (Phase E) is **shipped and live** on
> `feat/multi-user` (magic-link auth, invite-only, per-account squad isolation). The
> original phases were ordered by *dependency*; now that the foundations are in, the
> **Forward Roadmap** below is ordered by *value × effort × demand* into Tiers 1–4.
> Phases A–E are kept as the completed record. `CLAUDE.md`'s "Current Phase" should be
> refreshed to match (multi-user live; next up = Tier 1).

Original ordering rationale (historical): fix the trust-damaging fairness bug and quick
wins first (current users were actively testing), do the refactors that both the UX work
and multi-user need next, then ship multi-user before the bigger UX build-out so new
coaches onboard onto the shared instance instead of yet more Render clones.

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
> **Status (2026-07-14): Phase C COMPLETE — C.1–C.7 all done & committed.** All
> five algorithm modules mutation-hardened; service layer extracted; backend
> tidy-ups landed. A post-refactor bug-squash also shipped (finished-match goals,
> live-browse model, pause button, connection-lost banner). **Now in Phase D:
> D.1 "Review the plan" screen is DONE** (`37a2cec`). Committed locally, not yet
> pushed (see NEXT_STEPS.md "Env"/push policy). Live tracker:
> `docs/refactor/NEXT_STEPS.md`.

1. ✅ **DONE** (`f35492a`) Split `frontend/app.js` into ES modules: `state.js`, `screens.js`,
   `pitch.js`, `setup-form.js` (shared season+tournament config form — killed the
   duplicated picker lines), `season.js`, `tournament.js`. No framework. Globals
   consolidated into a shared `state` object. Also fixed the pitch back-context bug
   and dedup'd the size/formation pickers.
2. ✅ **DONE** (`b5cc20f`) Added a **Playwright smoke suite** (`tests/e2e/`) exercising both
   modes through the same flow (create → generate → tinker → start → advance → full time).
   (Landed after C.1, not before, since the split was already complete working-tree WIP.)
3. ✅ **DONE** (`920f4dd`) CSS/HTML visibility tests (`tests/e2e/test_visibility.py`)
   guarding the `display:flex` / `[hidden]` invariant and the pitch state machine
   across both flows.
4. ✅ **DONE** (`345872c`, `0ac6662`, `bd9530a`, `030a75c`) **Mutation testing**
   (`mutmut`) against the pure algorithm modules. RNG seeded for determinism
   (`tests/unit/conftest.py`); all five modules hardened, each to a documented
   equivalent-mutant tail (validator 60→20, rotation_engine 287→255,
   time_balancer 137→87, skill_balancer 134→54, gk_selector 47→27). Surviving
   mutants reveal hollow tests — fixed by strengthening assertions, not adding
   tests. Full detail in NEXT_STEPS.md.
5. ✅ **DONE** (`7e02eb4`) **Service layer extraction**: business logic pulled out
   of `matches.py`/`tournaments.py` into `backend/services/match_service.py` and
   `tournament_service.py`. Routers are thin HTTP adapters; services own
   orchestration; repositories own queries. Pure helpers unit-tested with no DB
   (`tests/unit/services/`).
6. ✅ **DONE** (`c9340a5`, `5d67a08`) **Schema normalisation** (done before multi-user to avoid concurrent-write races):
   replaced JSON blob columns (`slots_json`, `goals_json`, `removed_players_json`,
   `available_player_ids_json`) with proper relational tables — `SlotDB`,
   `SlotAssignmentDB`, `GoalRecordDB`, `MatchAvailabilityDB`. Use Alembic for this
   migration (decide on Alembic here — it's the right tool once the schema evolves
   beyond simple additive columns). Deleting a player then correctly cascades;
   stats queries become SQL not in-memory JSON parsing.
7. ✅ **DONE** (`db7109d`, `6d50c5b`) Backend tidy-ups: stats/history aggregation
   extracted into `services/analytics.py`; silent frontend `.catch()`s replaced
   with a `toast.js` toast/retry helper; `sw.js` SHELL cache-list fixed (now
   caches all frontend modules, guarded by a unit test).

### Phase D — v1.0 "Plan Review" UX (first feature on the new structure)
1. ✅ **DONE** (`37a2cec`) **Review the match plan** screen after generation
   (season *and* tournament — same `#screen-review`). Player-row grid (one row per
   player, position chip per slot, per-player slot total + skill-total row, changed
   cells highlighted), an under-slotted-player warning vs fair share (folds in bug
   #3), actions: Tinker / Start match / Back. Grid is read-only — "Tinker" opens the
   pitch editor (edits persist via `/adjust`) and a "◀ Plan" pill returns.
   Tournament also gets a combined "Review all plans" page (one card per match,
   rotations generated in order for cross-match fairness). ("Save changes" was
   dropped — edits already auto-persist.)
2. Tinkering undo/redo command stack (adopt the V2 §6 spec). → **moved to Forward
   Roadmap T3.3** (not yet done).
3. Revisit export (CSV/Sheets) once the review screen exposes the same data. → **moved
   to Forward Roadmap T3.3** (not yet done).
4. This is the proving ground for the new module structure — if the component can be
   shared cleanly between season and tournament, the refactor worked.

### Phase E — v1.1 Multi-user (magic link) — ✅ SHIPPED & LIVE
> **Shipped on `feat/multi-user`.** Magic-link auth (no PIN ever), invite-only
> onboarding, `AccountDB`/`InviteDB`/`LoginTokenDB`, `deps.py` isolation seam
> (`get_current_account`/`get_current_squad` + `owned_*` IDOR guards), early-access
> capture + Resend email, Railway + Neon deploy. **Scope note:** the shipped model is
> **1 account ↔ 1 squad** (`AccountDB.squad_id`); the planned `SquadMembershipDB` join
> table + roles were deliberately deferred — so **both multi-team (Tier 1) and co-coach
> (Tier 3) now depend on introducing that membership/ownership layer.** The link was
> intentionally placed on `AccountDB` so this is additive.

Original plan (for reference), per `V1_MULTIUSER_PLAN.md` §5–§10:
1. Tables: `AccountDB` (email required/unique), `InviteDB`, `LoginTokenDB`,
   **`SquadMembershipDB`** (account_id FK, squad_id FK, role: `owner | coach | viewer`).
   Co-coach is a membership row — no shared credentials, individual identity per coach,
   role-based access revocable per member without affecting others. *(membership table
   not yet built — see scope note above)*
2. Auth core: token gen/hash/verify, signed session cookie, email send via Resend/Postmark.
3. `deps.py`: `get_current_account`, `get_current_squad`, `owned_match/tournament/player`
   — audit every id-path route (IDOR list already enumerated in the plan doc).
4. Swap `get_or_create_squad()` → injected `current_squad` across all routers.
5. Frontend: `credentials:"include"`, 401 → login screen, `/join` invite redemption,
   account menu, co-coach invite UI; move `gaffer_onboarded` server-side.
6. Harden: CORS to real origin, secrets fail-fast, rate-limit `/auth/*`.
7. Tests: authenticated-client fixture; isolation/IDOR tests; `multi_user.feature` BDD.
8. Deploy: Dockerfile, Railway + fresh Neon Postgres; invite existing coaches; retire
   Render clones once migrated.

## Forward Roadmap — prioritised (2026-07-18)

Ordered by **value × effort × demand** (replaces the old dependency-ordered Phases F–J).
⚡ = quick win. Cross-cutting rules still apply to every match-day item: **season ⇄
tournament parity** (mirror both flows in the same change) and **additive migrations**
for any schema change.

### 🔴 Tier 1 — Now

**T1.1 Multi-team (one coach, several squads).** *Real user demand — a live coach has
already asked.* Today it's 1 account ↔ 1 squad (`AccountDB.squad_id`). Because the
isolation seam is a single function (`get_current_squad` in `deps.py`), this is additive,
not a rewrite:
- **Data:** introduce ownership/membership — either add `owner_account_id` to `SquadDB`
  (simplest), or a `SquadMembershipDB(account_id, squad_id, role)` join (**preferred** —
  it also unblocks co-coach, T3.2). Migrate each existing account → one owned squad.
- **Active squad:** add the currently-selected squad (e.g. `AccountDB.active_squad_id`,
  or carry it in the session) so requests resolve to the right team.
- **`get_current_squad`:** return the active squad *after* asserting the account owns/
  is a member of it — keeps the IDOR guarantee intact.
- **Frontend:** team switcher + "Create new team" in the account menu; current team name
  visible; squad-scoped screens refetch on switch.
- **Tests:** extend isolation tests — account A can never reach account B's second squad.

**T1.2 ⚡ Signed-out → marketing site.** On `app.keepthingslevel.com`, give an
unauthenticated visitor an obvious link back to `keepthingslevel.com` (header/landing
link on the login screen). Tiny; plugs a funnel leak. *(was H6)*

**T1.3 Settings screen + account self-service.** New screen from the account menu:
- **Update email address** — needs a re-verify step (magic link to the new address) so a
  change can't silently hijack the login handle.
- **Invite a friend** — reuse the existing invite-token flow to generate a shareable
  one-time link. *(growth loop)*
*(was H1–H3)*

**T1.4 ⚡ Clear squad & data (destructive).** In settings: delete the coach's squad(s),
players, matches and tournaments. Requires **at least one extra explicit confirmation**
("Are you sure? This data cannot be recovered") beyond the initial tap — ideally
type-to-confirm — and unreachable by accident. Also backs the delete-on-request promise
in the Privacy/Safeguarding pages. *(was H5)*

### 🟠 Tier 2 — Next (retention + product-led growth)

**T2.1 Shareable match-day moments.** The share-image is the viral surface — every
WhatsApp post is a soft ad. Ship together:
- **Man of the Match on the export** — add `motm_player_id` (nullable) to `MatchDB`; at
  full-time pick from players who actually played (`available_player_ids`); render on the
  share image / export. *(was G4)*
- **Record assists** — on goal record, "Who assisted?" popup (on-pitch players + **N/A**);
  store per-player by id (assists column on `GoalRecordDB` or a sibling table); surface in
  stats + export; assist must be an on-pitch player and not the scorer. *(was G2)*
- **Goal celebration** — confetti/fireworks on goal (`pitch.js`); respect
  `prefers-reduced-motion`; must not block goal/assist recording. *(was G3)*

**T2.2 FA 2026/27 cornerstone blog + SEO content + reach.** Marketing-site blog
(`marketing/blog/`, plain HTML, no build step), answer-first with `FAQPage`/`Article`
JSON-LD; add each post to `sitemap.xml`. Cornerstone + cluster:
- "What the FA's 2026/27 youth football changes mean for your team" (timely anchor —
  30–40 min recommended game time, 3v3 U7 no-subs).
- "Why equal playing time matters (and what the FA actually recommends)" (links to FA guides).
- "A fair rotation without the spreadsheet" (problem→product).
- "How much game time should kids get, by age group?" (FAQ-schema bait).
- "Sharing keeper time so one kid isn't stuck in goal" (maps to `share_gk`).

Off-site reach (highest leverage — backlinks + trusted audiences): outreach to aligned
creators (Kev Weir / *Just Play Sports*, Saul Isaksson-Hurst / *My Personal Football
Coach*, The Coaching Manual, 360TFT) with free access + a genuine feedback ask —
**cite/link freely; never imply endorsement without explicit consent**; County-FA
resource listings; genuine community participation (Facebook groups,
r/grassrootsfootball); founder safeguarding credibility (parent/coach/ref/former DSL) in
content and press/podcast outreach. *(SEO technical foundations already ✅ shipped — see
bottom.)*

**T2.3 Colourway switcher + colourblind mode.** A theme = an alternate CSS
custom-property set (`:root` in `style.css`, mirroring `assets/brand/tokens.json`). The
colourblind variant must keep GK/incoming/danger/goal states distinguishable without
relying on hue alone (design against BRAND.md; verify contrast). Accessibility + fits the
inclusive brand. *(was H4)*

### 🟡 Tier 3 — Bigger bets, later

**T3.1 Match-day engine features.**
- **Adjust formation mid-match** — `MatchDB.formation` is fixed at creation; allow a live
  change keeping played/locked slots, re-deriving remaining unlocked slots against the new
  formation (reuse the tinkering locked-slot model + `config.formation.outfield_positions()`);
  guard the team-size invariant. *(was G1)*
- **Add an extra player mid-match (power play)** — the engine assumes a fixed `team_size`;
  needs a per-slot size override / temporary lineup addition so remaining slots recalc
  without corrupting fairness accounting. Trickiest item; pin behaviour with BDD before
  touching the engine. *(was G5)*

**T3.2 Co-coach plan proposals.** Depends on the T1.1 membership layer. A co-coach
proposes a rotation for the head coach to review:
- **`PlanProposalDB`**: match_id FK, proposed_by (account_id) FK, snapshot of
  `SlotAssignment` rows (diffs, not JSON copies), status `pending | accepted | rejected`,
  optional note.
- Co-coach opens Plan Review, tinkers, hits "Propose to head coach"; head coach sees a
  badge, opens a current-vs-proposed diff, and Accepts / Requests changes / Rejects.
*(was Phase F — unblocked once T1.1 membership exists)*

**T3.3 Plan Review polish.** Tinkering undo/redo command stack (V2 §6 spec) and the
CSV/Sheets export revisit against the review-screen data. *(was Phase D.2/D.3)*

### ⚪ Tier 4 — Decision points (only when the trigger fires)
- Open self-serve signup (drop the invite gate) — only after magic link + rate limiting
  are proven.
- 8-a-side preset; knockout bracket structure.
- Local-first/offline sync and any monetization: **re-evaluate only if** real usage shows
  offline failures or hosting costs bite. Not before.

### SEO technical foundations — ✅ SHIPPED (2026-07-18)
`robots.txt`, `sitemap.xml`, `llms.txt`, JSON-LD (`Organization` + `SoftwareApplication`),
canonical + OG/Twitter tags (`index.html` + `about.html`), 1200×630 `og-image.png`
(source `og-image.svg`). **Remaining manual step (you, on the live site):** submit
`sitemap.xml` to Google Search Console + Bing Webmaster Tools.

---

## Part 4 — Risks

| Risk | Mitigation |
|---|---|
| Refactor (Phase C) breaks live testers | Playwright smoke suite lands *first* (C.2 before C.1 completes); one module extracted per commit; per user's rule, nothing pushed until locally tested |
| Magic-link email deliverability (spam folders) | Postmark/Resend with verified domain; invite flow doubles as fallback login ("send me a fresh link") |
| Existing coaches' data stranded on old instances | Instances stay live until each coach confirms migration; squads are small — worst case is 10 minutes of re-entry |
| Consecutive-sit-out fix destabilises the rotation engine | It's an additive constraint + validator check; BDD scenarios pin current good behaviour before the change |
| Flaky tests erode trust in CI | While touching time_balancer for sit-outs, seed randomness in tests (inject `random.Random(seed)`) — removes flakiness without removing variety in production |
