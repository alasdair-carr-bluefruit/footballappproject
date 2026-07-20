# Level — Forward Development Plan

> Originally produced 2026-07-10 from a full codebase/history/requirements audit.
> **Refreshed 2026-07-20:** Phases A–E are all shipped, so the historical audit and the
> original dependency-ordered plan have been trimmed to a short completed record. The
> living part of this document is now the **Forward Roadmap** (Tiers 1–4). Big decisions
> live in `docs/adr/`; the multi-team design lives in `MULTI_TEAM_PLAN.md`.

---

## Part 1 — State of the Project

Everything through **v1.1 multi-user** is shipped and live on `app.keepthingslevel.com`
(magic-link auth, invite-only, per-account squad isolation, marketing site + early
access). The backend layering is healthy, the rotation algorithm is pure/tested/mutation-hardened,
and the **frontend is no longer the problem child** — `app.js` is split into ES modules
(`state`/`screens`/`pitch`/`setup-form`/`season`/`tournament`/`api`/`toast`), guarded by a
Playwright smoke suite + CSS/HTML visibility tests, and season⇄tournament parity is a
tested invariant. Test count is ~316 `def test_` functions.

### Documentation inconsistencies (from the 2026-07-10 audit) — all resolved

| # | Original finding | Status |
|---|---|---|
| 1 | CLAUDE.md "Current Phase" ~6 weeks stale (said v0.7 next) | ✅ Resolved — CLAUDE.md tracks v1.1 shipped + Tier 1 next |
| 2 | CLAUDE.md said goals keyed by player *name* | ✅ Resolved — doc corrected; goals keyed by `str(player_id)`, now in relational `GoalRecordDB` |
| 3 | Flaky-test names in CLAUDE.md didn't exist | ✅ Resolved — RNG seeded (`conftest.py` seed 1234); Known Limitations rewritten with real names |
| 4 | Test count said ~105 | ✅ Resolved — ~316 `def test_` now |
| 5 | requirements.md declared timer out of scope | ✅ Resolved — timer in scope (requirements.md §9.8, FR-38–40); shipped v0.9 |
| 6 | requirements.md had no tournament FRs | ✅ Resolved — tournament FRs present |
| 7 | Two competing futures (V1 evolve vs V2 rebuild) | ✅ Resolved — ADR 0001 "evolve, not rebuild"; V2 docs treated as a parts bin (see Part 2) |
| 8 | Refactor tasks (Phase C) none done | ✅ Resolved — Phase C complete (C.1–C.7), app.js modularised, dup logic removed, migrations inspection-based |
| 9 | Planning artefacts untracked in git | ✅ Resolved — `DEVELOPMENT_PLAN.md`, `MULTI_TEAM_PLAN.md`, `V1_MULTIUSER_PLAN.md` + ADRs all committed |
| 10 | Deploy guide institutionalised the N-instances model | ✅ Resolved — multi-user shipped; app runs as a single shared Railway + Neon instance |
| 11 | `TournamentDB.squad_id` FK not enforced | ✅ Resolved — DB-table FKs to `squads.id` enforced in `backend/db/models.py` |
| 12 | `docs/adr/` empty | ✅ Resolved — ADRs 0001–0004 written (evolve, magic-link, Railway/Neon, vanilla-JS modules) |

---

## Part 2 — Rebuild vs Evolve (decision recorded)

**Decision: evolve, don't rebuild.** Captured in **`docs/adr/0001-evolve-not-rebuild.md`**
(frontend module direction in `0004-frontend-vanilla-js-modules.md`). Rationale, in brief:

- **Backend kept** — good layering, the rotation algorithm is the isolated/tested crown
  jewel, and multi-tenancy was a mechanical change because isolation flows through one seam.
- **Frontend restructured in place, no framework** — the pain was *monolith + no tests*, not
  *vanilla JS*. Splitting into modules + a Playwright smoke suite fixed the fragility at a
  fraction of a React rewrite's cost. **Done.**
- **V2 rebuild docs = parts bin, not a plan** — adopted the multi-tenant schema *direction*,
  plan-review/manual-mode concepts, and (originally) the tinker undo/redo idea. Deferred
  indefinitely: local-first sync engine, React rebuild, ads/subscription tiers.
- **Auth went straight to magic link**, skipping the PIN stage — see `0002-auth-magic-link-first.md`.

