# ADR 0005 — DEF restriction stays soft (warned, not enforced)

**Status:** Accepted (2026-11-24)

## Context

A player who didn't pick DEF is `def_restricted`. The swap passes (`_eligible_for`) never
move them into defence, but the first position assignment
(`rotation_engine._assign_outfield_positions.pool_for`) falls back to any unassigned player
when no eligible one is left, so a squeezed squad can put a DEF-restricted child at the back.
The roadmap listed "make it truly hard" as a quick fix.

## Decision

Keep it soft. Filling every position beats leaving a gap, and since 2026-08 the coach sees an
**"out of position"** plan warning before kick-off whenever it happens, so they can tinker.
GK specialist status remains hard.

## Consequences

- Don't "fix" the `pool_for` fallback into a hard rule; tests must not assert DEF is never used.
- Docs describe DEF as strongly avoided, not guaranteed (CLAUDE.md, requirements.md §3.2).
- Revisit only if coaches report the warning isn't enough.

## Update — 2026-11-24 (later the same day): DEF is no longer special

Owner: an unticked DEF should behave exactly like an unticked MID or ATT. The UI no longer
sets `def_restricted`, tournament position overrides no longer derive it, and Alembic revision
`a3d7c1e9f4b2` clears it on every player. `preferred_positions` carries the preference, so
DEF is now a plain soft pick. The engine's `def_restricted` code paths stay (dormant) for
API compatibility. The "No DEF" badge is gone. GK-only is still special, but only when the
coach says yes to the explicit "Keeper only?" switch.
