# Gaffer — Squad Rotation Manager

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
| `CLAUDE.md` | Primary development context — conventions, data model, constraints |
| `requirements.md` | Functional requirements (FR-01…) |
| `PHASES.md` | Phase history and acceptance gates |
| `DEVELOPMENT_PLAN.md` | Current audit findings + forward roadmap (v0.9 → v1.x) |
| `V1_MULTIUSER_PLAN.md` | Multi-user/auth implementation plan (magic-link-first) |
| `docs/adr/` | Architecture decision records |
| `docs/feedback/` | Captured user feedback |
| `BRAND.md` | Gaffer brand guidelines |
| `Deploy Guide.md` | Legacy per-coach single-user deployment (Render + Neon) |

## Reporting bugs

Found a bug? [Open an issue](../../issues/new?labels=bug&template=bug_report.md&title=%5BBug%5D+)
(in-app reporting without a GitHub account is planned for v0.9).
