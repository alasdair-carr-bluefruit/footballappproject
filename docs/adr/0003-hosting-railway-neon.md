# ADR 0003 — v1.0 hosting: one Railway instance + fresh Neon Postgres

**Status:** Accepted (2026-06-12, reaffirmed 2026-07-10)

## Context

Single-user deployment is one Render free instance + Neon DB *per coach* (~£25/mo
across instances, each spinning down after 15 minutes idle — slow first loads).
Multi-user needs one always-on shared instance. Fly.io retired its free tier; Render
free spins down; Koyeb free limits were unverified; Oracle free VM means real ops work.

## Decision

- **Railway Hobby (~$5/mo)** for the app: always-on, GitHub auto-deploy, workflow
  near-identical to Render. Requires a small Dockerfile (FastAPI + uvicorn).
- **Fresh Neon Postgres** via `DATABASE_URL` for the multi-user schema, starting empty.
- **Existing Render instances and their Neon DBs stay untouched** as live fallback
  until each coach has migrated (squads are small; worst case is minutes of re-entry).

## Consequences

- Replaces ~£25/mo with ~$5/mo and removes spin-down lag.
- No destructive migration risk: old data is never touched by the new deployment.
- Deploy Guide.md remains valid only for legacy per-coach fallback instances.
