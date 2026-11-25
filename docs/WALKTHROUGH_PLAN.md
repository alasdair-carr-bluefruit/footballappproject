# First-run walkthrough + first-use intros — build plan

> Status: **BUILT 2026-11-25 (P1–P3 together), local — ships via `staging`.** Deviations from this plan: the
> overlay keeps its `#whats-new` id (tests and CSS use it); "spell" became **"stint"** (owner);
> card 2's FA line was reworded to what the verified source says; tournaments got an extra first
> card on *why* tournament mode exists (owner); the rested intro shows the first time the season
> "who's coming" screen opens (owner: belongs with the first match). Previously:
> planned 2026-11-25. Owner decisions taken (§8). **Card copy lives in
> the review doc https://claude.ai/artifact/WpTUxx7F7tdZzz7yxnRBKo** — build from the owner's
> edited version of it, not from the drafts below. Roadmap item 6 in `DEVELOPMENT_PLAN.md`.
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
4. **Only verified FA claims** (see memory `reference_fa_equal_playing_time_sources`), and **no
   source links on cards** (owner). No statistics on cards.
5. **Skippable, replayable, switch-off-able.** Skip on every card; "Replay the tour" in
   Settings; a "Show tips" switch in Settings turns all first-use intros off.
6. **Accessible.** `role="dialog"`, focus on the primary button, Esc = Skip, demos
   `aria-hidden`, "2 of 6" counter, reduced-motion shows each animation's end state.

## 3. Part A — the welcome tour (new head coach)

**When:** straight after a new head coach finishes **Create my team** (the join screen,
`#screen-join`) and before the existing team-name screen (`#screen-tutorial`). The last card's
button is **"Set up my team →"**, which lands on the team-name screen. Skipping lands there too.
Assistants get Part C instead.

**4 cards (owner, 2026-11-25):** 1) Fair time, done for you · 2) Everyone tries positions ·
3) Even line-ups · 4) You're still the coach. "Subs halfway" and "Your keeper" were cut from the
tour (the keeper point lives in the first-squad intro instead). Full wording + animation notes:
the review doc linked at the top. No FA source links on cards.

Card 3 describes the skill balancer — check it against `CLAUDE.md` before shipping.

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

**Seen-state on the account (owner: yes, 2026-11-25).** New coaches often set up on a laptop and run
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

## 8. Owner decisions (2026-11-25)

1. Welcome tour = **4 cards** (fair time, positions, even line-ups, you're still the coach).
2. "Seen" is **remembered on the coach's account** (migration, via staging).
3. **No "Source: The FA" links.**
4. All card copy drafted in the review doc (link at top) — owner reviewing; its "For you to
   decide" checklist must be settled before P1 copy is final.
