# Level — fair rotation for grassroots youth football

A mobile-first PWA for grassroots youth football coaches. It builds a full, fair
rotation plan (who plays where, and when) for 5v5–9v9 matches and tournament days,
then runs match day pitch-side. Live at **app.keepthingslevel.com** (invite-only);
marketing site and coach guides at **keepthingslevel.com**.

**Stack:** Python 3.12 · FastAPI · SQLModel (SQLite locally, Neon Postgres in production,
Alembic migrations) · pure-Python rotation engine · vanilla-JS ES-module PWA · Railway + Cloudflare.

```bash
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"
.venv/bin/python -m uvicorn main:app --reload   # API + frontend
.venv/bin/python -m pytest                       # ~580 tests (incl. Playwright e2e)
.venv/bin/ruff check .
```

## Documentation map

| Doc | What it's for |
|---|---|
| `CLAUDE.md` | **Read first.** Current state, conventions, constraints, data model |
| `DEVELOPMENT_PLAN.md` | The only roadmap: ▶ Next up, backlog, decision points, risks |
| `docs/STAGING.md` | How changes reach live (`staging` → `main`) |
| `docs/DEPLOY.md` | Infra setup: Railway + Neon + Resend + Cloudflare |
| `docs/adr/` | Why the big decisions were made |
| `docs/ASSISTANT_COACH_PLAN.md` | Assistant-coach design (phase 3 still to build) |
| `BRAND.md` + `assets/brand/tokens.json` | Brand (runtime truth: `frontend/style.css` `:root`) |
| `requirements.md` | Original product spec + FR numbers (not a status tracker) |
| `marketing/README.md` | The static marketing site (Cloudflare Pages) |
| `docs/youtube/` | Tutorial video strategy + scripts |
| `docs/reference/` | External source documents (e.g. league rules) |
| `docs/archive/` | Shipped plans and history (`CHANGELOG.md`) — not current |

## Reporting bugs

Coaches report bugs in the app (Settings → Report a bug). Developers can also
[open an issue](../../issues/new?labels=bug&template=bug_report.md&title=%5BBug%5D+).
