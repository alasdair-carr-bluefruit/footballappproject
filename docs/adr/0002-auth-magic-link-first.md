# ADR 0002 — v1.0 auth is email + magic link; the PIN stage is skipped

**Status:** Accepted (2026-07-10) — supersedes the PIN-first sequencing in `V1_MULTIUSER_PLAN.md`

## Context

`V1_MULTIUSER_PLAN.md` (2026-06-12) proposed shipping PIN login first, architected so
magic link could be added later without identity migration (`AccountDB` is the identity;
credential verification is separate from session issuance). The owner has since decided
email + magic link is the near-term goal, which removes the reason to build PIN at all.

## Decision

Build magic link as the first and only credential verifier:

- `AccountDB.email` is **required and unique** (the login handle).
- No `pin_hash` / lockout fields; no `/set-pin` endpoint.
- New `LoginTokenDB`: hashed one-time login token, ~15-minute expiry, single-use
  (same shape as `InviteDB`). Endpoints: `POST /api/auth/request-link`,
  `POST /api/auth/verify`.
- Transactional email via Resend or Postmark (free tier suffices for invited coaches).
- Everything else in `V1_MULTIUSER_PLAN.md` stands: invite-only onboarding, signed
  HttpOnly session cookie, `get_current_account`/`get_current_squad` dependencies,
  `owned_*()` IDOR guards, CORS tightening.

## Consequences

- No PIN code is ever written, tested, or migrated away from.
- Login gains an external dependency (email delivery); mitigate with a verified
  sending domain and the invite flow as a fallback ("send me a fresh link").
- `/auth/request-link` must be rate-limited (email-sending abuse surface).
