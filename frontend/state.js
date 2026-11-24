import { api } from "./api.js";

// ── Shared mutable state ────────────────────────────────────────────────────
// Single mutable object rather than individual `export let` bindings: ES
// module imports are read-only live bindings, so any module that needs to
// *reassign* (not just read) a piece of state would otherwise need its own
// setter function per variable. Property mutation on an imported object is
// always safe from any module, so every consumer just does `state.x = y`.
export const state = {
  currentSlot: 0, // slot currently being VIEWED (free to browse in a live match)
  liveSlot: 0, // first slot of the period actually in play; only advances on explicit "start period"
  showingReport: false,
  showingChanges: false,
  editMode: false,
  showSkillRow: true, // plan grid skill-balance row (owner: on by default)
  matchStarted: false, // true once "Start Match" has been tapped
  lockedSlots: new Set(), // slot indices locked by coach edits
  pendingSwap: null, // {slotIndex, posKey, currentPlayerName}
  dragState: null, // {slotIndex, posKey, playerName} for drag-and-drop
  matchData: null, // { match, slots, warnings }
  goalCounts: {}, // { playerName: count }
  ownGoals: 0, // opposition own goals this match (count for us, no named scorer)
  reportEditUnlocked: false, // coach opted in to editing a finished match's goals
  gameConfigs: null, // cached from /api/matches/config/game-configs
  selectedSize: 5,
  selectedHomeAway: "home",
  selectedPeriods: 4,
  manualRotationMode: false,
  teamInfo: { team_name: "My Team", team_logo: "" }, // cached squad info
  shirtNumbers: {}, // { playerName: shirtNumber } — populated from squad API
  removedPlayers: {}, // { playerId: fromSlot } — players removed mid-match
  pendingActionPlayer: null, // { id, name } for player-action overlay
  pendingDeletePlayerId: null, // player id awaiting delete confirmation
  pitchBackContext: "season", // "season" | "tournament" — where pitch back button goes
  squadBackContext: "landing", // "landing" | "season" — where squad back button goes
  activeTournamentId: null, // tournament currently open in lobby
  activeTournamentStage: "group", // "group" | "knockout" — for add-match panel
  pendingPositionChanges: {}, // { playerId: [positions] } — tournament squad screen overrides
  cachedSquadPlayers: [], // full player objects cached during tournament squad screen
  lastQuipIndex: -1,
  pendingMatchConfig: null, // stored between config step and player selection step
  editingPlayerId: null,
  timerInterval: null,
  newPeriodHintSlot: null, // slot for which the "reset clock?" prompt was handled
  tournamentSelectedSize: 5,
  activeTournamentData: null, // full detail from GET /tournaments/{id}
  pendingNumMatches: 4,
  editingTournamentId: null, // null = creating new, set = editing existing
  editingMatchId: null, // season match being edited (null = creating a new match)
  account: null, // /me payload (auth on): { email, squad_id, auth_enabled, ... }
  teams: [], // multi-team: list from GET /api/teams
  activeSquadId: null, // multi-team: the account's active squad id
  role: "head", // caller's role on the ACTIVE team: "head" | "assistant" (T3.2)
  planEditable: true, // may the caller edit/run the match or tournament now open? (server's can_edit)
  watching: false, // viewing a LIVE match another device is running (read-only, polled)
  controller: null, // { name, is_me, same_account } for the live match open, or null
  assistants: null, // head coach only: cached GET /teams/assistants for the hand-over picker
  planTinkered: false, // coach has adjusted this plan — sets the plan-flag tone
  reviewShare: null, // { blocks:[{md,title}], heading, subheading, filename, shareTitle } for the review screen's Share button
};

