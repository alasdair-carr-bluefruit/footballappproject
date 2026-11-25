# First-run walkthrough + first-use intros — build plan

> Status: **planned 2026-11-25, not started.** Roadmap item 6 in `DEVELOPMENT_PLAN.md`.
> Builds on the shipped What's new carousel (`frontend/whats-new.js`, `.feature-intro`
> styles, `.demo-*` / `.wn-*` animations). Read that file first.

## 1. What the owner asked for

- A **walkthrough of Level for new coaches** when they first join, on the same full-screen
  animated pattern as What's new.
- Each feature / decision gets a **rationale a coach understands** (why the app does it), never
  technical detail (no databases, backend, algorithms).
- **Always skippable** — a Skip in the same top-right corner on every step; never forced.
- The same pattern then shows **the first time a coach uses any feature** (first-use intros).

## 2. Design principles

1. **Short up front, detail at the moment of use.** Coaches skip long tours. The welcome tour is
   at most 6 cards about *why Level plans the way it does*; the "how do I use this screen" detail
   comes later, as a 1–3 card intro the first time they reach that screen.
2. **One idea per card.** Title (≤5 words) · one-sentence what · one or two sentence **Why:** ·
   a small looping animation. Same layout as What's new, so it feels like one system.
3. **Coach language.** "Every child gets the same time on the pitch", not "equal-time
   constraint". Never say *violation*, *algorithm*, *slot*, *database*. Say *spell* or
   *half of a quarter* rather than *slot*.
4. **Only verified FA claims** (see memory `reference_fa_equal_playing_time_sources`). If a card
   cites the FA, link the FA page in a small "Source" line; otherwise make no statistical claim.
5. **Skippable, replayable, switch-off-able.** Skip on every card; "Replay the tour" in
   Settings; a "Show tips" switch in Settings turns all first-use intros off.
6. **Accessible.** `role="dialog"`, focus on the primary button, Esc = Skip, demos
   `aria-hidden`, "2 of 6" counter, reduced-motion shows each animation's end state.

## 3. Part A — the welcome tour (new head coach)

**When:** straight after a new head coach finishes **Create my team** (the join screen,
`#screen-join`) and before the existing team-name screen (`#screen-tutorial`). The last card's
button is **"Set up my team →"**, which lands on the team-name screen. Skipping lands there too.
Assistants get Part C instead.

| # | Title | Animation idea | What (1 line) | Why (coach rationale) |
|---|---|---|---|---|
| 1 | Fair time, done for you | 8 bars of uneven height level out to the same height | Level plans who plays when, so every child gets the same time on the pitch. | The FA recommends equal playing time at grassroots, and lack of game time is the top reason children give for stopping playing. *(Source: FA / Cornwall FA equal playing time — verified links in memory.)* |
| 2 | Everyone tries positions | One coin moves DEF → MID → ATT across Q1–Q3 | Children rotate through the positions you've said they can play. | The FA discourages fixing children into one position before 12 — the tallest at eight may be average at fourteen. |
| 3 | Subs halfway through each quarter | A timeline: Q1 start / mid, coins swapping at the mid marker | Changes happen at the start and halfway through each quarter. | Nobody sits out a whole quarter, and bench spells stay short. |
| 4 | Your keeper | Keeper coin in goal, then swapping out while a backup goes in | You choose who can go in goal; a keeper-only child shares time like everyone else. | Without sharing, a keeper-only child would play every minute while others wait. |
| 5 | Even line-ups | Two scales tipping, then balancing | Skill ratings keep each line-up evenly matched — they're private to you. | Every spell is a fair contest, so no group of kids gets stuck in the "weak" team. Assistants never see ratings. |
| 6 | You're still the coach | A dashed "tinker" coin swaps places with another | Change anything with Tinker; Level re-balances what's left. | The plan is a starting point, not a rule — you know your players. |

Copy is a first draft for the owner to edit. Cards 3–5 describe current engine behaviour
(mid-period subs, `share_gk`, skill balancer) — check them against `CLAUDE.md` before shipping.

## 4. Part B — first-use intros (1–3 cards each, shown once)

Triggered the first time the coach reaches each screen. Season ⇄ tournament **parity**: wherever
a trigger exists in one flow, add it to the other in the same change.

