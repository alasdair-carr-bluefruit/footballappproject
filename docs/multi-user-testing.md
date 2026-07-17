# Multi-user auth — quick testing guide

A short, practical guide to exercising the v1.1 auth backend by hand. The
automated tests (`tests/integration/test_auth.py`, `tests/unit/test_auth_core.py`)
already cover the important behaviour — **hands-on testing is low priority** (see
the note at the bottom). Use this when you want to *see* the flow, or after a
deploy.

## 1. Run the app with auth ON

Auth is **off by default** (single-squad dev mode). Turn it on with env vars:

```bash
AUTH_ENABLED=true SECRET_KEY=dev-secret ADMIN_KEY=dev-admin COOKIE_SECURE=false \
  .venv/bin/python -m uvicorn main:app --reload
```

- `COOKIE_SECURE=false` lets the session cookie work over `http://localhost`
  (in production it's https, so leave it unset there).
- With no `RESEND_API_KEY`, magic links are **not emailed** — they're logged to
  the console and returned in the API response as `dev_link`, so you can test
  without email set up.

## 2. Invite a coach (you, as admin)

```bash
curl -X POST localhost:8000/api/admin/invites \
  -H "X-Admin-Key: dev-admin" -H "Content-Type: application/json" \
  -d '{"note":"Dave – U10s"}'
# → {"id":1,"link":"http://localhost:8000/?invite=<TOKEN>", ...}
```

The `link` is what you'd send the coach. Copy the `<TOKEN>` after `invite=`.

## 3. Redeem the invite (the coach signs up)

```bash
curl -X POST localhost:8000/api/auth/redeem -c cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"token":"<TOKEN>","email":"dave@example.com","display_name":"Dave"}'
```

`-c cookies.txt` saves the session cookie. Now you're "logged in" as Dave:

```bash
curl localhost:8000/api/auth/me -b cookies.txt
# → {"authenticated":true,"email":"dave@example.com", ...}
```

Any app call with `-b cookies.txt` now operates on Dave's squad.

## 4. Sign in again on a "new device" (magic link)

```bash
curl -X POST localhost:8000/api/auth/request-link \
  -H "Content-Type: application/json" -d '{"email":"dave@example.com"}'
# → {"ok":true,"dev_link":"http://localhost:8000/?login=<LOGINTOKEN>"}

curl -X POST localhost:8000/api/auth/verify -c cookies2.txt \
  -H "Content-Type: application/json" -d '{"token":"<LOGINTOKEN>"}'
# → logged in; cookies2.txt now holds a fresh session
```

## 5. Check the rolling session

Every authenticated request re-issues the cookie with a fresh 30-day expiry, so
an active coach never has to re-request a link. You can see the refresh header:

```bash
curl -i localhost:8000/api/auth/me -b cookies.txt | grep -i set-cookie
# → set-cookie: gaffer_session=...   (re-issued on this request)
```

Only a coach who doesn't open the app for 30 days is asked for a new link.

## 6. Confirm isolation (two coaches don't see each other)

Redeem a second invite as `sam@example.com` into `cookies_sam.txt`, create a
match as Dave, then try to read it as Sam:

```bash
# as Dave:
curl -X POST localhost:8000/api/matches/ -b cookies.txt \
  -H "Content-Type: application/json" -d '{"date":"2026-03-25","opponent":"Rovers"}'
# note the returned "id"

# as Sam — should be 404, and Sam's list should be empty:
curl -i localhost:8000/api/matches/<DAVE_MATCH_ID> -b cookies_sam.txt   # → 404
curl localhost:8000/api/matches/ -b cookies_sam.txt                     # → []
```

---

## Is hands-on testing low priority? Yes.

The mechanics are covered by automated tests and the change is low-risk:

- **Rolling session, isolation/IDOR, invite + magic-link lifecycle** all have
  integration tests (`test_auth.py`) that run with auth enabled.
- Auth is **off by default**, so none of this affects the current single-user
  app or its 287 passing non-e2e / 47 e2e tests.

The verification that *does* matter happens later and end-to-end:
1. after the **frontend** lands (real click-the-link-in-an-email flow), and
2. on a **staging deploy** with a real `RESEND_API_KEY` — confirm an email
   actually arrives and the cookie sticks over https.

Until then, the curl walkthrough above is enough of a smoke test.
