# Level — Development Plan

> The **only** roadmap. Live work only: infra to-dos, **▶ Next up** (the ordered list), the
> backlog, decision points and risks. Shipped history lives in `docs/archive/CHANGELOG.md`;
> big decisions in `docs/adr/`; assistant-coach design in `docs/ASSISTANT_COACH_PLAN.md`.
> Restructured 2026-11-24 (was 522 lines of mostly history).

**State (2026-11-24):** everything through v1.1 multi-user, multi-team (T1.1) and assistant
coaches P1–P2 (T3.2) is live on `app.keepthingslevel.com` for ~8 coaches. 583 tests collected.
FA FutureFit guides are live on `keepthingslevel.com/blog/`.

## Lessons to keep (don't re-learn these)
- **Bench-run breaking:** reordering *selection* to favour players on a run cut runs but pushed
  9-player squads from 14% → 79% of plans with a >1-slot time gap. Only compensating swaps are
  allowed (playing time provably unchanged). Re-measure before touching it.
- **Coach-facing copy:** never say "violation"; a generated plan's flags use the quiet info tone,
  the ⚠ tone only after the coach has tinkered. Competitive mode stays selectable.
- **FA copy accuracy:** only FA-owned sources; never imply FA endorsement; the U6–U11 / U12–U16
  equal-time split is a county-guidance *club policy*, not an FA mandate.
- **DEF is not special** (owner, 2026-11-24) — unticked DEF = soft, like any position (ADR 0005).
- **CI installs from `uv.lock`** — unpinned `pip install` had CI red Sep–Nov 2026 on a FastAPI
  version production never ran. Never go back to an unpinned install.
- `mid_period_subs` / `max_subs` is a **soft** cap (fair time + full team win over it).

---
## To do — infrastructure follow-ups (added 2026-09-29)

Loose ends from moving the production database from Neon us-east-1 to London
(`aws-eu-west-2`) on 2026-09-29 (it was ~260ms per query from Railway Amsterdam).

- [ ] **Create a `staging` branch in the London Neon project** (Branches → New branch,
      from the production branch) and point Railway **staging**'s `DATABASE_URL` at it.
      Staging still uses the old US project's `ep-old-union` branch.
- [ ] ⚠️ **OVERDUE (was due ~2026-10-06) — Delete the old US Neon project** (both branches) once production has run cleanly
      on London for a week *and* staging has moved. Until then a copy of
      coach data remains in the US, which the privacy policy (§6) no longer allows for.
- [x] **`staging` branch exists on GitHub** (pushed with T3.2, last updated 2026-11-16, level
      with `main`). *Still worth a glance that Railway's staging environment builds from it.*
- [x] **Measure after the move** — done 2026-09-29: `Server-Timing` shows ~16ms per query
      (was ~260ms) with 0 new connections per request (pooling works; distance was the cause).

## Ease-of-use sprint (from the 2026-11-24 audit + owner review)

