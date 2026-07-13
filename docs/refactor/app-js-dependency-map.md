# app.js dependency map (pre-refactor)

Built by reading `frontend/app.js` in full (3,086 lines) and grepping every
mutable global's read/write sites, before any code was moved. Target module
split is the one named in `DEVELOPMENT_PLAN.md` Phase C.1: `state.js`,
`screens.js`, `pitch.js`, `setup-form.js`, `season.js`, `tournament.js`.

**Key mechanic that drives every "risk" call below:** ES module imports are
live bindings for *reads* — any module can `import { x } from './state.js'`
and always see the current value, no matter which module last wrote it.
The only thing that breaks across a module boundary is a *raw reassignment*
(`x = ...`) of an imported binding — that throws, because imported bindings
are read-only in the importing module. So the only real hazard is: **a
global whose raw `x = ...` sites live in more than one target module.**
Property/Set mutation in place (`matchData.slots = ...`, `lockedSlots.add()`,
`goalCounts[name] = ...`) is *not* a reassignment of the top-level binding —
those are safe from any module as long as the object itself isn't rebound
elsewhere.

---

## 1. Cross-module write hazards (fix these first, before splitting)

Four globals are reassigned with a bare `x = ...` from what will become two
or three different files. Each needs an **exported setter/loader function**
in its home module that the other module(s) call — not a plain `export let`.

### 1a. `editMode` and `manualRotationMode` — season.js ↔ pitch.js
Always set together, in exactly two places:
- `btn-manual-slots` handler (app.js:544-545) → **season.js** — sets both `true`
- `btn-manual-slots-pitch` handler (app.js:561-562) → **pitch.js** — sets both `true`
- Also written from inside pitch.js proper: `enterPitchView` (268-269),
  `btn-next` handler (1417, manual-mode branch), `btn-adjust` handler (1741,
  `editMode` only).

Fix: give `pitch.js` an exported `enterManualAssignMode()` (or similar) that
does `editMode = true; manualRotationMode = true;`, and have season.js's
`btn-manual-slots` handler call it after `enterPitchView(data)` instead of
assigning the raw globals itself.

### 1b. `gameConfigs` — season.js ↔ tournament.js
Reassigned identically in three places, each guarded by `if (!gameConfigs)`:
- `btn-go-new-match` handler (342) → **season.js**
- `btn-new-tournament` handler (2390) → **tournament.js**
- `btn-edit-tournament` handler (2783) → **tournament.js**

Fix: export `async function ensureGameConfigs()` from `setup-form.js` (it
already owns the formation-dropdown logic that consumes `gameConfigs`); both
season.js and tournament.js call it instead of inlining the fetch-and-cache.

### 1c. `shirtNumbers` — pitch.js ↔ screens.js ↔ tournament.js (highest risk — 3 modules)
Rebuilt from scratch with the identical `shirtNumbers = {}; players.forEach(...)`
pattern in three unrelated places:
- `openMatch` (310) → **pitch.js**
- `loadSquad` (602) → **screens.js**
- `btn-generate-tournament-match` handler (3078) → **tournament.js**

Fix: export `async function refreshShirtNumbers()` from `state.js` (fetches
players, rebuilds the map); all three call sites replace their inline block
with a call to it. This is also flagged in `DEVELOPMENT_PLAN.md` as
duplicated logic, so fixing it kills two birds.

### 1d. Pre-existing bug found while mapping — do not silently "fix" without flagging it to the user
`pitchBackContext` (default `"season"`) is set to `"tournament"` in two
places (renderLobbyMatches' match-click handler, line 2878; and
`btn-generate-tournament-match`, line 3074) but is **never** reset back to
`"season"` anywhere — not even when `loadHome`'s match-list click handler
opens a season match (`openMatch(m.id)`, line 248, no context reset).
`activeTournamentId` has the same one-way-only lifecycle (set in
`loadTournamentSquadScreen`/`loadTournamentLobby`, never cleared).

Net effect: once a coach opens *any* tournament match in a session, the
pitch "back" button and the full-time "done" button (both gate on
`pitchBackContext === "tournament" && activeTournamentId`) will incorrectly
route back to the tournament lobby the next time they open a **season**
match, instead of the season home list. This is a real latent bug, not a
refactor artifact — worth deciding explicitly whether to fix it (reset both
in `openMatch`'s season-entry path, or better: pass back-context as an
explicit parameter through the call chain instead of a global) rather than
having it silently reproduced or silently patched mid-split.

