# ADR 0001 — Evolve the existing codebase; no V2 rebuild

**Status:** Accepted (2026-07-10)

## Context

Two competing futures were drafted: `V1_MULTIUSER_PLAN.md` (evolve in place) and
`V2_Requirements.md`/`V2_UI_Requirements.md` (full rebuild: React, UUID/RLS Postgres
schema, local-first sync engine, ads/subscriptions). A 2026-07 audit found the backend
well-layered (pure-Python algorithm, one-function tenancy seam in
`get_or_create_squad()`, all 34 endpoints integration-tested) and the frontend's pain
to be *monolith + no tests*, not the choice of vanilla JS.

## Decision

Evolve. Keep the backend and rotation algorithm. Restructure `frontend/app.js` into
ES modules incrementally (no framework). Treat the V2 documents as a parts bin:
adopt the plan-review concept, tinkering undo/redo command stack, and multi-tenant
schema *direction*; defer local-first sync and monetization indefinitely
(re-evaluate only if real usage demands them).

## Consequences

- ~144 passing tests and a battle-tested algorithm are retained.
- User-facing progress continues during refactoring; no feature freeze.
- The V2 docs remain gitignored reference material, not a commitment.
- If offline reliability becomes a real problem pitch-side, the sync question reopens.
