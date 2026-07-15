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
  matchStarted: false, // true once "Start Match" has been tapped
  lockedSlots: new Set(), // slot indices locked by coach edits
  pendingSwap: null, // {slotIndex, posKey, currentPlayerName}
  dragState: null, // {slotIndex, posKey, playerName} for drag-and-drop
  matchData: null, // { match, slots, warnings }
  goalCounts: {}, // { playerName: count }
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
};

// Shared across season.js + tournament.js (both need the formation/team-size
// config payload). Consolidates 3 identical inline fetch-and-cache blocks.
// Map any position code (granular real code OR normalized band) to the
// simplified display label the coach sees: DEF / MID / ATT / GK. Display only —
// stored values and CSS `pos-*` colour classes keep using the normalized band.
const _DISP_DEF = new Set(["DEF", "LB", "CB", "CB2", "RB"]);
const _DISP_MID = new Set(["MID", "LM", "CM", "CM2", "RM", "CAM"]);
const _DISP_FWD = new Set(["FWD", "ATT", "LW", "CF", "CF2", "RW"]);
export function displayPos(pos) {
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