---

## 2. Full mutable-state inventory

Every module-level `let`/mutable `const` object, its natural home module (all
current writers agree on one module unless flagged), and who touches it.

| Global | Declared | Home module | Writers (function → module) | Notes |
|---|---|---|---|---|
| `currentSlot` | 4 | pitch.js | `enterPitchView`, `doStartMatch`, `btn-next`/`btn-prev` handlers — all pitch.js | contained |
| `showingReport` | 5 | pitch.js | `enterPitchView`, `showMatch`, `btn-next` — all pitch.js | contained |
| `showingChanges` | 6 | pitch.js | `enterPitchView`, `showMatch`, `btn-next`, `btn-prev` — all pitch.js | contained |
| `editMode` | 7 | pitch.js | **season.js + pitch.js** | ⚠️ see 1a |
| `matchStarted` | 8 | pitch.js | `doStartMatch`, `btn-return-plan` — pitch.js | contained |
| `lockedSlots` | 9 | pitch.js | `enterPitchView`, `btn-next` (manual carry-fwd), `applyAdjustResult`; `.add()` in `playerCircle` drop handler — all pitch.js | contained |
| `pendingSwap` | 10 | pitch.js | `swap-cancel`, `openSwapPicker`, `executeSwap` — pitch.js | contained |
| `dragState` | 11 | pitch.js | `playerCircle` drag handlers only | contained |
| `matchData` | 12 | pitch.js | **reassigned only in `enterPitchView`**; all `.slots=`/`.match.status=`/etc. property writes happen inside other pitch.js functions (`btn-next`, action-remove/reinstate, `applyAdjustResult`, `doStartMatch`, `doEndMatch`, `btn-return-plan`) | contained — object mutation only, safe |
| `goalCounts` | 13 | pitch.js | never reassigned (const); mutated in `enterPitchView`, `playerCircle`, `btn-action-goal` — all pitch.js | could become pitch.js-local, not shared state |
| `gameConfigs` | 14 | setup-form.js | **season.js + tournament.js (×2)** | ⚠️ see 1b |
| `selectedSize` | 15 | setup-form.js | `selectSize` only | season.js *calls* `selectSize()`, doesn't assign directly — safe |
| `selectedHomeAway` | 16 | season.js | `home-away-picker` click handler | season-only concept (tournaments have no home/away); doesn't belong in setup-form.js |
| `selectedPeriods` | 17 | setup-form.js | `selectPeriods` only | contained |
| `manualRotationMode` | 18 | pitch.js | **season.js + pitch.js** | ⚠️ see 1a |
| `teamInfo` | 19 | screens.js | `initScreen`, tutorial-start handler, `loadSquad`, `btn-save-team-info` handler — all screens.js | read (not written) from pitch.js (`showFulltime`, `buildResultBlob`) — fine, reads are always live |
| `shirtNumbers` | 20 | state.js (shared) | **pitch.js + screens.js + tournament.js (×3)** | ⚠️ see 1c, highest risk |
| `removedPlayers` | 21 | pitch.js | `enterPitchView`, action-remove handler, reinstate-confirm handler — pitch.js | contained |
| `pendingActionPlayer` | 22 | pitch.js | all in player-action/reinstate overlay handlers — pitch.js | contained |
| `pendingDeletePlayerId` | 23 | screens.js | `loadSquad`'s delete button, delete-player cancel/confirm — screens.js | contained |
| `pitchBackContext` | 24 | tournament.js writes it | tournament.js only writes; **never reset to "season"** | ⚠️ see 1d, latent bug |
| `squadBackContext` | 25 | screens.js | `btn-squad-management` handler only | contained (note: also never explicitly reset to `"season"`, but only two values and default covers it — lower risk than 1d) |
| `activeTournamentId` | 26 | tournament.js | `loadTournamentSquadScreen`, `loadTournamentLobby` — tournament.js | contained, but see 1d for lifecycle gap |
| `activeTournamentStage` | 27 | tournament.js | `openAddMatchPanel` only | contained |
| `pendingPositionChanges` | 28 | tournament.js | `loadTournamentSquadScreen`, pos-chip click handler, `btn-generate-all-matches` — tournament.js | contained |
| `cachedSquadPlayers` | 29 | tournament.js | `loadTournamentSquadScreen` only | contained |
| `lastQuipIndex` | 420 | setup-form.js | `pickCompetitiveQuip` only | contained |
| `pendingMatchConfig` | 464 | season.js | `btn-select-players` handler only | contained |
| `editingPlayerId` | 576 | screens.js | `openPlayerForm`, `closePlayerForm` — screens.js | contained |
| `timerInterval` | 1487 | pitch.js | `stopTimerTicker`, `startTimerTicker` — pitch.js | contained |
| `newPeriodHintSlot` | 1488 | pitch.js | new-period reset/dismiss handlers, `doStartMatch` — pitch.js | contained |
| `tournamentSelectedSize` | 2343 | tournament.js | `tournamentSelectSize` only | contained; near-duplicate of `selectedSize`, see §4 |
| `activeTournamentData` | 2344 | tournament.js | `loadTournamentSquadScreen`, `loadTournamentLobby` — tournament.js | contained |
| `pendingTournamentId` | 2459 | tournament.js | set once (2507), **never read anywhere** | dead variable — candidate for deletion, confirm with user before removing |
| `pendingNumMatches` | 2460 | tournament.js | `new-tournament-form` submit handler only | contained |
| `editingTournamentId` | 2776 | tournament.js | 5 sites, all tournament.js | contained |

