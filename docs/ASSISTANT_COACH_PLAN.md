# Assistant coach mode (T3.2) — implementation plan

> Status: **Phase 1 BUILT on `staging` (2026-09-28), not yet deployed.** Phases 2–3 planned.
> Decisions locked with the owner 2026-09-28.
> A team has **one head coach** and any number of **assistants**. Roles are per team,
> so one account can be head coach of its own team and an assistant on someone else's.
> Delivered in three phases: read-only → run matchday → comment & propose.

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

## Phase 2 — assistant runs matchday

### One controlling device
- New fields on `MatchDB` (and the tournament-match equivalent):
  `controller_account_id`, `controller_device_id`, `controller_since`.
- **Device id:** a random id generated once per device and kept in `localStorage`
  (`gaffer_device_id`, keeping the `gaffer_` prefix convention), sent as a header on matchday calls.
- **Start Match** claims control. Every matchday write (`advance`, goals, timer, remove/reinstate,
  full time) requires the caller's `(account, device)` to match the controller, or it returns 409:
  - different account → *"This match was started on [display_name]'s device."* + **Take control**
  - same account, other device → *"This match was started on your other device."* + **Take control**
- Everyone else sees the match **live, read-only**: poll `GET` every ~10–15s (no websockets needed yet).
- **Take control (locked 2026-09-28):** anyone with `run_matchday` (the head coach **or any
  assistant**) can take control after an in-app confirm, so a dead phone never locks the team out.
  `POST /matches/{id}/take-control` rewrites the controller fields. The old device's next matchday
  write gets 409 *"[Name] took control of this match"* and drops to live read-only view.

### Timer must move to the server
The match clock is currently **per-device `localStorage`** (`pitch.js` `timerKey()` / `writeTimer`).
Viewers and a device taking over would show the wrong time. Persist
`timer_started_at`, `timer_paused_at` and `timer_paused_accum_ms` on the match, keeping localStorage
as a cache only. **This is a prerequisite for phase 2**, and useful on its own (the clock survives
a device switch).

### Capabilities
Add `run_matchday` to the assistant set. The phase-1 route guard means each matchday route just
switches from `require("edit_plan")` to `require("run_matchday")`.

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