// Shared across season.js + tournament.js (both need the formation/team-size
// config payload). Consolidates 3 identical inline fetch-and-cache blocks.
// Map any position code (granular real code OR normalized band) to the
// simplified display label the coach sees: DEF / MID / ATT / GK. Display only —
// stored values and CSS `pos-*` colour classes keep using the normalized band.
const _DISP_DEF = new Set(["DEF", "LB", "CB", "CB2", "RB"]);
const _DISP_MID = new Set(["MID", "LM", "CM", "CM2", "RM", "CAM"]);
const _DISP_FWD = new Set(["FWD", "ATT", "LW", "CF", "CF2", "RW"]);
// ── Granular positions (squad toggle) — mirrors backend/models/rotation.py ────
// Picks are stored as given (bands and/or LB/CB/RB…); the toggle only changes how
// they're read, so switching it off and on again loses nothing.
export const GRANULAR_GROUPS = [
  { band: "DEF", picks: ["LB", "CB", "RB"] },
  { band: "MID", picks: ["LM", "CM", "CAM", "RM"] },
  { band: "FWD", picks: ["LW", "CF", "RW"] },
];
const _GRAN_ALIAS = { CB2: "CB", CM2: "CM", CF2: "CF" };
export const isGranular = () => !!(state.teamInfo && state.teamInfo.granular_positions);
export const granularPos = pos => _GRAN_ALIAS[pos] || pos;
export function bandOf(pos) {
  if (_DISP_DEF.has(pos)) return "DEF";
  if (_DISP_MID.has(pos)) return "MID";
  if (_DISP_FWD.has(pos)) return "FWD";
  return pos;
}
// Variety/compare key: the granular position when on, else the band.
export const posType = pos => (isGranular() ? granularPos(pos) : bandOf(pos));
// Do these picks cover this slot? Empty = happy anywhere; a band pick covers its band.
export function picksAllow(picks, pos) {
  if (!picks || !picks.length) return true;
  const band = bandOf(pos);
  if (picks.includes(band)) return true;
  if (isGranular()) return picks.includes(granularPos(pos));
  return picks.some(p => bandOf(p) === band);
}
// Picks as the coach should see them right now (bands, de-duped, when off).
export function picksLabel(picks) {
  return isGranular() ? [...picks] : [...new Set(picks.map(bandOf))];
}

export function displayPos(pos) {
  // Granular on: show the real position (CB2 → CB); band picks still read DEF/MID/ATT.
  if (isGranular() && bandOf(pos) !== pos && !["DEF", "MID", "FWD", "ATT"].includes(pos)) {
    return granularPos(pos);
  }
  if (_DISP_DEF.has(pos)) return "DEF";
  if (_DISP_MID.has(pos)) return "MID";
  if (_DISP_FWD.has(pos)) return "ATT";
  return pos; // GK and anything else pass through
}

export async function ensureGameConfigs() {
  if (!state.gameConfigs) {
    state.gameConfigs = await api.getGameConfigs().catch(() => null);
  }
  return state.gameConfigs;
}

// Shared across pitch.js + screens.js + tournament.js (all three rebuilt
// this map from scratch with identical inline code). Always resets the map
// on call (even on fetch failure) — matches loadSquad's original semantics.
export async function refreshShirtNumbers() {
  const players = await api.getPlayers().catch(() => []);
  state.shirtNumbers = {};
  players.forEach(p => { if (p.shirt_number != null) state.shirtNumbers[p.name] = p.shirt_number; });
  return players;
}

// Multi-team: reload the account's team list + active id. No-op (empty list) when
// auth is off or the fetch fails, so the switcher simply doesn't render.
export async function refreshTeams() {
  if (!state.account?.auth_enabled) { state.teams = []; return state.teams; }
  const teams = await api.getTeams().catch(() => []);
  state.teams = teams;
  const active = teams.find(t => t.is_active);
  state.activeSquadId = active ? active.id : (state.account?.squad_id ?? null);
  if (active) setRole(active.role);
  return teams;
}

// ── Roles → capabilities (T3.2 assistant coach mode) ─────────────────────────
// Mirrors backend/api/deps.py ROLE_CAPS. The server is the authority (every write
// 403s for an assistant); this only decides what the UI offers. Anything the
// assistant can't do is hidden via `body.role-assistant .head-only` in style.css.
const ROLE_CAPS = {
  head: new Set(["view", "author_plan", "run_matchday", "comment", "propose", "edit_plan", "manage_squad", "manage_team"]),
  assistant: new Set(["view", "author_plan"]),
};
// "edit_plan" / "run_matchday" are per plan: the head coach always can; an assistant
// can only on a match/tournament they created. The server says which via `can_edit`
// on every match/tournament payload → setPlanEditable() below.
const PER_PLAN_CAPS = new Set(["edit_plan", "run_matchday"]);

export function can(cap) {
  if (PER_PLAN_CAPS.has(cap)) return state.planEditable;
  return (ROLE_CAPS[state.role] || ROLE_CAPS.head).has(cap);
}

// Call whenever a match / tournament is opened (with its `can_edit`), and with `true`
// when returning to a list (creating a new plan is open to assistants). Controls that
// change a plan carry `.editor-only` and vanish while the open plan is read-only.
export function setPlanEditable(editable) {
  state.planEditable = editable !== false;
  document.body.classList.toggle("plan-readonly", !state.planEditable);
}

export function isAssistant() {
  return state.role === "assistant";
}

export function setRole(role) {
  state.role = role === "assistant" ? "assistant" : "head";
  document.body.classList.toggle("role-assistant", state.role === "assistant");
  setPlanEditable(true);
}