---

## 3. Constants / pure helpers that must move as a unit

Not mutable state, but referenced across functions — get these wrong and a
function silently reads `undefined`.

- `DEF_KEYS`, `MID_KEYS`, `FWD_KEYS`, `_DEF_SET`, `_MID_SET`, `_FWD_SET`,
  `parseFormation()`, `formationPositions()`, `normalizePos()` — **all
  belong to pitch.js only.** Verified: every call site is `render()`,
  `renderChanges()`, or `renderReport()`. They are *not* used by
  `updateFormationOptions`/`updateTournamentFormationOptions` (those build
  the formation `<select>` purely from the `gameConfigs` API payload, a
  different data source) — don't be tempted to lump these into
  `setup-form.js` just because "formation" is in both names.
- `COMPETITIVE_QUIPS`, `pickCompetitiveQuip()`, `lastQuipIndex`,
  `updateFairnessLabel()`, `getRotationValue()` — genuinely shared: called
  from both season's new-match screen and tournament's new/edit + knockout
  screens. These belong in `setup-form.js`, imported by both season.js and
  tournament.js.

---

## 4. Duplication already flagged in DEVELOPMENT_PLAN.md — confirmed, not cross-module-risky, but worth doing while files are open

- `selectSize`/`selectPeriods`/`updateFormationOptions` (season, driven by
  `selectedSize`/`selectedPeriods`) vs `tournamentSelectSize`/
  `updateTournamentFormationOptions` (tournament, driven by
  `tournamentSelectedSize`) — near-identical bodies, different globals. Each
  is currently self-contained (no cross-module write), so merging is a
  design choice (parametrize like `getRotationValue(formPrefix)` already
  does), not a correctness requirement. Flagging so it isn't confused with
  the §1 hazards during the split.
- The player-form position/GK-status derivation logic (`gk_status` +
  `def_restricted` from checked positions) is duplicated near-verbatim in
  the squad player-form submit handler (~line 770) and the guest-player-form
  submit handler (~line 2996). Candidate for a shared `derivePositionFields()`
  helper.

---

## 5. Function-by-function ledger, grouped by target module

Format: `functionName / handler-id` — globals read, globals written (`—` = none).

### state.js (new file — home for shared globals + the setter/loader fixes from §1)
No existing functions live here today; this file's job is to hold the
declarations plus the new exported helpers: `enterManualAssignMode()`,
`ensureGameConfigs()` (or place in setup-form.js, see 1b), `refreshShirtNumbers()`.

### screens.js
- `showScreen` — none (DOM only)
- `initScreen` IIFE — R: none W: `teamInfo`
- tutorial logo/start handlers — W: `teamInfo`
- `showSquadTip` / `dismissSquadTip` — none (localStorage/DOM)
- bug-report handlers — R: `matchData` (id only), `activeTournamentId`
- `loadHome` — none
- `loadSquad` — W: `teamInfo`, `shirtNumbers`
- `openPlayerForm` — W: `editingPlayerId`
- `updateBestPositionOptions` — none
- `closePlayerForm` — W: `editingPlayerId`
- `btn-squad-back` handler — R: `squadBackContext`
- `btn-save-team-info` handler — W: `teamInfo`
- player-form submit handler — R: `editingPlayerId` (via close), calls `loadSquad`
- delete-player cancel/confirm — W: `pendingDeletePlayerId`
- `loadStats` / `loadPlayerHistory` — none
- `buildMatchesCsv` / export handlers — none