**Built locally 2026-11-24, frontend only (not pushed yet):** settings remembered per team (from the
team's latest match/tournament, so it works on any device), age groups under the size buttons
(U8–U9 / U10–U11 / U12–U13, no "FutureFit" wording), "N of M coming" on both player pickers,
"Keeper only" / "No DEF" badges + a warning in the player form, no skill stars on the tournament
picker, tap a live player → Goal / Injured (injured asks who comes on and keeps the rest of the
slot put), one LIVE marker, Next starts the next period once its clock has run, plan grid with
"Q1 start/mid" headers + first names + skill row behind a toggle, onboarding → add players,
"Save & add another", back/button labels.

**Built locally 2026-11-24, round 2 (backend → goes via staging):**
- ✅ **Login fix:** `pool_pre_ping` + `pool_recycle` on the Postgres engine (Neon drops idle
  connections → first request 500 → "Something went wrong"), plus one quiet retry on request-link.
- **CI fixed:** installs from `uv.lock` (was red since Sep on FastAPI 0.165).
- ✅ Login + CI fixes **SHIPPED** to staging + main 2026-11-24 (`dc5b116`, SW v62). The rest below is still local.
- **Rested vs unavailable:** unticking a player on the season picker offers Unavailable
  (default) / Rested. Rested is stored (`match_rested`, migration `b8e2f4a6c9d1`).
  `GET /api/matches/stats/owed` gives the advisory "N′ owed" per player, from finished Equal-play season
  matches. It shows on the picker and the review screen. The engine is untouched. Tournaments don't have it (one-day event).
- **DEF not special:** migration `a3d7c1e9f4b2` clears `def_restricted`; "No DEF" badge removed.
- **Keeper only? asked explicitly** when only GK is ticked.
- **Housekeeping:** `render.yaml` / `Procfile` deleted; `feat/multi-user`, `feature/v0.4-ui`,
  `feature/v0.5-api` deleted locally + on GitHub. Manual left for the owner: shut down the Render
  services; Neon London staging branch + delete the US project (infra list above).

**Owner decisions (2026-11-24):** season fairness = advisory flag ✓ · keeper: no engine change ·
settings per team ✓ · keep 6v6 · stats in minutes · shirt numbers fine as-is · **never:** parent
view, 11v11, league cap warnings · MoM/assists low priority.

**Granular positions — built 2026-11-24, on `main` 2026-11-25 (SW v68).** "Detailed
positions" switch on the squad page (`squads.granular_positions`, migration `c4f1a8e2d7b3`); turning
it on asks first. Picks become GK · LB/CB/RB · LM/CM/CAM/RM · LW/CF/RW (CB2→CB, CM2→CM, CF2→CF).
**Reversible by design (owner wanted coaches to try it):** picks are stored as given and the toggle
only changes how they're read (`models.rotation.position_mode` / `picks_allow`). Off = a detailed
pick reads as its line; a band pick always covers its whole line, so squads half-converted still
plan sensibly. Each detailed position counts for rotation variety when on (LW ≠ RW). Also fixed
for both modes: a same-slot repair pass stops the greedy assigner stranding a narrow picker (e.g.
DEF-only at RM), and late swap passes (skill balance, mid-quarter alignment) can no longer move a
player out of a pick. Tournament chips stay by line but keep detailed picks. Tests:
`tests/unit/algorithm/test_granular_positions.py`, `tests/integration/test_granular_positions_api.py`,
`tests/e2e/test_granular_positions.py`.

## ▶ Next up (recommendation, 2026-11-23)

Tier 1 is done and T3.2 phases 1–2 are live, so the order below is by risk to live coaches
first, then value × effort. Details for each are in the tier sections further down.

1. **Close the US Neon loose end** (infra list above) — a copy of coach data still sits in
   the US, which privacy policy §6 no longer allows. Manual, ~30 min, highest-priority non-code item.
2. ~~Make `def_restricted` truly hard~~ — **dropped (owner, 2026-11-24).** The last-resort
   fallback is acceptable: the coach already sees an "out of position" warning, so it stays soft.
3. ~~League daily playing-time cap in tournaments~~ — **dropped (owner, 2026-11-24).**
4. **T2.1 Man of the Match + assists** — owner: low priority (2026-11-24).
5. ~~**T2.2 SEO cornerstone**~~ — on-site content built 2026-11-23 (4 guides + hub); sitemaps submitted to Google + Bing; remaining: outreach.
6. **In-app "New feature" banners + mini tutorials (owner idea, 2026-11-25)** — usability. A
   dismissible "New" banner (per account, remembered server-side so it follows the coach across
   devices) that opens a short full-screen explainer: the why, plus a simple animation of what
   changes (e.g. DEF chip → LB/CB/RB). First building block shipped with detailed positions: the
   `.feature-intro` full-screen pop-up + `.chip-demo` animation (`index.html` `#granular-overlay`,
   reduced-motion safe). **Owner 2026-11-25:** if it works well, show an intro like this the
   **first time a coach uses any feature** — and it must **always be skippable** (a Skip in the
   corner on every step, never a forced walkthrough). Next: a small registry (`id`, title, steps,
   min app version), a "seen" list on `AccountDB`, the banner on home, and first-use triggers
   for Tinker, Rested, live match, tournaments, share.
7. Then **T3.2 P3** (comments + proposals) or **T3.1** per-quarter formation in tinker, depending on
   which a coach asks for first. Open question for the owner: should assistants be able to *run*
   (not edit) any match on matchday? Today only the plan owner or head coach can.


## Backlog (unordered — ▶ Next up says what's next)

### Growth & content

**T2.1 Shareable match-day moments.** The share-image is the viral surface. Progress:
- **"Level" branding on the shared match report** — ✅ **DONE.** Wordmark/spirit-level mark on
  the share image so every WhatsApp post is a soft ad.
- **Share the team sheet (pre-match)** — ✅ **SHIPPED (built 2026-09-13, on `main`).** Came
  straight from watching a coach screenshot the plan grid and paste it into the co-coaches'
  WhatsApp group. `frontend/plan-image.js` renders that same grid as a branded PNG (positions ×
  periods with full names, a per-period BENCH row, the ⚡ skill-total row, slots-per-player totals, `keepthingslevel.com`
  footer) behind a **Share** button in the review-screen header. **Portrait by design** — the
  grid wraps after 4 periods and stacks (same split the review screen uses on mobile), so the
  image reads on a phone in a group chat rather than shrinking to a landscape strip — so it covers a season match, a
  single tournament match, and the tournament "Review all plans" page (every match stacked in one
  image). Native share sheet on mobile, download fallback on desktop. Both flows feed it through
  `state.reviewShare` / `setReviewShare()`, so season ⇄ tournament parity is structural. SW→v50;
  e2e `tests/e2e/test_share_plan.py` (parametrized season/tournament + the all-plans page).
- **Goal celebration** — ✅ **SHIPPED (built 2026-07-20, on `main`).** Firework-confetti burst
  (`celebrateGoal()` in `pitch.js`) on every goal-add path; `pointer-events:none` so it never
  blocks recording, self-removes, skipped under `prefers-reduced-motion`.
- **Man of the Match on the export** — ⏳ `motm_player_id` (nullable) on `MatchDB`; pick at
  full-time from players who actually played; render on the share image.
- **Record assists** — ⏳ per-player by id, on-pitch non-scorer, surfaced in stats + export.
- **Opposition own goals** — ✅ **SHIPPED 2026-11-14/16 (SW v59–v60).** Recorded live, credited
  to the team's score; a save that omits `own_goals` no longer wipes them.

**Cornwall Youth League 2026-27 rules — app-relevant clauses** (`docs/reference/cornwall-youth-league-rules-2026-27.pdf`,
added 2026-08-08). Not yet built against; the first two are candidate features.
- **Maximum playing time in one day**, by age group: U7 40min (60 in tournaments), U8/U9 40 (60),
  U10/U11 60 (90), U12/U13 80 (120), U14/U15 100 (150), U16 100 (150), U17/U18 120 (180).
  **Tournament mode has no notion of this** — cross-match fairness balances minutes between players
  but never caps a player's day. A coach can currently breach a league rule without being told.
- **Match-day squad ≤ double the team size** (Mini-Soccer). 5v5→10, 7v7→14, 9v9→18.
- **Subs, Mini-Soccer:** unlimited, at any stoppage, return subs allowed — so the engine's sub caps
  are a coaching preference here, not a league constraint. U11–U18: 5 from 5 return subs. 3v3: none.
- **Period lengths** are bounded per age group (e.g. U8/U9 quarters 5–10 min, U10/U11 10–12.5).
- **Formats the app does not support:** 3v3 (U7) and 11v11 (U12+ in this league). Worth knowing
  before demoing to a club with those age groups.

**T2.2 FA 2026/27 cornerstone blog + SEO content + reach.** 🟢 **On-site content BUILT (2026-11-23).**
`marketing/blog/` (Guides): cornerstone `fa-futurefit-2026-27-changes` + cluster posts
`youth-football-game-time-by-age`, `how-to-rotate-players-fairly`, `sharing-goalkeeper-time`, and
a `blog/index.html` hub. Each has Article + BreadcrumbList + FAQPage JSON-LD (FAQ mirrors the
visible "Quick answers"), sitemap + `llms.txt` entries, "Guides" in nav/footer site-wide, and
`why-equal-playing-time` now cites FutureFit. **Primary source: England Football, *FutureFit: Know
Your Format* (Feb 2026)** — formats by age (U7 3v3 · U8–9 5v5 · U10–11 7v7 · U12–13 9v9 · U14+
11v11), match lengths (6–10 / 40 / 50 / 60 / 70–90 min), laws table, and p.7: *"For u8 and above,
equal playing time (at least 50%) is the best practice recommendation."* Pages generated by a
one-off script (output committed as plain HTML; no build step). ✅ **Sitemap submitted to Google
Search Console (Domain property, verified via Cloudflare DNS) and Bing Webmaster Tools (2026-11-23).**
**Still to do (owner):** off-site outreach + County-FA listings below.
**Product implications spotted while researching FutureFit (not built):** (1) setup presets
could default match length/periods from the age group (5v5 = 40 min, 7v7 = 50, 9v9 = 60);
(2) the laws table lists a **power play** at U8–U11 — overlaps T3.1 "extra player / power
play"; (3) **6v6 is no longer an FA format**, and Level can't serve U7 3v3 (no rotation needed
— everyone plays) or **U14+ 11v11** coaches; 11v11 support is the bigger gap.
Original scope: Marketing-site blog
(`marketing/blog/`, plain HTML, `FAQPage`/`Article` JSON-LD, add to `sitemap.xml`).
Cornerstone + cluster posts on the FA 2026/27 youth changes, equal playing time, fair
rotation, game time by age, sharing keeper time. Off-site: creator outreach (cite/link
freely, **never imply endorsement without consent**), County-FA listings, community
participation, founder safeguarding credibility. *(SEO technical foundations ✅ shipped.)*