| Intro id | Trigger (code entry point) | Cards (what → why) |
|---|---|---|
| `first-squad` | first `openPlayerForm()` (`screens.js`) | Positions they're happy in → rotation uses them · Skill 1–5 → even line-ups, private · "Keeper only?" → only if they truly never play outfield |
| `first-setup` | first New match / New tournament form (`setup-form.js`) | Format by age (5v5 U8–U9 …) → matches FA formats · Fairness slider: Equal ↔ Start strong → your choice for big games · Rotation slider: specialist ↔ all-rounder |
| `first-review` | first `renderReview()` (`pitch.js`) | Reading the grid (quarters across, positions down) · Notes like "out of position" or "long bench spell" are suggestions, not errors · View on pitch / adjust plan |
| `first-tinker` | first time Tinker turns on | Drag or tap to swap · edited spells lock, the rest re-balances · "Sorted. Plan updated." |
| `first-live` | first `btn-review-start` / Start match | Next only previews ahead; "Start period" moves the game on · Tap a player for a goal or injury · One phone runs the match, others watch and can take over |
| `first-tournament` | first tournament lobby (`tournament.js`) | Minutes balance across the whole day, not one match · Guests for the day · Per-day position changes |
| `first-rested` | first untick on the season picker | Unavailable vs Rested → rested children are owed time later (reuse What's new slide) |

**Existing coaches must not get intros for things they already use.** On first load after
release, mark as seen: `first-squad` if they have players; `first-setup`, `first-review`,
`first-tinker`, `first-live` if they have any match; `first-tournament` if they have a
tournament. (Data check on the server — see §6.)

## 5. Part C — assistant welcome (3 cards)

After an assistant joins (`?assist=` flow in `auth.js`): 1) You can see the plans, reports and
stats for {team}; 2) You can create and run matches of your own, and the head coach can hand you
one; 3) One phone runs a live match — tap "Take control" if you're running it today. Why lines in
the same coach language. No skill-rating mention beyond "the head coach keeps ratings private".

## 6. Technical design

**Generalise the engine.** Move the carousel mechanics out of `whats-new.js` into
`frontend/intro.js`:

```js
showIntro(id, slides, { kicker, finalLabel, onDone, onSkip, fromSettings })
```

`whats-new.js` becomes a caller (its `SLIDES` + version). Slides keep the same shape
(`title, body, why, where?, demo, beta?, headOnly?`). Shared demo primitives get small helper
functions (coin row, chip split, bar chart, timeline, scales) so new cards are a few lines.
Reuse the existing `#whats-new` overlay markup (rename to `#intro-overlay`) so there's one
dialog.

**Seen-state on the account (recommended).** New coaches often set up on a laptop and run
matches on a phone — a tour that re-appears per device would grate. Add
`AccountDB.intros_seen` (JSON text, default `"{}"`, map `id → ISO date`) via an Alembic
migration, return it from `GET /api/auth/me`, and add `POST /api/auth/intros/{intro_id}`
(own account only; no team capability needed; add to the route-coverage allow-list as an
account route). Keep localStorage as the fallback when auth is off, and as a cache so an intro
never flashes twice while the POST is in flight. Optionally move What's new onto the same store
(`whats-new:2026-11`).
→ backend + migration ⇒ **goes via staging**.

**Backfill for existing coaches** (§4): the `/me` handler (or the migration) computes the
"already used" intros from existing rows (players / matches / tournaments) the first time
`intros_seen` is empty, so no existing coach sees first-use intros for features they know.

**Settings:** "Replay the welcome tour" button, and a "Show tips for new screens" switch
(stored as `intros_seen.__tips_off`).

**Reconcile existing onboarding:**
- `#screen-tutorial` (team name + logo) stays as the form step after the tour; trim its intro
  paragraph and the two mode descriptions, since the tour now covers them.
- The landing tip "Start by building your squad!" (`#squad-onboarding`) stays — it's the
  "do this next" pointer, not an explainer.
- New coaches are already marked as having seen What's new (`markWhatsNewSeen`); keep that.

**Tests:**
- e2e `conftest.py`: generalise `_whats_new_already_seen` to pre-mark **all** intros as seen
  (welcome + first-use) unless a test is marked `show_intros`.
- New e2e: a new head coach joins → welcome tour → Skip on card 3 lands on the team-name
  screen; finishing lands there too; replay from Settings; first-use intro shows once then never
  (parametrize season/tournament for `first-setup` / `first-review` / `first-live`); an assistant
  gets the assistant welcome, not the head tour; seen-state follows the account (second browser
  context, same cookies, no tour).
- Integration: `POST /api/auth/intros/{id}` marks seen, is idempotent, only touches own account;
  backfill marks the right intros for an account with matches.
- Unit: intro ids unique; every slide has title/body/why.

## 7. Phasing

1. **P1 — engine + welcome tour + account seen-state** (staging; migration). Settings "Replay".
2. **P2 — first-use intros for review, Tinker, live match** (the three screens coaches find
   hardest), with the backfill. Parity tests.
3. **P3 — remaining intros + assistant welcome + "Show tips" switch.** Move What's new onto the
   account store.

Each phase: bump the SW cache, update `DEVELOPMENT_PLAN.md`, purge Cloudflare after the deploy.

## 8. Questions for the owner before P1

1. Is six cards right for the welcome tour, or fewer (say 4: fair time, positions, keeper, Tinker)?
2. OK to store "seen" on the account (needs a small database change, via staging) rather than per phone?
3. Should the FA cards show a small "Source: The FA" link?
4. Card copy: happy for me to draft all cards in full for you to edit in one go before building?