### setup-form.js
- `pickCompetitiveQuip` — R/W: `lastQuipIndex`
- `updateFairnessLabel` — calls `pickCompetitiveQuip` (indirect `lastQuipIndex`)
- `getRotationValue` — none
- `selectSize` — W: `selectedSize`; calls `selectPeriods`, `updateFormationOptions`
- `selectPeriods` — W: `selectedPeriods`
- `updateFormationOptions` — R: `gameConfigs`, `selectedSize`
- `tournamentSelectSize` — W: `tournamentSelectedSize`
- `updateTournamentFormationOptions` — R: `gameConfigs`, `tournamentSelectedSize`
- (new) `ensureGameConfigs()` — R/W: `gameConfigs`

### pitch.js
- `slotObj` / `periodLabel` — R: `matchData`
- `slotPlayerNames` / `incomingSubs` / `outgoingSubs` — params only
- `playerCircle` — R: `goalCounts`, `shirtNumbers`, `editMode`, `matchStarted`, `dragState`, `matchData`; W: `goalCounts`, `dragState`, `matchData` (lineup swap), `lockedSlots` (`.add`)
- `render` — R: `matchData`, `currentSlot`, `editMode`, `matchStarted`, `lockedSlots`, `removedPlayers`, `showingReport`, `newPeriodHintSlot`
- `renderChanges` — R: `matchData`, `currentSlot`
- `renderReport` — R: `matchData`, `matchStarted`, `goalCounts`
- `showMatch` — W: `showingReport`, `showingChanges`
- `enterPitchView` — W: `matchData`, `showingReport`, `showingChanges`, `editMode`, `manualRotationMode`, `lockedSlots`, `removedPlayers`, `goalCounts` (clear), `matchStarted`, `currentSlot`; R: `manualRotationMode`
- `openMatch` — W: `shirtNumbers`; calls `enterPitchView`
- `btn-next` handler — R: `showingReport`, `matchStarted`, `showingChanges`, `currentSlot`, `matchData`, `manualRotationMode`; W: `currentSlot`, `matchData.match.current_slot`, `showingChanges`, `editMode`, `lockedSlots`, `showingReport`
- `btn-prev` handler — R: `showingReport`, `showingChanges`, `currentSlot`; W: `currentSlot`, `showingChanges`
- `btn-end-match`/cancel/confirm — R: `currentSlot`, `matchData`, `showingReport`
- `doEndMatch` — R: `matchData`, `goalCounts`, `currentSlot`; W: `matchData.match.status`
- timer functions (`timerKey`, `readTimer`, `writeTimer`, `timerElapsedSecs`, `beginMatchTimer`, `resumeMatchTimer`, `resetMatchTimer`, `stopTimerTicker`, `clearMatchTimer`, `startTimerTicker`, `updateTimerDisplay`) — R: `matchData` (id), `matchStarted`, `showingReport`; W: `timerInterval`
- new-period reset/dismiss handlers — W: `newPeriodHintSlot`; R: `currentSlot`
- `doStartMatch` — R: `matchData`; W: `matchStarted`, `matchData.match.*`, `currentSlot`, `newPeriodHintSlot`
- `showGoalTip` — none
- `btn-return-plan` handler — R: `matchData`; W: `matchStarted`, `matchData.match.status`
- `openPlayerActionMenu` / `openReinstateOverlay` — W: `pendingActionPlayer`; R: `currentSlot`
- action-cancel/goal/remove, reinstate-cancel/confirm — R: `pendingActionPlayer`, `matchData`, `currentSlot`; W: `pendingActionPlayer`, `goalCounts`, `removedPlayers`, `matchData.slots`/`.warnings`
- `btn-adjust` handler — W: `editMode`
- `openSwapPicker` — W: `pendingSwap`; R: `matchData`
- `executeSwap` — R: `pendingSwap`, `matchData`, `manualRotationMode`, `lockedSlots`; W: `pendingSwap`
- `fillFairnessList` / `showFairnessWarning` / `showFairnessInfo` — DOM only (warning/info dialogs)
- `applyAdjustResult` — W: `matchData.slots`/`.warnings`, `lockedSlots`
- `saveGoalsIfNeeded` — R: `matchData`, `goalCounts`
- `btn-pitch-back` handler — R: `pitchBackContext`, `activeTournamentId`
- `showFulltime` — R: `matchData`, `goalCounts`, `teamInfo`
- `ft-opp-input` handler — R: `goalCounts`, `matchData`
- `btn-ft-done` handler — R: `matchData`, `goalCounts`, `pitchBackContext`, `activeTournamentId`
- `buildResultBlob` / `downloadBlob` / share handlers — R: `matchData`, `goalCounts`, `teamInfo`

