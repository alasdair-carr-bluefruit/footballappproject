# Level — Multi-Team Plan (one coach, several squads)

> **Status:** planned (Forward Roadmap **T1.1**). Real user demand — a live coach has
> already asked. Depends on nothing new; builds on the shipped multi-user layer
> (`feat/multi-user`).
>
> **Goal:** let one authenticated account own and switch between multiple squads
> ("teams"), each fully isolated (its own players, matches, tournaments, name, badge).
>
> **Non-goals (deliberately deferred):** sharing a squad between accounts / co-coach
> roles (that's T3.2 — but this plan lays its foundation), and any billing/limits
> beyond a soft anti-abuse cap.

---

## 1. Current state (what we're building on)

- **1 account ↔ 1 squad.** `AccountDB.squad_id` is a NOT-NULL FK to `squads.id`
  (`backend/db/models.py`). Created together in `POST /api/auth/redeem`.
- **Single isolation seam.** `get_current_squad()` (`backend/api/deps.py`) resolves
  "the squad this request operates on" — every router depends on it, and the
  `owned_match/tournament/player` guards assert `row.squad_id == squad.id` (IDOR
  defence). **This is the only place squad resolution happens** — the whole feature
  hinges on this one function.
- **Squad-scoped data already keyed by `squad_id`.** `players`, `matches`,
  `tournaments` all carry `squad_id`. Multi-team does **not** touch these tables — a
  second squad is just more rows with a different `squad_id`.
- **Session is credential-agnostic** (`backend/auth/session.py`): token = signed
  `"<account_id>.<issued>"`. We must **not** put squad state in the token.
- **Auth-off fallback** (dev/tests): `get_current_squad` returns the single default
  squad via `get_or_create_squad`. Must stay single-squad and unchanged.

---

## 2. Design decisions

1. **Membership join table, not just an owner column.** Add `SquadMembershipDB
   (account_id, squad_id, role)`. A simple `SquadDB.owner_account_id` would be less
   code, but the join table is the exact structure co-coach (T3.2) needs, so we pay for
   it once. Role is `owner` for every row today; `coach`/`viewer` land with T3.2.
2. **Active squad lives on the account, server-side.** Add
   `AccountDB.active_squad_id` (nullable). Server-side (like `seen_tutorial`) so the
   selection follows the coach across devices, and so `session.py` stays untouched.
3. **Keep `AccountDB.squad_id` as the legacy "home" squad for now.** Dropping a
   NOT-NULL column is a heavier migration; leave it, stop using it for *resolution*,
   and remove it in a later cleanup once nothing reads it. Backfill sets
   `active_squad_id = squad_id` so behaviour is identical on day one.
4. **Resolution asserts membership.** `get_current_squad` returns the *active* squad
   only after confirming a membership row exists for `(account, active_squad_id)` —
   this is what preserves the IDOR guarantee across teams.

---

## 3. Data model changes (`backend/db/models.py`)

```python
class SquadMembershipDB(SQLModel, table=True):
    __tablename__ = "squad_memberships"
    __table_args__ = (UniqueConstraint("account_id", "squad_id", name="uq_member_account_squad"),)
    id: int | None = Field(default=None, primary_key=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    squad_id: int = Field(foreign_key="squads.id", index=True)
    role: str = "owner"          # owner | coach | viewer (only owner used today)
    created_at: str = ""         # ISO datetime
```

Add to `AccountDB`:
```python
    active_squad_id: int | None = None   # currently-selected squad; None → fall back to squad_id
```

Everything else on `SquadDB`/`PlayerDB`/`MatchDB`/`TournamentDB` is unchanged — they
are already squad-scoped.

---

## 4. Backend changes

### 4.1 Resolution — `deps.py` (the one seam)
```python
def get_current_squad(request, session=Depends(get_session)) -> SquadDB:
    if not auth_enabled():
        return get_or_create_squad(session)          # dev/tests: unchanged
    account = _account_from_request(request, session)
    if account is None:
        raise HTTPException(401, "Not authenticated")
    squad_id = account.active_squad_id or account.squad_id
    membership = session.exec(select(SquadMembershipDB).where(
        SquadMembershipDB.account_id == account.id,
        SquadMembershipDB.squad_id == squad_id,
    )).first()
    if membership is None:
        raise HTTPException(403, "Not a member of this squad")
    squad = session.get(SquadDB, squad_id)
    if squad is None:
        raise HTTPException(401, "Account has no squad")
    return squad
```
No other router changes — they all go through this.

### 4.2 New endpoints — `backend/api/routers/squad.py`
- `GET /api/squad/list` → squads the account is a member of:
  `[{squad_id, name, team_name, team_logo, role, is_active}]`. Drives the switcher.
- `POST /api/squad/create` `{name, team_name?}` → create `SquadDB` + membership
  (`owner`) + set `active_squad_id` to it → return the new squad. (Factor out the
  squad-creation lines from `auth.redeem` into a `create_squad_for(account, …)` helper
  and reuse in both.)
- `POST /api/squad/switch` `{squad_id}` → assert membership → set
  `account.active_squad_id` → return the now-active squad. **This is an IDOR-sensitive
  route** — a non-member `squad_id` must 404/403, never switch.
- `DELETE /api/squad/{squad_id}` (**folds in Tier 1.4 "clear squad & data"**) → assert
  `owner` membership → delete players, matches (+ rotation/slot/goal/availability/
  removed rows), tournaments, membership, then the squad. If it was active, switch to
  another owned squad; **block deleting the last remaining squad** (or replace it with a
  fresh empty one) so an account is never squad-less.

### 4.3 Update `redeem` + `/me`
- `auth.redeem`: after creating the squad + account, also create the `owner` membership
  and set `active_squad_id = squad.id`.
- `auth.me` / `_account_public`: return the **active** squad plus a `squads` array (id,
  name, role, is_active) so the frontend can render the switcher from the `/me` probe it
  already does on boot.

---

## 5. Migration + backfill (Alembic — per repo convention)

New schema goes through Alembic (`_run_migrations`), **not** the legacy additive bridge.
One revision:
1. `create_table("squad_memberships", …)` with the unique constraint + indexes.
2. `add_column("accounts", Column("active_squad_id", Integer, nullable=True))`.
3. **Backfill** (data migration — `create_all` will NOT do this): for every existing
   `accounts` row, insert `SquadMembershipDB(account_id, squad_id, role="owner")` and set
   `active_squad_id = squad_id`.
4. `downgrade`: drop the column + table.

Test the backfill explicitly (§7) — it's the risky part.

---

## 6. Frontend changes

- **Team switcher** in the account menu (near `btn-signout`, `frontend/auth.js`): a
  dropdown listing teams from `/me`'s `squads` (or `/api/squad/list`), current one
  ticked, plus **"+ Create new team"**. Selecting one → `POST /api/squad/switch` →
  reset + refetch state.
- **Show the active team name** in the header/landing so it's always clear which team
  is in context.
- **State reset on switch (important).** `state` is a shared mutable object
  (`frontend/state.js`) holding players/matches/tournaments for the current squad. On
  switch, clear squad-scoped state and refetch (mirror the boot path) so no stale
  team-A data leaks into team-B screens. Reset **both** season and tournament flows.
- **Create-team flow:** reuse the existing team-name/badge form
  (`screens.js` tutorial/squad form) → `POST /api/squad/create` → land on the new
  empty squad's home.
- **`api.js`:** add `listSquads`, `createSquad`, `switchSquad`, `deleteSquad` wrappers.
- Existing single-team coaches: unaffected — they just see one team + the option to add
  another.

---

## 7. Tests

- **Isolation / IDOR (critical):** account A cannot `switch` to or `delete` account B's
  squad (non-member `squad_id` → 403/404); after switching, A only ever reads its
  active squad's players/matches.
- **Multi-squad happy path:** create a 2nd team → switch → data scoped correctly →
  switch back → team-A data intact.
- **Backfill:** seed a pre-migration account (squad_id set, no membership) → run
  migration → exactly one `owner` membership + `active_squad_id == squad_id`.
- **Delete:** deleting a squad removes all its scoped rows; deleting the active squad
  re-points `active_squad_id`; deleting the last squad is blocked/handled.
- **Auth-off fallback unchanged:** single default squad, no switcher behaviour.
- **BDD** (`tests/bdd/features/`): "a coach manages two teams" scenario.
- Extend the existing authenticated-client fixture to seed a second squad + membership.

---

## 8. Edge cases & decisions to confirm

- **Soft cap** on teams per account (e.g. 20) as light anti-abuse? *Recommend yes.*
- **Delete-the-last-squad** behaviour: block, or replace with a fresh empty squad?
  *Recommend block with a clear message* (account must always have ≥1 squad).
- **Guest players** are tournament-scoped (`source_tournament_id`) — unaffected.
- **`seen_tutorial`** is per-account (not per-squad) — a coach adding a 2nd team should
  not re-see onboarding. Fine as-is; the create-team flow is not the tutorial.
- **Team identity** (name, badge) is per-`SquadDB` — each team keeps its own. Good.

---

## 9. Rollout

Fully additive + backward-compatible. Deploy the migration → existing coaches see their
single team exactly as before, with a new "Create new team" affordance. Low risk; no
data reshape of the big tables.

---

## 10. Implementation order (checklist)

1. Models: `SquadMembershipDB` + `AccountDB.active_squad_id`.
2. Alembic revision: table + column + **backfill** (+ downgrade). Test backfill.
3. `deps.get_current_squad`: active-squad resolution + membership assertion.
4. Extract `create_squad_for(account)` helper; wire into `auth.redeem` (+ membership,
   active_squad_id).
5. Endpoints: `list`, `create`, `switch`, `delete` (delete = also T1.4).
6. `/me` + `_account_public`: return active squad + `squads[]`.
7. `api.js` wrappers + account-menu team switcher + active-team-name display.
8. State reset-on-switch (season + tournament).
9. Tests: isolation/IDOR, multi-squad, backfill, delete, BDD.
10. Deploy migration → verify existing coach unchanged → announce to the requesting user.

---

## 11. What this unblocks

The `SquadMembershipDB` table + role column is exactly the substrate **co-coach plan
proposals (T3.2)** needs: inviting another account to a squad becomes a new membership
row with role `coach`, and `get_current_squad`'s membership check already gates access.
No identity migration later — same additive pattern as magic-link was to invites.
