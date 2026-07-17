# Level — Multi-User Deploy Guide

How to stand up the always-on, multi-tenant deployment of Level on **Railway
Hobby** with a fresh **Neon** Postgres and **Resend** for magic-link email.
Domain: **keepthingslevel.com**.

> This deploy is fully isolated from the existing single-user Render instances.
> It's a **new app** on a **new, empty database**. Nothing here touches or
> migrates the old instances — they stay up as a fallback until you retire them.

The whole auth/isolation layer sits behind one flag: **`AUTH_ENABLED=true`**.
With it unset the app behaves exactly as the single-squad app always has, which
is why a stray `main` redeploy anywhere else is behaviourally identical.

---

## 0. What you're deploying

- **Runtime:** `Dockerfile` at repo root → `python:3.12-slim`, `pip install -e ".[api]"`,
  runs `uvicorn main:app` on `$PORT`.
- **App:** FastAPI serves the API *and* the static frontend/assets same-origin
  (`main.py` StaticFiles mounts). No separate frontend host — so no cross-origin
  cookie problems by default.
- **DB:** Postgres via `DATABASE_URL`. Schema is created on first boot by
  `create_db_and_tables()` (`create_all` + Alembic upgrade). No manual migration step.
- **Email:** Resend via `backend/auth/email.py`. With no `RESEND_API_KEY` the
  magic link is only logged (dev-stub) — so email is required for real prod use.

---

## 1. Neon — fresh Postgres database

1. Create a Neon account / project (or a new database inside an existing project).
   **Make it a brand-new database** — do not reuse an old single-user DB.
2. Copy the **pooled** connection string. It looks like:
   ```
   postgresql://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/DBNAME?sslmode=require
   ```
   - Use the **`-pooler`** host (pgBouncer) — a single always-on instance under
     concurrent coaches should go through the pooler.
   - Keep `?sslmode=require`.
   - The scheme must be `postgresql://` (SQLAlchemy 2.x rejects the legacy
     `postgres://`). Neon already gives you `postgresql://`; if you ever paste one
     that starts `postgres://`, change it to `postgresql://`.
3. Save it — this becomes `DATABASE_URL` in Railway.

---

## 2. Resend — transactional email

1. Create a Resend account and an **API key** → this is `RESEND_API_KEY`.
2. **From address:**
   - Quick start: leave `EMAIL_FROM` unset — it defaults to
     `Level <onboarding@resend.dev>`, Resend's shared test sender. Fine for the
     first couple of invites, but deliverability is poor and it can only send to
     your own verified address on the free tier.
   - Proper setup: **verify `keepthingslevel.com` as a Resend domain** (add the
     DKIM/SPF/return-path DNS records Resend shows you), then set
     `EMAIL_FROM="Level <noreply@keepthingslevel.com>"`.
3. Free tier is plenty for invite-only onboarding (100 emails/day).

---

## 3. Railway — the app

1. New Railway project → **Deploy from GitHub repo** → pick this repo,
   branch `feat/multi-user` (switch to `main` once you merge — see §7).
2. Railway auto-detects the `Dockerfile` and builds from it. No build/start
   command config needed — the image's `CMD` runs uvicorn on Railway's injected
   `$PORT`.
3. Set the environment variables (§4).
4. First deploy: watch logs for `create_db_and_tables()` succeeding and uvicorn
   binding. If `AUTH_ENABLED=true` but `SECRET_KEY`/`ADMIN_KEY` are missing, the
   app **fails fast on boot** with a clear error (by design) — set them and redeploy.

---

## 4. Environment variables (set in Railway)

| Var | Value | Notes |
|---|---|---|
| `AUTH_ENABLED` | `true` | **The switch.** Off → single-squad legacy mode. |
| `SECRET_KEY` | *(random 32+ bytes)* | Signs session cookies. Generate below. Changing it logs everyone out. |
| `ADMIN_KEY` | *(random secret)* | Gates `/api/admin/*` (invites, support tooling) via `X-Admin-Key`. |
| `DATABASE_URL` | *(Neon pooled URL, §1)* | `postgresql://…?sslmode=require` |
| `RESEND_API_KEY` | *(from §2)* | Absent → links are only logged, not emailed. |
| `EMAIL_FROM` | `Level <noreply@keepthingslevel.com>` | Omit to use the `resend.dev` test sender. |
| `APP_BASE_URL` | `https://keepthingslevel.com` | Used to build magic-link / invite URLs in emails. Must match the domain coaches click from. |
| `FRONTEND_ORIGIN` | `https://keepthingslevel.com` | CORS allow-origin. Same-origin deploy → can be left unset, but set it to be explicit. |
| `COOKIE_SECURE` | *(leave unset)* | Defaults to secure-on whenever auth is enabled (prod is https). Only set `false` for an http staging box. |

