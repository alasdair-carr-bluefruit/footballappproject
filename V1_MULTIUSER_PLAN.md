# Level v1.0 — Multi-User Plan (PIN-first, magic-link-ready)

> Working plan for converting Level from single-global-squad to multi-tenant.
> Built to be picked up task-by-task in development. Robust and additive.

> [!IMPORTANT]
> ## ▶ STATUS 2026-07-17 — backend + frontend BUILT on branch `feat/multi-user` (5 commits, NOT pushed)
>
> **Done & green (289 non-e2e + 49 e2e).** Steps 1–9 of §10 complete. Key design
> choice: an **`AUTH_ENABLED` env flag, OFF by default** — dev/tests keep today's
> single-squad behaviour (via `get_current_squad`'s fallback to
> `get_or_create_squad`); prod sets `AUTH_ENABLED=true`.
> - Models `AccountDB`/`InviteDB`/`LoginTokenDB` (`backend/db/models.py`); tables
>   auto-created by `create_all` on boot (no Alembic migration needed).
> - `backend/auth/` — stdlib **HMAC-SHA256** signed session cookie (no itsdangerous
>   dep), sha256 one-time tokens, Resend email sender (dev-stubs to a logged link
>   when no `RESEND_API_KEY`). `backend/settings.py` (lazy env reads).
> - `backend/api/deps.py` — `get_current_squad` pivot (replaces every
>   `get_or_create_squad` call site) + `owned_match/tournament/player` IDOR guards
>   (→404) on every id-path route. `analytics`/`spreadsheet_export` take `squad_id`.
> - Routers: `/api/auth` (redeem, request-link, verify, logout, me),
>   `/api/admin` (invites + accounts list/dump/impersonate, `X-Admin-Key`-gated).
> - **Rolling 30-day session** (`main.py` `rolling_session` middleware refreshes the
>   cookie on activity → 30 days from last use, not sign-in).
> - Frontend: `frontend/auth.js` boot gate (auth-off boots straight through),
>   login/join/verify screens, sign-out, `credentials:"include"`, 401→login
>   (post-boot only). `screens.js` IIFE → exported `bootApp()`. SW cache v32.
> - Tests: `tests/integration/test_auth.py` (isolation/IDOR, invite + magic-link
>   lifecycle, rolling, admin tooling), `tests/e2e/test_auth_e2e.py` (`auth_server`
>   fixture, full browser flow). Testing guide: `docs/multi-user-testing.md`.
>
> **DEPLOY ARTEFACTS DONE (2026-07-17):** `Dockerfile` + `.dockerignore` at repo
> root (python:3.12-slim, `pip install -e ".[api]"`, uvicorn on `$PORT`) and a
> full **`DEPLOY.md`** (Railway + Neon + Resend + domain, env table, smoke test).
> Also added `httpx` to the `[api]` extras — the Resend sender imports it and it
> was previously dev-only (email would have silently failed in prod). **Still to do
> by hand (external accounts, can't script):** create Railway Hobby project, fresh
> Neon DB, Resend account, set env vars, point the domain, run the smoke test.
> Env to set in prod: `AUTH_ENABLED=true`, `SECRET_KEY`, `ADMIN_KEY`,
> `RESEND_API_KEY`, `EMAIL_FROM`, `APP_BASE_URL`, `FRONTEND_ORIGIN`, `DATABASE_URL`
> (leave `COOKIE_SECURE` unset → secure on). **Domain: `keepthingslevel.com`** →
> point at the Railway app; set `FRONTEND_ORIGIN`/`APP_BASE_URL` to it; verify it
> with Resend for a branded From address. See `DEPLOY.md`.
>
> **Safety:** existing live Render instances are unaffected — separate app + fresh
> Neon DB; and even a stray `main` redeploy stays behaviourally identical because
> `AUTH_ENABLED` defaults off. Decision pending: merge branch → `main` before or
> after standing up the new deploy. Restore-of-deleted-data = Neon PITR for v1;
> soft-delete is a documented fast-follow (not built).
>
> _(Original task-ordered plan below is still the reference; §8 deploy is what's left.)_

> [!IMPORTANT]
> **DECISION UPDATE (2026-07-10): magic link FIRST — the PIN stage is skipped entirely.**
> Sign-up/login = email + emailed magic link. The architecture below still applies because
> it was designed to make this additive (§2): `AccountDB` remains the identity and session
> issuance is unchanged. Substitutions when implementing (see DEVELOPMENT_PLAN.md Phase D):
> - `AccountDB.email` becomes **required + unique** (it is the login handle)
> - Drop `pin_hash`, `failed_pin_attempts`, `locked_until`; no `/set-pin` endpoint
> - Add `LoginTokenDB` — hashed one-time login token, ~15-min expiry, single-use
>   (same shape as `InviteDB`); `POST /api/auth/request-link` + `POST /api/auth/verify`
> - Transactional email via Resend or Postmark (free tier); rate-limit `/auth/request-link`
> - Everything else stands: invite-only onboarding, session cookie, `get_current_squad`
>   pivot, `owned_*()` IDOR guards, CORS hardening, Railway + fresh Neon Postgres (§8)

---

## 1. Goals & Non-Goals

**Goal:** One always-on deployment + one shared Postgres DB serving many coaches, each
isolated to their own squad. Solves the spin-down problem (one warm instance for everyone)
and the "10 deployments" problem (one deployment for all).

**This release (v1.0-lean):**
- Invite-only accounts (only coaches you send a link to can create a team)
- PIN-based login, architected so **magic link / email+password drop in later with no identity migration**
- One account → one squad
- Existing Render instances left **completely untouched** as a fallback

**Explicitly deferred (see §11):**
- Magic link / email+password credentials (architecture supports it; not built now)
- Multiple squads per account
- Roles (head coach / assistant), squad sharing between coaches
- Open self-serve signup

---

## 2. The One Rule That Keeps Magic Link Open

**The PIN is never the identity. An `Account` row is the identity.**

Auth is always two separate steps:
1. **Verify a credential** — a PIN now; a magic-link token or password later
2. **Issue a session** — a signed HttpOnly cookie keyed to `account_id`

Consequences we must honour:
- ❌ Never key data by PIN. ❌ Never look up the squad by PIN. ❌ Never store the PIN client-side.
- ✅ Add a **nullable `email`** column to `Account` now, so accounts are addressable by email later with zero migration.
- ✅ Session issuance is credential-agnostic — adding magic link = a new verifier that issues the *same* session against the *same* `Account`.

If we follow this rule, magic link later is purely additive.

---

## 3. Data Model Changes

Current state (verified): `SquadDB`, `PlayerDB`, `MatchDB`, `TournamentDB`, `RotationPlanDB`.
`squad_id` already threads through Player/Match/Tournament — **the isolation column already exists**;
it is simply always "the one squad" today via `get_or_create_squad()` (`repositories.py:14`).

### New table: `AccountDB`
```
AccountDB
  id: int (PK)
  squad_id: int            ← FK → squads.id (1:1 for now; the link is here, not on SquadDB,
                              so multi-squad-per-account later = drop this + add a join table)
  email: str | None        ← nullable NOW (magic-link-ready). Unique when present.
  pin_hash: str | None     ← bcrypt/argon2 hash of the PIN. Nullable so an invited-but-not-yet-
                              activated account can exist.
  display_name: str        ← coach's name, shown in UI (default "")
  status: str              ← "invited" | "active" | "disabled"
  created_at: str          ← ISO datetime
  last_login_at: str | None
  failed_pin_attempts: int (default 0)   ← lockout counter
  locked_until: str | None               ← ISO datetime; brute-force throttle
```

### New table: `InviteDB`
```
InviteDB
  id: int (PK)
  token_hash: str          ← hash of the one-time invite token (never store the raw token)
  account_id: int | None   ← set once redeemed
  created_at: str
  expires_at: str          ← e.g. +14 days
  redeemed_at: str | None
  note: str                ← free text e.g. "Dave – U10s" so you know who you sent it to
```

### Optional (recommended for robustness): `SessionDB`
A server-side session table lets you **revoke** sessions (logout-all, disable account).
Lean alternative: a stateless signed JWT cookie (no table, but no revocation).
**Recommendation:** start with stateless signed cookie for speed; the auth dependency hides
the choice, so swapping to `SessionDB` later touches one module. Decision recorded in §5.

### Migration approach
Follow the existing additive pattern in `database.py:17-34` — `create_all` makes new tables,
then `ALTER TABLE ... ADD COLUMN` in try/except for any column added to existing tables.
**No destructive migrations.** The new DB is a *fresh Neon database* (see §8), so on first
boot `create_all` simply builds everything clean.

---

## 4. Auth & Invite Flow (PIN-first)

### Admin (you) create an invite
- A small admin-only endpoint or one-off script generates an `InviteDB` row + a raw token.
- You get a link: `https://<app>/join?token=<raw-token>`. Store only the hash.
- Gate the admin endpoint behind an `ADMIN_KEY` env var (header or query) — crude but fine for a trial.

### Coach redeems the invite (first visit)
1. Coach opens `/join?token=…`.
2. Frontend posts the token to `POST /api/auth/redeem`.
3. Backend validates (exists, not expired, not redeemed), then:
   - creates an `AccountDB` (status `invited` → `active`) **and** its empty `SquadDB`,
   - prompts the coach to set a **PIN** (and optionally `display_name` + `email` — email
     optional now, but capturing it makes magic-link migration trivial later),
   - issues a session cookie.
4. Marks the invite redeemed. The link is now dead.

### Returning login
- **Same device:** session cookie persists (long expiry, e.g. 30 days) → straight in.
- **New device / expired cookie:** coach needs to re-auth. Because PIN alone is enumerable,
  re-login must be tied to a specific account, not "enter PIN → find squad". Two lean options:
  - **(a) Re-send invite-style link** for new devices (simplest, no enumeration surface).
  - **(b) Account handle + PIN:** coach enters their `email` (or a short account code) **and**
    the PIN. Rate-limited + lockout via `failed_pin_attempts`/`locked_until`.
  - **Recommendation:** ship **(a)** for the trial (zero enumeration risk, least code); add **(b)**
    only if coaches actually hit multi-device friction. Capturing email at redeem makes (b) and
    magic-link the same later flow.

### Session mechanism
- HttpOnly, Secure, SameSite=Lax cookie.
- Stateless signed token (JWT via `python-jose`, or `itsdangerous` signed payload) carrying
  `account_id` + expiry, signed with `SECRET_KEY` env var.
- One FastAPI dependency `get_current_account(session, request) -> AccountDB` reads + verifies
  the cookie. **This is the single chokepoint** — see §5.

---

## 5. Backend Changes

### 5.1 The pivot point: replace `get_or_create_squad()`
Today every router calls `get_or_create_squad(session)` (`repositories.py:14`) and filters by
`squad.id`. This is the **entire isolation seam**. The migration is essentially:

> Replace the implicit "the one squad" with "the squad belonging to the authenticated account."

Add a dependency:
```python
# backend/api/deps.py (new)
def get_current_account(request: Request, session: Session = Depends(get_session)) -> AccountDB:
    token = request.cookies.get("gaffer_session")
    account_id = verify_session_token(token)        # raises 401 if missing/invalid/expired
    account = session.get(AccountDB, account_id)
    if not account or account.status != "active":
        raise HTTPException(401)
    return account

def get_current_squad(account: AccountDB = Depends(get_current_account),
                      session: Session = Depends(get_session)) -> SquadDB:
    return session.get(SquadDB, account.squad_id)
```

Then in **every** router, swap:
```python
squad = get_or_create_squad(session)        # OLD
squad = Depends(get_current_squad)           # NEW (injected param)
```
The rest of each endpoint is unchanged because it already filters by `squad.id`.

**Robustness requirement — defence in depth:** every query that loads a Match/Tournament/Player
by path-param `id` must **also** assert it belongs to `current_squad.id`, returning 404 otherwise.
Today `GET /matches/{id}` trusts the id. In multi-tenant that's an IDOR (one coach reads another's
match). Add a helper:
```python
def owned_match(match_id, squad, session) -> MatchDB:   # 404 if match.squad_id != squad.id
def owned_tournament(...): ...
def owned_player(...): ...
```
Audit checklist of endpoints to harden (all in `backend/api/routers/`):
- matches: `GET/POST/DELETE /{id}`, `/{id}/rotation`, `/blank-rotation`, `/adjust`, `/goals`,
  `/start`, `/unstart`, `/progress`, `/remove-player`, `/reinstate-player`,
  `/stats/player/{id}`
- tournaments: `GET/PUT/DELETE /{id}`, `/set-available-players`, `/set-position-overrides`,
  `/matches`, `/matches/{id}/opponent`, `/players`, `/players/{id}`, `/{id}/stats`
- squad: `/players/{id}` (PUT/DELETE)

### 5.2 New `auth` router
`backend/api/routers/auth.py` (mounted at `/api/auth`):
- `POST /redeem` — body `{token, pin, display_name?, email?}` → creates account+squad, sets cookie
- `POST /login` — (option (b) only) `{email|code, pin}` → sets cookie, with lockout
- `POST /logout` — clears cookie (+ deletes SessionDB row if/when server-side)
- `GET /me` — returns `{display_name, email, squad_id}` for the current account (drives UI state)
- `POST /set-pin` — change PIN while authenticated

### 5.3 Admin invite endpoint
`POST /api/admin/invites` (gated by `ADMIN_KEY`) → `{note}` → returns one-time link.
`GET /api/admin/invites` → list (status, note, redeemed?). Keep it minimal.

### 5.4 Security hardening
- **CORS:** `main.py:20` currently `allow_origins=["*"]` with permissive everything. Tighten to the
  real frontend origin and `allow_credentials=True` (required for cookies; `*` origin is invalid
  with credentials).
- **PIN hashing:** `passlib[bcrypt]` or `argon2-cffi`. Never store raw PIN.
- **Rate limit / lockout:** `failed_pin_attempts` + `locked_until` on the account; optional IP
  throttle on `/auth/*` (e.g. `slowapi`).
- **Secrets:** `SECRET_KEY`, `ADMIN_KEY` as env vars. Fail fast on boot if unset in prod.
- **Invite tokens & PINs:** high-entropy invite tokens (`secrets.token_urlsafe(32)`); store only hashes.

### 5.5 Dependencies to add
`passlib[bcrypt]` (or `argon2-cffi`), `python-jose[cryptography]` *or* `itsdangerous`,
optionally `slowapi`. Add to `pyproject.toml`.

---

## 6. Frontend Changes

Current: `BASE = "/api"`, only `Content-Type` header, no identity (`api.js`). localStorage holds
UI flags only (`gaffer_onboarded`, etc.).

- **api.js:** add `credentials: "include"` to every fetch so the session cookie rides along.
  Add a 401 handler → redirect to the login/join screen.
- **New screens:**
  - `/join` redeem screen (token from URL → set PIN + name + optional email).
  - Login screen (option (a): "ask your coordinator for a fresh link"; or option (b): email/code + PIN).
  - A small account menu (display name, logout, change PIN).
- **Boot flow:** on load, call `GET /api/auth/me`. If 401 → show login/join. If ok → load app as today.
- **Tutorial flag:** `gaffer_onboarded` is per-device localStorage (known issue in roadmap memory).
  With accounts, onboarding state can move server-side (a `seen_tutorial` flag on `AccountDB`) so it
  follows the coach across devices. Optional polish; note it.
- **No change to the rotation/pitch/match-day UI** — it already operates on whatever squad the API returns.

---

## 7. Testing Plan

- **Unit:** session token sign/verify, PIN hash/verify, invite token lifecycle, lockout logic.
- **Integration (extends `tests/integration/`):**
  - redeem invite → account+squad created, cookie set
  - unauthenticated request → 401 on every protected route
  - **isolation/IDOR:** account A cannot read/modify account B's match/tournament/player (expect 404)
  - expired/invalid/reused invite → rejected
  - lockout after N bad PINs
- **BDD (`tests/bdd/features/`):** `multi_user.feature` — "coach redeems invite", "two coaches keep
  separate squads", "logged-out coach is blocked".
- Existing ~105 tests: most call endpoints that now require auth → add a shared authenticated-client
  fixture that redeems an invite once and reuses the cookie. Budget time for this fixture refactor.

---

## 8. Deployment & Data Strategy

- **Leave the 3–4 existing Render instances + their Neon DBs entirely as-is.** They remain the
  current live fallback. No migration of their data in this plan (your call: "leave them as they are").
- **New deployment** = the multi-user app, **new fresh Neon database** (new `DATABASE_URL`).
  Starts empty; `create_db_and_tables()` builds the new schema clean on first boot.
- **Host:** the goal is *one always-on instance, no spin-down, no boot lag*. There is no longer a
  truly-free low-effort PaaS for this (Fly.io retired its free allowance — now pay-as-you-go,
  ~$2/mo per machine after a one-time trial credit; Render free spins down). Realistic options:
  | Option | Cost | Notes |
  |---|---|---|
  | **Koyeb free tier** | £0 | One always-on web service on the free plan — closest to "free + always on". Verify current limits before committing. |
  | **Railway Hobby** | ~$5/mo (incl. $5 usage) | Best DX, GitHub auto-deploy, no spin-down. Easiest migration from Render. |
  | **Fly.io PAYG** | ~$2/mo | Cheap but no real free tier now; Docker-based. |
  | **Render Starter** | ~$7/mo | Stay put, just upgrade off free to stop spin-down. Zero migration. |
  | **Oracle Cloud Always-Free VM** | £0 forever | Truly free, never sleeps, but real ops overhead (SSH/nginx/systemd) — not PaaS. |
  Needs a ~10-line `Dockerfile` (FastAPI + uvicorn) for Fly/Koyeb/Railway.
  **DECISION: Railway Hobby (~$5/mo).** Always-on (no spin-down), best DX, GitHub auto-deploy,
  near-identical workflow to Render. Replaces the current ~$25/mo Render spend with ~$5/mo for one
  warm shared instance serving all coaches. Keep Neon as the DB (Railway connects via `DATABASE_URL`).
- **Rollout:** stand up new app → smoke test → generate invites → send to a couple of coaches →
  widen. Old instances stay up until you decide to retire them.
- **New env vars:** `DATABASE_URL` (new Neon), `SECRET_KEY`, `ADMIN_KEY`, allowed CORS origin.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| IDOR — coach reads another's data via guessable `id` | `owned_*()` ownership checks on every id-path route (§5.1); isolation tests (§7) |
| PIN brute force | lockout counter + high-entropy account binding; prefer fresh-link re-login (option a) |
| Cookie not sent cross-origin | serve frontend same-origin as API (already the case via StaticFiles mount), `credentials:"include"`, correct CORS+SameSite |
| Existing 105 tests break on auth | shared authenticated-client fixture |
| Lock-in to stateless sessions | auth hidden behind one dependency; `SessionDB` swap is localised |
| Secret misconfig in prod | fail-fast on missing `SECRET_KEY`/`ADMIN_KEY` at boot |

---

## 10. Task Breakdown (suggested order for development)

1. **Models:** add `AccountDB`, `InviteDB` (+ optional `SessionDB`) to `db/models.py`; additive migrations in `database.py`.
2. **Auth core:** PIN hashing, session token sign/verify, invite token gen/verify (`backend/auth/` module) + unit tests.
3. **Deps:** `get_current_account` / `get_current_squad` / `owned_*` helpers in `api/deps.py`.
4. **Auth router:** `/api/auth/redeem`, `/me`, `/logout`, `/set-pin` (+ `/login` if option b).
5. **Admin router:** `/api/admin/invites` gated by `ADMIN_KEY`.
6. **Pivot routers:** replace `get_or_create_squad()` with injected `current_squad`; add `owned_*` checks across matches/tournaments/squad routers.
7. **Harden:** tighten CORS, add lockout, fail-fast on missing secrets.
8. **Frontend:** `credentials:"include"`, 401 handling, `/join` redeem screen, login screen, account menu, `GET /me` boot flow.
9. **Tests:** auth fixture refactor for existing suite; new isolation/IDOR + invite + BDD tests.
10. **Deploy:** `Dockerfile`, new Neon DB, new env vars, Fly.io/Railway; smoke test; generate first invites.

Each step is independently shippable to a branch and testable. Steps 1–6 are backend-only and can
be fully tested before any frontend work.

---

## 11. Future Extensions (design hooks already in place)

- **Magic link / email+password:** add a new credential verifier issuing the same session against
  the same `AccountDB`. `email` column already exists. No identity migration. (§2)
- **Multiple squads per account:** the `account.squad_id` link lives on `AccountDB`, not `SquadDB`.
  Replace it with an `AccountSquad` join table (`account_id`, `squad_id`, `role`) + a squad-picker
  in the UI. Data model already squad-scoped, so no per-row migration.
- **Roles (head coach / assistant) & sharing:** the `role` column on the future `AccountSquad` join
  table carries this. Authorization checks read `role` instead of plain ownership.
- **Open self-serve signup:** add a public `/signup` that creates an invite-equivalent; layer on
  email verification + abuse protection.
- **Server-side onboarding state:** move `gaffer_onboarded` to a flag on `AccountDB` so the tutorial
  follows the coach across devices (fixes the per-device localStorage roadmap item).
