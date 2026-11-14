# Assistant coach mode (T3.2) — implementation plan

> Status: **Phase 1 BUILT on `staging` (2026-09-28), not yet deployed.** Phases 2–3 planned.
> **Phase 1.5 (assistant-authored plans, hand-over, Reviewed ✓, emails) and Phase 2 (one
> controlling device + server clock) BUILT on `staging` (2026-11-14)** — see below. Phase 3 planned.
> Decisions locked with the owner 2026-09-28.
> A team has **one head coach** and any number of **assistants**. Roles are per team,
> so one account can be head coach of its own team and an assistant on someone else's.
> Delivered in phases: read-only → assistant plans → one controlling device → comment & propose.

## Decisions (locked)
- **Roles live on a membership, not the account.** `SquadMembershipDB(squad_id, account_id, role)`.
  Exactly **one `head`** per team; any number of `assistant`s.
- **Head-coach transfer:** allowed later (not phase 1).
- **Skill ratings are hidden from assistants.** Per-slot pooled `skill_total` (the ⚡ chips,
  plan grid, share image) stays visible. Squad management is hidden entirely for now.
  Revisit if assistants ever get an "add player → head coach approves" workflow.
- **Draft plans are visible** to assistants (no "published" state needed).
- **An assistant invite admits a brand-new person to the app.** Once in, they can create
  their own team like any coach (becoming `head` of it).
- **Deleting / clearing a team** simply ends assistants' access (memberships go with it).
- **Matchday (phase 2): one controlling device per match.** Anyone else who opens it is told
  *"This match was started on [Name]'s device"* and offered **Take control**. The head coach and
  **any assistant** can take control (so a dead phone never locks the team out mid-match).

## Why the design looks like this
- `owned_squad` in `backend/api/deps.py` is already the single access check for teams, and
  `get_current_squad` is the single isolation seam for everything else. Swapping both to a
  membership lookup changes access in one place.
- **Capabilities, not role checks.** Routes require a capability; roles map to capability sets.
  Phases 2 and 3 are then mostly "add a capability to the assistant set", and a later
  per-assistant toggle ("Sam can run matchday") needs no new plumbing.

| Capability | Head | Assistant P1 | Assistant P2 | Assistant P3 |
|---|---|---|---|---|
| `view` — stats, history, reports, plans (skill ratings redacted) | ✓ | ✓ | ✓ | ✓ |
| `run_matchday` — start, advance, goals, timer, remove/reinstate | ✓ | – | ✓ | ✓ |
| `comment`, `propose` | ✓ | – | – | ✓ |
| `edit_plan` — create match, generate, tinker, recalc, delete | ✓ | – | – | – |
| `manage_squad` — players, guests, skill ratings | ✓ | – | – | – |
| `manage_team` — name/logo, invite/revoke assistants, clear/delete | ✓ | – | – | – |

---

## Phase 1 — read-only assistants

> **As built (differences from the original sketch below):**
> - Assistant invites are **shareable one-time links** (`?assist=`, like invite-a-friend —
>   WhatsApp-friendly), not emailed. Settings → *Assistant coaches* mints them; the landing
>   "Add your assistant coach" card (was a "coming soon" teaser) opens that section.
> - An account that loses its **last** team (removed, left, or team deleted) gets a fresh empty
>   team it heads (`memberships.repoint_active_squad`), so `AccountDB.squad_id` always resolves.
>   `get_squad_access` also re-points defensively if the active team is no longer accessible.
> - A signed-out **existing** coach who opens an assist link: the join form gets a 409, parks the
>   token in `localStorage` (`gaffer_pending_assist`), sends them to sign in, and the confirm
>   screen (`#screen-assist-join`) appears after the magic link.
> - `/auth/account/clear-data` is head-only; `/teams/{id}` delete needs head of that team.
> - Code: `backend/db/memberships.py`, `backend/api/deps.py` (`SquadAccess`, `require`),
>   `backend/api/routers/teams.py` (assistant endpoints), revision `e4b8a1c6d2f9`.
>   Frontend: `can()` / `setRole()` in `state.js`, `.head-only` / `.assistant-only` classes.
> - Tests: `tests/integration/test_assistants.py` (incl. the route-coverage guard + backfill),
>   `tests/e2e/test_assistant_e2e.py` (season ⇄ tournament parity).

### Data model (one Alembic revision)
```
SquadMembershipDB  (__tablename__ = "squad_memberships")
  id, squad_id (index), account_id (index)
  role: "head" | "assistant"
  created_at, invited_by_account_id: int | None
  UniqueConstraint(squad_id, account_id)
```
- **Backfill:** one `head` row per `SquadDB` with a non-null `account_id`.
- **Keep `SquadDB.account_id`** during the transition as the denormalised head pointer, and write
  it alongside the membership. Reads move to the membership table. Drop the column in a later
  cleanup revision.
