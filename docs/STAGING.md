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

## One-time setup — the evening runbook

All dashboard work; nothing here lives in the repo. Allow about an hour, most of
it waiting for DNS. Do the steps in order — each one's verification depends on
the previous.

**Before you start, generate two secrets** and keep them somewhere for step 4:

```bash
python3 -c "import secrets; print('SECRET_KEY=', secrets.token_urlsafe(48))"
python3 -c "import secrets; print('ADMIN_KEY=',  secrets.token_urlsafe(32))"
```

---

### ☐ 1. Neon — branch the database

The single most important step. **Staging must never point at the production
database** — a migration you're testing would hit eight real coaches' squads.

1. Neon dashboard → your project → **Branches** → **New branch**
2. Parent: `main` (or `production`, whatever your prod branch is called)
3. Name it `staging`
4. Open the new branch → **Connection string** → copy it

Neon branches are copy-on-write, so this is instant, costs almost nothing, and
gives you realistic data to test against.

**Verify:** the string starts `postgresql://` (not `postgres://`) and the host
differs from your production one. If they're identical you've copied the wrong
branch — stop and re-copy, this is the one mistake that actually hurts.

---

### ☐ 2. Railway — a second environment

1. Railway → your project → environment dropdown → **New Environment**
2. Name it `staging`
3. Point its service at the same GitHub repo, watching the **`staging`** branch
4. Same build and start commands as production:
   - Build: `pip install -e ".[api]"`
   - Start: `python -m uvicorn main:app --host 0.0.0.0 --port $PORT`

**Verify:** it builds and the deploy log ends with uvicorn listening. It will
still fail to serve properly until step 4 — that's expected.

---

### ☐ 3. Railway — generate a staging domain

Settings → **Networking** → **Generate Domain**. You'll get something like
`level-staging-production.up.railway.app`. Keep the tab open; you need this for
step 5.

**Verify:** the Railway URL loads the app (it'll be a fresh empty instance).

---

### ☐ 4. Staging environment variables

Set these on the **staging environment only**:

| Variable | Value | Why it matters |
|---|---|---|
| `DATABASE_URL` | the Neon **staging branch** string from step 1 | Never prod |
| `APP_BASE_URL` | `https://staging.keepthingslevel.com` | Magic links are built from this — point it at prod and your staging sign-in emails send people to the live app. **Include the `https://`** — without a scheme the link is treated as relative and the Dev-link button 404s |
| `FRONTEND_ORIGIN` | `https://staging.keepthingslevel.com` | CORS |
| `SECRET_KEY` | the **new** value you generated | A leaked staging key must not be able to sign production sessions |
| `ADMIN_KEY` | the **new** value you generated | Same |
| `AUTH_ENABLED` | `true` | Match prod, or you aren't testing the real thing |
| `RESEND_API_KEY` | **leave unset** | See the box below |
| `EMAIL_FROM` | leave unset | Only read when Resend is configured |

> **Leave `RESEND_API_KEY` unset.** With no email provider, `/api/auth/request-link`
> returns the sign-in link in the response body and the UI renders it as a
> **"Dev link — open sign-in"** button (`auth.js` → `login-devlink`). Two wins:
> you sign into staging in one click with no inbox round-trip, and it is
> *structurally impossible* for staging to email a real coach. Resist wiring up
> a test key later.

Note `validate_config()` fails fast on boot if `AUTH_ENABLED=true` and either
secret is missing — so a boot crash here means you missed one.

> **Ordering:** DNS doesn't exist until step 5, so set `APP_BASE_URL` and
> `FRONTEND_ORIGIN` to the **Railway URL** for now and swap them to
> `staging.keepthingslevel.com` once step 5 is green. Set them to the real
> hostname too early and the Dev link lands on a domain that doesn't resolve.

**Verify:** redeploy, open the Railway URL, and you should get the **Coach
sign-in** screen. Enter **an email that already has an account** — your own —
→ the **Dev link** button appears → tap it → you're in, looking at that
account's squad. That proves the DB, secrets and auth are all wired.

Not *any* email: `request-link` only returns `dev_link` when an active account
matches, and deliberately returns a bare `200 {"ok": true}` otherwise so the
endpoint can't be used to enumerate accounts. An unknown email looks like
nothing happening — that's correct behaviour, not a broken deploy. Because the
Neon staging branch clones production, every real coach's email works here, so
you can reproduce a reported bug signed in as them, against their own data,
without touching production.

---

### ☐ 5. DNS — `staging.keepthingslevel.com`

In Railway: Settings → Networking → **Custom Domain** → `staging.keepthingslevel.com`.
Railway shows you the records it wants. In Cloudflare, add:

- a **CNAME** `staging` → the Railway target
- the **`_railway-verify` TXT** record Railway asks for ← *this is the one that
  held up the production cutover; add it at the same time, not after it fails*

Set the CNAME to **DNS only** (grey cloud) initially — it's one less layer while
you're checking the domain works. Turn the orange cloud on afterwards if you want
Cloudflare in front.

**Verify:** `dig staging.keepthingslevel.com` resolves, and the URL serves the
sign-in screen. Railway's domain status goes green.

---

### ☐ 6. Keep staging out of Google

Staging serves the same `index.html` as production, so left alone it will get
indexed and can outrank the real site.

Easiest: **Cloudflare Access** in front of the hostname (email OTP to yourself) —
that blocks both crawlers and randoms. Alternative: a Cloudflare Transform Rule
adding `X-Robots-Tag: noindex` on that host.

**Verify:** open staging in a private window — you should hit the Access prompt
(or see the `noindex` header in devtools → Network → Headers).

---

### ☐ 7. Prove the whole loop works

Don't declare it done until a change has actually travelled the path:

```bash
git checkout staging
# make a visible, harmless change — e.g. a word in the landing copy
git commit -am "test: staging deploy check"
git push origin staging
```

Watch CI go green, watch Railway deploy, confirm the change appears on
`staging.keepthingslevel.com` **and not** on `app.keepthingslevel.com`. Then
revert it on staging.

If that works, staging is real.

---

### Notes

Sessions can't leak between the two hosts: the cookie is set without a `domain`
attribute (`backend/auth/session.py:99`), so it's host-only. Signing into staging
will not sign you out of production.

Your existing production env vars are untouched by all of this — the two Railway
environments have separate variable sets.

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
