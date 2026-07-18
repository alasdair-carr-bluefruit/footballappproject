# Level — Squad Rotation Manager

A mobile-first PWA for grassroots youth football coaches: generates a full, fair
rotation plan (who plays where, when) for 5v5–9v9 matches and tournament days,
respecting goalkeeper tiers, position preferences, playing-time fairness, and
substitution limits — then runs match day pitch-side (live pitch view, tinkering
mode, goal recording, share image).

## Stack

Python 3.12 / FastAPI / SQLModel (SQLite, Postgres via `DATABASE_URL`) backend with a
pure-Python rotation algorithm; vanilla-JS PWA frontend.

## Quick start

```bash
pip install -e ".[dev]"
python -m uvicorn main:app --reload   # serves API + frontend
pytest                                # full test suite
ruff check .
```

## Documentation map

| Doc | Purpose |
|---|---|
| `CLAUDE.md` | Primary development context — conventions, data model, constraints, current phase |
| `requirements.md` | Functional requirements (FR-01…) |
| `DEVELOPMENT_PLAN.md` | Audit findings + forward roadmap (refactor → v1.0 → v1.x) |
| `docs/refactor/NEXT_STEPS.md` | Live refactor-phase (C.4) tracker |
| `V1_MULTIUSER_PLAN.md` | Multi-user/auth implementation plan (magic-link-first) |
| `docs/adr/` | Architecture decision records |
| `docs/feedback/` | Captured user feedback |
| `BRAND.md` | Level brand guidelines |
| `DEPLOY.md` | Multi-user deployment (Railway + Neon + Resend) |
| `docs/Deploy Guide.md` | Legacy per-coach single-user deployment (Render + Neon) |

## Reporting bugs

Found a bug? [Open an issue](../../issues/new?labels=bug&template=bug_report.md&title=%5BBug%5D+)
(in-app reporting without a GitHub account is planned for v0.9).