*(The full 2026-07-10 audit narrative that backed this decision has been retired now that it's
shipped; the ADRs are the source of truth.)*

---

## Part 3 — Completed phases (record)

The original plan was ordered by dependency into Phases A–E. **All shipped:**

- **Phase A — Housekeeping.** Docs reconciled, planning docs versioned, bug kanban seeded. ✅
- **Phase B — v0.9 "Fairness & Trust."** Consecutive sit-out constraint, tinkering warning
  clarity, match timer (count-up + countdown + vibration), rotating competitive messages,
  in-app bug reporting. ✅
- **Phase C — Refactor for leverage.** C.1–C.7: app.js → ES modules, Playwright smoke suite,
  CSS/HTML visibility tests, mutation testing (all five algorithm modules hardened, RNG
  seeded), service-layer extraction, schema normalisation (JSON blobs → `SlotDB`/
  `SlotAssignmentDB`/`GoalRecordDB`/`MatchAvailabilityDB` via Alembic), analytics extraction,
  `toast.js` retry helper, SW shell-cache fix. ✅
- **Phase D — v1.0 "Plan Review" UX.** D.1 "Review the match plan" screen (season + tournament,
  shared `#screen-review`) with per-player slot/skill totals and under-slotted warning. ✅
  *(D.2 tinker undo/redo and D.3 export were moved out — undo/redo is now **deprioritised
  altogether**; export revisit remains a low-priority Tier 3 item.)*
- **Phase E — v1.1 Multi-user (magic link).** ✅ SHIPPED & LIVE on `feat/multi-user`.
  Magic-link auth (no PIN ever), invite-only onboarding, `AccountDB`/`InviteDB`/
  `LoginTokenDB`, `deps.py` isolation seam (`get_current_account`/`get_current_squad` +
  `owned_*` IDOR guards), early-access capture + Resend email, Railway + Neon deploy.
  **Scope note:** shipped model is **1 account ↔ 1 squad** (`AccountDB.squad_id`); the
  `SquadMembershipDB` join + roles were deferred — so **both multi-team (T1.1) and co-coach
  (T3.2) depend on adding that membership layer next.** The link was placed on `AccountDB`
  so this is additive.

---

## Forward Roadmap — prioritised (2026-07-18, refreshed 2026-07-20)

Ordered by **value × effort × demand**. ⚡ = quick win. Cross-cutting rules still apply to
every match-day item: **season ⇄ tournament parity** (mirror both flows in the same change)
and **additive migrations** for any schema change.

### 🔴 Tier 1 — Now

**T1.1 Multi-team (one coach, several squads). — NEXT.** *Real user demand — a live coach has
asked.* **Full design: `MULTI_TEAM_PLAN.md`.** Today it's 1 account ↔ 1 squad
(`AccountDB.squad_id`). Because the isolation seam is a single function
(`get_current_squad` in `deps.py`), this is additive, not a rewrite:
- **Data:** `SquadMembershipDB(account_id, squad_id, role)` join (preferred — also unblocks
  co-coach T3.2) + `AccountDB.active_squad_id`; Alembic revision with a **backfill** (one
  `owner` membership per existing account, `active_squad_id = squad_id`).
- **`get_current_squad`:** return the active squad *after* asserting membership — keeps the
  IDOR guarantee intact.
