# Staging & release process

> Introduced 2026-09-11, at ~8 live coaches. Before this, every push to `main`
> went straight to production. That was fine with one user; it isn't now.
>
> Canonical doc for how changes reach live. `docs/Deploy Guide.md` is the
> **legacy single-user** Render setup and does not describe this.

---

## The branch model (pragmatic)

| Branch | Deploys to | Use for |
|---|---|---|
| `staging` | `staging.keepthingslevel.com` | Anything touching the rotation engine, the API, the database, or auth |
| `main` | `app.keepthingslevel.com` (live) | Docs, marketing copy, comments, and genuinely cosmetic tweaks |

The split is deliberately not "everything goes through staging" — a strict rule
gets abandoned the first time you want to fix a typo, and then you have no rule
at all. The line is: **could this change lose or corrupt a coach's data, or stop
them getting a plan out on a Saturday morning?** If yes, it goes via staging.

**Always via staging:**
- Alembic migrations (the highest-risk change type — see below)
- `backend/algorithm/**` — rotation, fairness, GK selection
- `backend/api/**`, `backend/db/**`, `backend/auth/**`
- Anything touching `deps.py` (the account/squad isolation seam)

**Straight to main is fine:**
- `docs/**`, `marketing/**`, `CLAUDE.md`
- Comments, copy tweaks, CSS that can't break a flow

### Releasing

```bash
git checkout staging
git merge main          # keep staging current before you start
# ... work, commit ...
git push origin staging # → CI runs, Railway deploys to staging
# verify on staging.keepthingslevel.com
git checkout main
git merge staging
git push origin main    # → production
```

Then **purge the Cloudflare cache**. Cloudflare serves the pre-deploy `.js` and
`sw.js` for ~4 hours; without a purge the change looks absent and incognito won't
help, because it's the CDN, not the browser. Bump the `CACHE` version in
`frontend/sw.js` in the same change whenever frontend assets move.

---

## One-time setup

Everything below is dashboard work — none of it lives in the repo.

### 1. Neon — a separate database

**Do not point staging at the production database.** Use Neon's branching:
create a branch of `main` named `staging`. You get a copy-on-write clone with
realistic data, and a restore point.

Copy the staging branch's connection string; make sure it starts `postgresql://`
not `postgres://`.

### 2. Railway — a second environment

New environment (or service) watching the `staging` branch, same build and start
commands as production.

### 3. Staging environment variables

| Variable | Value | Why |
|---|---|---|
| `DATABASE_URL` | the Neon **staging branch** string | Never prod |
| `APP_BASE_URL` | `https://staging.keepthingslevel.com` | Magic links must point at staging |
| `FRONTEND_ORIGIN` | `https://staging.keepthingslevel.com` | CORS |
| `SECRET_KEY` | a **new** random value | A leaked staging key must not sign prod sessions |
| `ADMIN_KEY` | a **new** random value | Same |
| `AUTH_ENABLED` | `true` | Match prod, or you're not testing the real thing |
| `RESEND_API_KEY` | **leave unset** | See below |
| `EMAIL_FROM` | unset | Only used when Resend is configured |

**Leaving `RESEND_API_KEY` unset is the important one.** With no email provider,
`/api/auth/request-link` returns the sign-in link directly in the response and
the UI renders it as a "Dev link" button (`auth.js`, `login-devlink`). So you can
sign into staging instantly, and there is **no way for staging to email a real
coach** — worth having even once you're tempted to wire up a test key.

Sessions won't leak between the two hosts: the cookie is set without a `domain`
attribute (`backend/auth/session.py:99`), so it's host-only.

### 4. DNS

`staging.keepthingslevel.com` → the Railway staging domain. Railway will also ask
for a `_railway-verify` **TXT** record — that was the gotcha that held up the
production cutover, so add it up front.

### 5. Keep staging out of Google

Staging serves the same `index.html` as production, so it can be indexed and
outrank the real thing. Either put Cloudflare Access in front of it, or serve
`X-Robots-Tag: noindex` on the staging host.

---

## Migrations, which are the actual risk

Bad code shows up as an error and you roll back. A bad Alembic migration can
silently mangle live squads and cannot be undone by redeploying.

Before running any migration against production:

1. Run it on staging first, against the Neon staging branch.
2. Take a Neon branch of **production** as a restore point immediately before.
3. Check it's reversible, or accept that it isn't and say so in the PR/commit.

`backend/db/migrations/` is Alembic; the older additive `ALTER TABLE ... ADD
COLUMN` bridge still exists for legacy columns but new work goes through a
revision.

---

## CI

`.github/workflows/ci.yml` runs on every push to `main`/`staging` and every PR
into them: `ruff check .` then `pytest -m "not e2e"` (375 tests, ~7s).

Two deliberate gaps:

- **Lint is non-blocking.** There are ~61 pre-existing findings, mostly `E402` in
  `tests/bdd/steps/` where imports after the feature binding are idiomatic. Clear
  the backlog, then drop `continue-on-error` from the Lint step.
- **e2e doesn't run in CI.** The Playwright suite needs a browser binary and a
  live uvicorn subprocess. Run `pytest -m e2e` locally before a release that
  touches the season or tournament golden path.