### Bigger bets

**T3.1 Match-day engine features.**
- **Adjust formation in tinker mode, per-quarter.** *User's preferred approach (2026-07-20):*
  change the formation from within tinker mode, applying **only to the quarter being
  tinkered** — this reuses the existing tinker locked-slot model and
  `config.formation.outfield_positions()`, so it **eliminates the need to touch the rotation
  algorithm** (no mid-match re-derivation of future slots against a new global formation).
  Much smaller than the original "adjust formation mid-match" framing; could move earlier.
- **Add an extra player mid-match / power play** — per-slot size override so remaining slots
  recalc without corrupting fairness accounting. Trickiest item; pin with BDD first.

**T3.2 Assistant coach mode.** ✅ **P1, P1.5 and P2 SHIPPED to `main`/live (2026-11-14, SW v58)**; P3 planned — full plan + locked decisions in
**`docs/ASSISTANT_COACH_PLAN.md`**. `SquadMembershipDB` with per-team roles (one `head`, many
`assistant`s; an account can be head on its own team and assistant on another), with
capability-based guards in `deps.py` plus a deny-by-default route-coverage test.
- **P1 read-only:** assistants see stats, reports and plans (drafts included). Skill ratings are
  redacted server-side, while pooled slot totals stay visible. Assistant invites admit new people.
