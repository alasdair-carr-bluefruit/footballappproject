# ADR 0004 — Frontend stays vanilla JS, split into ES modules with a Playwright smoke suite

**Status:** Accepted (2026-07-10)

## Context

`frontend/app.js` grew 330 → 2,843 lines in two months with 27 mutable globals, zero
tests, ~200 lines of duplicated season/tournament setup logic, and churn clusters in
git history showing changes are error-prone. `V2_UI_Requirements.md` assumed a React
rebuild; user feedback asks for season/tournament component parity and automated
checks of it.

## Decision

No framework. Restructure in place (DEVELOPMENT_PLAN.md Phase C):

- Split app.js into ES modules: `state.js`, `screens.js`, `pitch.js`,
  `setup-form.js` (one shared season+tournament config form), `season.js`,
  `tournament.js`.
- Add a Playwright smoke suite that drives both modes through the same flows
  (create → generate → tinker → start → advance → full time) — this is the
  automated season/tournament parity check.
- The smoke suite lands **before** the bulk of the extraction; one module per commit.

## Consequences

- Fixes fragility at a fraction of a rewrite's cost; no user-facing freeze.
- Parity regressions between modes become CI failures instead of user feedback.
- Revisit a framework only if the module structure proves insufficient (e.g. the
  v1.1 plan-review screen becoming unmanageable in vanilla DOM code).