- **Endpoints:** `list` / `create` / `switch` / `delete` (delete folds in T1.4's clear-data).
- **Frontend:** team switcher + "Create new team" in the account menu; active team name
  visible; **state reset + refetch on switch** (season + tournament).
- **Tests:** isolation/IDOR (A can't reach B's squad), multi-squad happy path, backfill, delete.
- **Effort:** multi-hour — new table + risky data migration + frontend switcher + tests. Not
  a one-hour job.

**T1.2 ⚡ Signed-out → marketing site.** ✅ **SHIPPED (live).** Unauthenticated visitors on
`app.keepthingslevel.com` get a link back to `keepthingslevel.com` from the login screen.

**T1.3 Settings screen + account self-service.** ✅ **Mostly done (2026-07-20).** Settings
screen shipped (landing header, auth-on only): account email shown, multi-team teaser,
danger zone. Update-email with re-verify-to-new-address + old-address "reclaim your squad"
notice (`session_epoch` sign-out-all-devices) shipped. **Remaining:**
- **Invite a friend** — ⏳ reuse the invite-token flow for a shareable one-time link (currently
  admin-key gated — needs a non-admin variant). *(growth loop)*

**T1.4 ⚡ Clear squad & data (destructive).** ✅ **SHIPPED (2026-07-20).**
`/auth/account/clear-data` behind a type-to-confirm "DELETE" modal; backs the Privacy
Policy / Terms self-service delete promise.

**T1.5 Fix touch drag-and-drop in tinker mode.** ✅ **BUILT (2026-07-20, pending device test + push).**
Root cause: the coin swap used the HTML5 Drag-and-Drop API, which never fires from touch on
iOS Safari / Android Chrome. Rewrote it to **Pointer Events** (`pointerdown`/`move`/`up` +
`setPointerCapture`, 6px drag threshold, `elementFromPoint` hit-test, `data-slot-index`/
`data-pos-key` on coins) so mouse **and** touch both work; added `touch-action:none` on
draggable coins so a finger-drag swaps instead of scrolling. Tap-to-open-swap-picker fallback
and long-press-to-score gesture preserved. Shared `pitch.js` path → both flows. *(Touch gesture
isn't covered by the e2e picker path — needs a real-device check.)*

### 🟠 Tier 2 — Next (retention + product-led growth)

**T2.1 Shareable match-day moments.** The share-image is the viral surface. Progress:
- **"Level" branding on the shared match report** — ✅ **DONE.** Wordmark/spirit-level mark on
  the share image so every WhatsApp post is a soft ad.
- **Goal celebration** — ✅ **BUILT (2026-07-20, pending test).** Firework-confetti burst
  (`celebrateGoal()` in `pitch.js`) on every goal-add path; `pointer-events:none` so it never
  blocks recording, self-removes, skipped under `prefers-reduced-motion`.
- **Man of the Match on the export** — ⏳ `motm_player_id` (nullable) on `MatchDB`; pick at
  full-time from players who actually played; render on the share image.
- **Record assists** — ⏳ per-player by id, on-pitch non-scorer, surfaced in stats + export.

**T2.2 FA 2026/27 cornerstone blog + SEO content + reach.** Marketing-site blog
(`marketing/blog/`, plain HTML, `FAQPage`/`Article` JSON-LD, add to `sitemap.xml`).
Cornerstone + cluster posts on the FA 2026/27 youth changes, equal playing time, fair
rotation, game time by age, sharing keeper time. Off-site: creator outreach (cite/link
freely, **never imply endorsement without consent**), County-FA listings, community
participation, founder safeguarding credibility. *(SEO technical foundations ✅ shipped.)*

**T2.3 Colourway switcher + colourblind mode.** ✅ **BUILT (2026-07-20, pending test + push).**
First theming layer: `:root[data-theme="colourblind"]` in `style.css` re-maps the categorical
(GK/DEF/MID/FWD) + player-state + status-badge tokens to an Okabe–Ito-based colourblind-safe
palette; the Signal-Lime brand accent is kept. Player-status **badges** (`--badge-gk/gkpref/
emergency/def`) were tokenised so themes re-map tokens, not selectors. Non-hue cues (🧤/↑/↓/⚽,
position labels) preserved. New `theme.js` (persists `gaffer_theme`, no-flash `<head>` boot
snippet), a **Colour theme** control in Settings (Level / Colourblind-friendly), `tokens.json`
synced (v2.1.0, `colourway` + `badge` sections), SW→v38. *(Scope: Default + Colourblind-safe,
per decision 2026-07-20; High-contrast deferred.)*

**T2.4 Configurable max subs on tournament creation.** ✅ **BUILT (2026-07-20, pending local test + push).**
`max_subs` (nullable) added to `TournamentDB` + denormalised onto `MatchDB`; threaded through
`build_tournament_config` (overrides `mid_period_subs`) and every call site; size-aware selector
(1..outfield-count, default = preset) on the tournament create/edit form; Alembic revision
`a8d3e6f1c2b4`; unit + integration tests; SW→v37. **Behaviour note:** `mid_period_subs` is a
**soft** cap — the engine still fields a full team and respects fair playing time, so in an
equal-time tournament with a full bench it may still rotate everyone (it can't bench a child
past their fair share to honour a low cap). A **hard** cap that overrides within-match fairness
would be a larger engine change — deferred unless the coach wants it. Original scope below:

Tournaments usually have no half-time,
so the coach wants direct control over subs per match: a size-aware picker (1–4 subs at
5v5, scaling up). The engine already has per-size limits (`GameConfig.mid_period_subs` /
`break_subs`, enforced by `validator.py`) — this exposes them. Work: `max_subs` on
`TournamentDB` (additive migration) threaded into `GameConfig`, size-aware selector on the
tournament create/edit form, validator wiring; mirror the season⇄tournament setup form where
shared. *(user request 2026-07-19. Smaller than T1.1 — good "otherwise" pick.)*

### 🟡 Tier 3 — Bigger bets, later

**T3.1 Match-day engine features.**
- **Adjust formation in tinker mode, per-quarter.** *User's preferred approach (2026-07-20):*
  change the formation from within tinker mode, applying **only to the quarter being
  tinkered** — this reuses the existing tinker locked-slot model and
  `config.formation.outfield_positions()`, so it **eliminates the need to touch the rotation
  algorithm** (no mid-match re-derivation of future slots against a new global formation).
  Much smaller than the original "adjust formation mid-match" framing; could move earlier.
- **Add an extra player mid-match / power play** — per-slot size override so remaining slots
  recalc without corrupting fairness accounting. Trickiest item; pin with BDD first.

**T3.2 Co-coach plan proposals.** Depends on the T1.1 membership layer. `PlanProposalDB`
(match_id, proposed_by, slot diffs, status); co-coach tinkers and "Propose to head coach";
head coach reviews a current-vs-proposed diff and Accepts / Requests changes / Rejects.

**T3.3 Export revisit.** Revisit CSV/Sheets export against the review-screen data.
*(Tinker undo/redo — formerly here — is **deprioritised altogether** and dropped from the roadmap.)*

### ⚪ Tier 4 — Decision points (only when the trigger fires)
- Open self-serve signup (drop the invite gate) — only after magic link + rate limiting proven.
- 8-a-side preset; knockout bracket structure.
- Local-first/offline sync and any monetization — re-evaluate only if real usage shows
  offline failures or hosting costs bite. Not before.

### UX polish
Shipped (pushed 2026-07-20):
- **"Rotate keeper?"** — renamed the "Share goalkeeper time" switch and moved its explanation
  behind a click-to-reveal (?) info button (reusable `.info-btn`/`.field-info`), both flows.
- **Manual mode promoted** — the availability screen's hidden "assign manually" link is now a
  proper secondary button "Manually create plan" with an explainer modal (Level rotates fairly /
  manual mode = you build lineups, still tracks goals + shows skill ratings).
- **Generating-plan loading overlay** — spinner + "Generating game plan…" + a random,
  positive/development-themed manager quote (rotates every 4s), on season + tournament generate.
  Includes an Uncle Iroh line and a Roy Kent "WHISTLE!!!!" easter egg. New `frontend/quotes.js`.

Built 2026-07-20 (pending test, not pushed):
- **Goal celebration** — see T2.1.
- **"Check for updates" in Settings** — clears caches + updates the SW + reloads, so an
  installed PWA (esp. Android, no easy refresh) can pull the latest version on demand
  (`btn-check-updates` in `settings.js`).

### SEO technical foundations — ✅ SHIPPED (2026-07-18)
`robots.txt`, `sitemap.xml`, `llms.txt`, JSON-LD (`Organization` + `SoftwareApplication`),
canonical + OG/Twitter tags, 1200×630 `og-image.png`. **Remaining manual step (you, on the
live site):** submit `sitemap.xml` to Google Search Console + Bing Webmaster Tools.

---

## Part 4 — Live risks

| Risk | Mitigation |
|---|---|
| Multi-team (T1.1) Alembic backfill corrupts existing coaches' data | Fully additive; test the backfill explicitly (one `owner` membership + `active_squad_id == squad_id` per account) before deploy; big squad-scoped tables untouched |
| State leaks across teams on switch | Clear squad-scoped `state` + refetch on switch (both season and tournament); isolation tests assert A never reads B's active squad |
| Magic-link email deliverability (spam folders) | Resend with verified domain; invite flow doubles as fallback login |
| Cloudflare serves stale JS/sw.js for ~4h after deploy | Purge CF cache on deploy — incognito won't help (it's the CDN) |