Generate the secrets:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"   # ADMIN_KEY
```

> `APP_BASE_URL` and `FRONTEND_ORIGIN` must be the **exact** origin coaches use
> (scheme + host, no trailing slash). A mismatch = broken invite links and/or
> cookies rejected cross-origin.

---

## 5. Domain — keepthingslevel.com

1. In Railway → the service → **Settings → Networking → Custom Domain** → add
   `keepthingslevel.com` (and optionally `www.`).
2. Railway shows a CNAME (or A/ALIAS for the apex) target. At your DNS registrar:
   - Apex `keepthingslevel.com` → the ALIAS/CNAME target Railway gives (use the
     registrar's ALIAS/ANAME/flattening if it's a bare CNAME at the apex).
   - `www` → CNAME to the same target (optional).
3. Wait for DNS + Railway's automatic TLS cert to go green.
4. Confirm `APP_BASE_URL` / `FRONTEND_ORIGIN` are set to `https://keepthingslevel.com`
   (§4). Redeploy if you changed them.

---

## 6. Smoke test (auth ON)

Against `https://keepthingslevel.com`:

1. **Boot gate.** Load the site → you should land on the login/join screen (not
   straight into the app), because `GET /api/auth/me` returns 401 when signed out.
2. **Mint an invite** (admin, from your machine):
   ```bash
   curl -X POST https://keepthingslevel.com/api/admin/invites \
     -H "X-Admin-Key: $ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{"note":"me — smoke test"}'
   ```
   Response includes `"link": "https://keepthingslevel.com/?invite=…"`.
3. **Redeem it.** Open that link → set your team up → you should receive (or, if
   still on the dev-stub with no `RESEND_API_KEY`, see logged) a sign-in link,
   verify, and land in the app with an empty squad.
4. **Create a squad + a match.** Confirm data saves.
5. **Isolation spot-check.** Mint a second invite, redeem in a private window as a
   second coach, confirm you cannot see the first coach's squad/matches.
6. **Rolling session.** Confirm you stay signed in across a reload (cookie is
   re-issued on activity, 30-day sliding expiry).

Admin support tooling (all `X-Admin-Key`-gated) if you need it:
```bash
curl https://keepthingslevel.com/api/admin/accounts            -H "X-Admin-Key: $ADMIN_KEY"
curl https://keepthingslevel.com/api/admin/accounts/1/dump     -H "X-Admin-Key: $ADMIN_KEY"   # read-only
curl -X POST https://keepthingslevel.com/api/admin/accounts/1/impersonate -H "X-Admin-Key: $ADMIN_KEY"
```

---

## 7. Rollout & branch

- Stand up the app on `feat/multi-user`, smoke-test, then **merge the branch to
  `main`** and point Railway at `main` (auto-deploy on push). Merging before or
  after standing up the deploy both work — the flag makes `main` safe either way.
- Send invites to a couple of coaches, confirm they can onboard, then widen.
- Leave the old Render instances running until you're confident, then retire them.

---

## 8. Ops notes

- **Restore of deleted data:** rely on **Neon point-in-time restore** for v1.
  Soft-delete is a documented fast-follow, not built yet.
- **Backups:** Neon retains history per your plan; no app-level backup job.
- **Rotating `SECRET_KEY`:** logs everyone out (sessions become unverifiable) —
  do it deliberately, not casually.
- **Cost:** Railway Hobby ~$5/mo (incl. $5 usage), one warm shared instance;
  Neon + Resend free tiers. Replaces ~$25/mo of Render single-user instances.
- **Rollback:** Railway keeps previous deploys — redeploy an earlier build, or
  flip `AUTH_ENABLED` off temporarily to fall back to single-squad behaviour
  (note: with it off, everyone shares one squad — emergency use only).