### season.js
- `btn-go-new-match` handler — R: (calls `ensureGameConfigs`); W: `gameConfigs` today (⚠️ fold into 1b fix)
- `btn-select-players` handler — R: `selectedSize`, `selectedHomeAway`, `selectedPeriods`; W: `pendingMatchConfig`
- `btn-generate` handler — R: `pendingMatchConfig`; calls `enterPitchView`
- `btn-manual-slots` handler — R: `pendingMatchConfig`; W: `manualRotationMode`, `editMode` today (⚠️ fold into 1a fix); calls `enterPitchView`
- `home-away-picker` click handler — W: `selectedHomeAway`

### tournament.js
- `loadTournamentHome` — none
- `btn-new-tournament` handler — W: `gameConfigs` today (⚠️ 1b), `editingTournamentId`
- `btn-new-tournament-back` handler — R: `editingTournamentId`; W: `editingTournamentId`
- `new-tournament-form` submit handler — R: `tournamentSelectedSize`, `editingTournamentId`, `activeTournamentId`; W: `pendingNumMatches`, `pendingTournamentId` (dead)
- `loadTournamentSquadScreen` — W: `activeTournamentId`, `pendingPositionChanges`, `activeTournamentData`, `cachedSquadPlayers`; R: `editingTournamentId`
- pos-chip click handler — W: `pendingPositionChanges`
- `renderTournamentSquadGuests` — none
- `btn-tournament-squad-back` handler — R: `editingTournamentId`; W: `editingTournamentId`
- `btn-generate-all-matches` handler — R: `activeTournamentData`, `tournamentSelectedSize`, `editingTournamentId`, `pendingPositionChanges`, `activeTournamentId`, `pendingNumMatches`; W: `pendingPositionChanges`, `editingTournamentId`
- `loadTournamentLobby` — W: `activeTournamentId`, `activeTournamentData`
- `btn-edit-tournament` handler — R: `activeTournamentData`; W: `editingTournamentId`, `gameConfigs` today (⚠️ 1b)
- `btn-tournament-stats`/close — R: `activeTournamentId`
- `renderLobbyMatches` — R: `activeTournamentId`; W: `pitchBackContext` (⚠️ 1d)
- `renderLobbyGuests` — none
- `openAddMatchPanel` — W: `activeTournamentStage`
- guest-player-form submit handler — R: `activeTournamentId`
- `btn-generate-tournament-match` handler — R: `activeTournamentData`, `activeTournamentStage`, `activeTournamentId`; W: `pitchBackContext` (⚠️ 1d), `shirtNumbers` today (⚠️ 1c)

---

## 6. Recommended extraction order

Given the dependency direction above (everything depends on state; pitch.js
and setup-form.js don't depend on season/tournament; season.js and
tournament.js both depend on pitch.js's `enterPitchView`):

1. **state.js** — move declarations + add the three new exported helpers
   from §1 (`enterManualAssignMode`, `ensureGameConfigs`,
   `refreshShirtNumbers`) *before* moving any calling code, so every later
   extraction can immediately call the safe version instead of inlining.
2. **pitch.js** — largest, most self-contained (verified: zero cross-module
   write hazards once §1a/§1c call sites are updated to use the new
   helpers). Also owns the `DEF_KEYS`-family constants.
3. **setup-form.js** — small, only depends on state.js.
4. **season.js**, then **tournament.js** — both depend on pitch.js
   (`enterPitchView`) and setup-form.js; do season first since it's simpler,
   use it to validate the pattern, then tournament.
5. **screens.js** — can move any time after state.js; lowest coupling to
   the match-flow modules.

Decide on §1d (the `pitchBackContext`/`activeTournamentId` reset bug) with
the user before or during step 4 — it's a real behavior fix, not a pure
refactor, so it shouldn't land silently inside a "just moving code" commit.