- `AccountDB.squad_id` stays the **active team** pointer, which may now be a team the account assists.
- Test the backfill explicitly against a copy of prod-shaped data: every squad has exactly one `head`,
  and every account's active squad has a membership row.

### Assistant invites
- Reuse `InviteDB`: add `squad_id: int | None` and `role: str = ""`. A plain invite (today's) has no
  squad. An assistant invite carries the squad and `role="assistant"`.
- **Head coach → Settings → "Assistants":** enter an email; an invite link is emailed via Resend.
  The list shows current assistants with **Remove**.
- **Redeem:**
  - Signed-in existing account → add membership, switch the active team to it.
  - New person → the normal `/join` magic-link signup, **but no team is created**. They land on
    the assistant team. The empty-state then offers "Add your own team".
- An assistant can **Leave team** from Settings.
- Invite-only onboarding is unaffected: an assistant invite is simply another valid invite.

### Access layer (`backend/api/deps.py`)
- Replace `get_current_squad` with a context dependency returning `(squad, membership)`.
  Auth off (dev/tests) → default squad + synthetic `head` membership, so today's tests are unchanged.
- `require(cap)` dependency factory → 403 `"Assistants can't do that"` when the role lacks `cap`.
- `owned_squad` → membership lookup (any role). It is used by the teams router (`list`/`activate`).
  Delete stays head-only via `require("manage_team")`.
- **Deny-by-default guard test:** walk `app.routes`. Every non-GET route under the squad-scoped
  routers must declare a `require(...)` dependency, or the test fails. This is the real safety net:
  about 34 write routes today, and any new one is caught automatically.

### Redacting skill ratings (server-side, not just UI)
Ratings currently leave the API in `squad.py` (player list) and `tournaments.py` (squad / guests /
availability rows, e.g. lines ~267, ~609). For an assistant:
- Omit `skill_rating` from player payloads (send `null`). Squad-management endpoints are head-only anyway.
- **Slot `skill_total` stays**, since it is computed server-side, so the chips, plan grid and share
  image keep working.
- Frontend: hide the `★n` badges in the tournament availability lists (`tournament.js` ~227/277/592)
  when the rating is null. Hiding the UI alone is not enough, because the data would still be in the response.

### Frontend read-only mode
- `state.role` from `/me` (the active membership), and a `can(cap)` helper mirroring the server map.
- Header team pill: lists every membership with an **"Assistant"** badge on assisted teams.
- On an assisted team, hide: New match / New tournament, generate, tinker, recalculate, Start Match,
  goals, remove/reinstate, squad management, team settings, clear/delete.
- Keep: season stats, match history, Full Time cards / reports, the upcoming-match plan on the pitch +
  the review table, and the share image.
- **Parity:** season and tournament flows get the same gating in the same change
  (`loadHome` ⇄ `loadTournamentHome`, `openMatch` ⇄ `loadTournamentLobby`).
- Bump `CACHE` in `sw.js`; purge Cloudflare after deploy.

### Tests
- **Unit / integration:** the backfill; invite → redeem (existing and new account); leave and remove;
  an assistant gets 200 on every GET and 403 on every write (parametrised over the route table);
  an assistant on team A gets 404 on team B's ids (IDOR); `skill_rating` is absent for an assistant
  and present for the head; the route-coverage guard.
- **e2e (parametrised `["season","tournament"]`):** an assistant opens an upcoming match, sees the
  plan, and finds no tinker / Start / goal controls.

### Release
Touches migrations, `backend/db/**`, `backend/api/**`, `deps.py` and auth → **via `staging` first**
(`docs/STAGING.md`).

---

## Phase 1.5 — assistant-authored plans (built 2026-11-14)

Pulled forward because a head coach asked an assistant to do the squad for a match.

- **Rule:** an assistant can **create** a match or tournament, and then **edit, tinker and
  run matchday on the ones they created**. The head coach can do all of that on every plan.
  Other assistants see an assistant's plan read-only, exactly like the head coach's.
- **Data:** `MatchDB.created_by_account_id` / `TournamentDB.created_by_account_id` (revision
  `a1c5e9d3b7f2`; nullable, no backfill — `NULL` = head-coach only = the old behaviour).
  A tournament's matches inherit the tournament's creator, whoever adds them.
- **Access:** new capability `author_plan` (head + assistant). Plan write routes depend on
  `plan_access`; every one that addresses an existing row ALSO depends on `editable_match` /
  `editable_tournament` (404 not your squad, 403 not your plan). Two guard tests: plan routes
  are the only ones an assistant's role admits, and every such route with a path id has the
  per-row guard. Guests (`manage_squad`) and squad/team routes stay head-only.
- **Payloads:** matches and tournaments carry `can_edit`, `created_by_name`, `created_by_me`.
  The name is only sent when the creator isn't the head coach.
- **Frontend:** `.editor-only` + `body.plan-readonly` (per open plan, `setPlanEditable()` in
  `state.js`) replaces `.head-only` on plan controls; `can("edit_plan" | "run_matchday")` now
  answers for the open plan. Fixtures / tournament lists show a **"Plan by Sam"** chip.
- **Hand-over (built 2026-11-14):** the head coach can hand one of their own planned
  matches — or a whole tournament — to an assistant, and take it back: `PUT
  /matches/{id}/owner`, `PUT /tournaments/{id}/owner` (head-only). So read
  `created_by_account_id` as **plan owner**. On the lists the head coach's chip is a button
  ("Hand over" / "Plan by Sam") that opens the picker (`frontend/plan-owner.js`).
- **Reviewed ✓ (built 2026-11-14), instead of an Accept gate:** `reviewed_at` on matches and
  tournaments; `POST …/review` (head-only). Shown on the chip and on the review screen. It is
  a mark, not a gate — an unreviewed plan can always be started — and it clears itself when
  the assistant changes the plan afterwards (`matches.plan_changed`). Tournament matches
  share their tournament's mark (the "Review all plans" page).
- **Emails (built 2026-11-14):** the head coach is emailed the first time an assistant makes
  a plan (first rotation for a season match; first batch of matches for a tournament), and
  an assistant is emailed when a plan is handed to them. `services/notifications.py`,
  queued as background tasks, opt-out via `AccountDB.notify_plans` (Settings → Account).
- **Temporary players (built 2026-11-14):** whoever runs a tournament can add/remove its
  guests. An assistant's guests get the default rating (3) and the rating is never sent back.

---

## Phase 2 — one controlling device + server clock (built 2026-11-14)

Needed as soon as phase 1.5 let two people run the same match. Code: `services/matchday.py`,
`deps.controlled_match`, revision `b6d2f8a4c1e7`; frontend in `pitch.js` ("One device runs a
live match") and `api.js` (`deviceId`, `setLostControlHandler`).

- **Who can run a match is unchanged** — the head coach, or the assistant who owns the plan
  (*not* "any assistant", as first sketched: that would undo phase 1.5's rule).
- **Device id:** random, per browser, in `localStorage` (`gaffer_device_id`), sent as
  `X-Device-Id` on every request.
- **Start Match claims control** (`controller_account_id` / `controller_device_id` /
  `controller_since` on `MatchDB`). While the match is live, every write to it
  (`controlled_match`: progress, goals, timer, adjust, remove/reinstate, unstart, …) from any
  other device gets **409 `{code: "not_controller", controller_name, same_account}`**.
- **Everyone else watches:** `GET /matches/{id}` carries `match.controller` (`is_me`,
  `same_account`, `name`); the pitch goes read-only, shows "● Sam is running this match" and
  re-fetches every 8s (no websockets). Goals are now saved as they happen, so viewers see them.
- **Take control:** `POST /matches/{id}/take-control`, after a confirm. The old device finds
  out on its next save (the 409) and drops to the watching view; it can take control back.
- **Full time / return to plan release control**; a finished match's report is editable from
  any device allowed to.
- **Compatibility rule (important):** control is only enforced between requests that carry a
  device id. A request without one (a stale cached frontend, a script) is never refused, and
  a live match nobody controls is claimed by the first device-carrying write. A deploy can
  therefore never strand a coach mid-match.
- **Server clock:** `timer_running` / `timer_elapsed_ms` / `timer_anchor_at`, stored as
  "elapsed at a server instant" so devices never compare wall clocks. Start sets it; the
  controlling device reports pause / resume / per-period reset via `PUT /matches/{id}/timer`.
  localStorage remains the running device's working copy (keeps ticking offline, re-pushed
  on reconnect); viewers and a device taking over adopt the server's.
- **Not built:** per-assistant "can run matchday" toggles; live push (it polls).

---

## Phase 3 — comments & proposals

- **Comments:** `PlanCommentDB(match_id, author_account_id, slot_index?, player_id?, body, created_at,
  resolved_at?)`, e.g. "Jake's been on the bench a lot". Shown on the review screen, where the head
  coach can resolve them.
- **Proposals:** `PlanProposalDB(match_id, proposed_by, plan_json, base_plan_version, status:
  pending|accepted|rejected, note)`.
  - The assistant generates or tinkers in a **proposal draft** (the same tinker UI, saving to a
    proposal instead of the plan) and taps "Propose to head coach".
  - The head coach sees a current-vs-proposed diff, then **Accept** (replaces the plan), **Tinker**
    (opens it in tinker mode, then accept), or **Reject** with a note.
  - If the live plan changed since `base_plan_version`, warn before accepting.
- Email notifications via Resend (new proposal / accepted / rejected), with a per-account opt-out.
- Add `comment` and `propose` to the assistant capability set.

---

## Later / deferred
- Head-coach transfer (`manage_team`: pick an assistant → swap roles atomically; still exactly one head).
- Per-assistant capability toggles.
- An assistant "add player" request that the head coach approves (would revisit skill-rating visibility).