- **P1.5 assistant-authored plans — ✅ SHIPPED (2026-11-14, SW v58):** an
  assistant can create a match/tournament and edit, tinker and run the ones they own
  (`created_by_account_id` = plan owner, capability `author_plan`, per-row
  `editable_match`/`editable_tournament`); other assistants stay read-only; lists show "Plan by …".
  Also built: **head-coach hand-over** of a match/tournament to an assistant (and back), a
  **"Reviewed ✓" mark** (a mark, not an Accept gate; clears when the assistant changes the plan),
  **plan emails** both ways (opt-out in Settings), and assistants adding **temporary players**
  to tournaments they run.
- **P2 one controlling device + server clock — ✅ SHIPPED (2026-11-14):**
  Start Match claims control for that device; anyone else watches live (polled, read-only) and
  whoever may run the match can Take control; the clock lives on the server. Never enforced
  against a client that sends no device id, so a deploy can't strand a live match.
- **P3 comments + proposals (planned):** `PlanCommentDB`, `PlanProposalDB`. The head coach accepts, tinkers or rejects.
- Head-coach transfer deferred. Goes via `staging` (migrations/auth/deps).

**T3.3 Export revisit.** An `.xlsx` export already exists (season: `GET /api/matches/export/season.xlsx`,
plus tournament stats export buttons — `services/spreadsheet_export.py`). Remaining: revisit it against
the review-screen data (per-slot plan grid).
*(Tinker undo/redo — formerly here — is **deprioritised altogether** and dropped from the roadmap.)*


## Decision points (only when the trigger fires)
- Open self-serve signup (drop the invite gate) — only after magic link + rate limiting proven.
- 8-a-side preset; knockout bracket structure.
- Local-first/offline sync and any monetization — re-evaluate only if real usage shows
  offline failures or hosting costs bite. Not before.


---

## Live risks

| Risk | Mitigation |
|---|---|
| A migration corrupts existing coaches' data | Additive Alembic revisions only; test backfills against a copy of prod-shaped data; migrations go via `staging` (`docs/STAGING.md`) |
| Two devices fight over a live match | One controlling device (`controlled_match`, 409 `not_controller`), never enforced against a request with no `X-Device-Id`, so a deploy can't strand a live match |
| Coach data outside the UK/EU | Old US Neon project still exists — delete it (infra list) |
| State leaks across teams on switch | Clear squad-scoped `state` + refetch on switch (both season and tournament); isolation tests assert A never reads B's active squad |
| Magic-link email deliverability (spam folders) | Resend with verified domain; invite flow doubles as fallback login |
| Cloudflare serves stale JS/sw.js for ~4h after deploy | Purge CF cache on deploy — incognito won't help (it's the CDN) |
