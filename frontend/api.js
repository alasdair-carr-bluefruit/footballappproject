const BASE = "/api";

// A 401 handler the app can register (auth.js) — invoked when the session has
// expired or is missing so the app can drop back to the login screen. Kept as a
// hook so api.js stays UI-agnostic. Suppressed for the boot probe (see auth.js).
let onUnauthorized = null;
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

// A live match is run from ONE device; when a write is refused because another
// device now holds control (409 `not_controller`), pitch.js drops to the live
// read-only view. Same hook pattern as the 401 handler.
let onLostControl = null;
export function setLostControlHandler(fn) { onLostControl = fn; }

// A random id for THIS browser, sent on every request so the server can tell which
// device is running a live match. Falls back to a per-page-load id if storage is
// blocked (control then simply doesn't survive a reload on that device).
let _deviceId = null;
export function deviceId() {
  if (_deviceId) return _deviceId;
  const fresh = () => (crypto.randomUUID ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`);
  try {
    _deviceId = localStorage.getItem("gaffer_device_id");
    if (!_deviceId) {
      _deviceId = fresh();
      localStorage.setItem("gaffer_device_id", _deviceId);
    }
  } catch (_) {
    _deviceId = fresh();
  }
  return _deviceId;
}

// FastAPI's `detail` is usually a string, but can be a validation list or a
// structured object ({code, message, …}) — always hand callers a readable message.
function errorMessage(detail, fallback) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(d => d.msg).filter(Boolean).join(", ") || fallback;
  return (detail && detail.message) || fallback;
}

async function request(path, options = {}) {
  const init = {
    headers: { "Content-Type": "application/json", "X-Device-Id": deviceId() },
    credentials: "include",  // send/receive the session cookie (multi-user auth)
    ...options,
  };
  if (init.body && typeof init.body === "object") {
    init.body = JSON.stringify(init.body);
  }
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    if (res.status === 401 && onUnauthorized && !init.suppressAuthRedirect) {
      onUnauthorized();
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const error = new Error(errorMessage(err.detail, res.statusText));
    error.status = res.status;  // lets callers branch on e.g. 409 without parsing text
    if (err.detail && typeof err.detail === "object" && !Array.isArray(err.detail)) {
      error.code = err.detail.code;
      error.detail = err.detail;
    }
    if (error.code === "not_controller" && onLostControl) onLostControl(error);
    throw error;
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Auth (multi-user). me() suppresses the 401 redirect — it IS the probe.
  me:            ()      => request("/auth/me", { suppressAuthRedirect: true }),
  redeemInvite:  (body)  => request("/auth/redeem",       { method: "POST", body, suppressAuthRedirect: true }),
  requestLink:   (email) => request("/auth/request-link", { method: "POST", body: { email }, suppressAuthRedirect: true }),
  verifyLogin:   (token) => request("/auth/verify",       { method: "POST", body: { token }, suppressAuthRedirect: true }),
  logout:        ()      => request("/auth/logout",       { method: "POST" }),
  // Account self-service (Settings screen)
  requestEmailChange: (newEmail) => request("/auth/account/request-email-change", { method: "POST", body: { new_email: newEmail } }),
  confirmEmailChange: (token)    => request("/auth/account/confirm-email-change", { method: "POST", body: { token }, suppressAuthRedirect: true }),
  clearAccountData:   ()         => request("/auth/account/clear-data", { method: "POST" }),
  updateName:         (name)     => request("/auth/account/name", { method: "POST", body: { display_name: name } }),
  setPlanEmails:      (on)       => request("/auth/account/notifications", { method: "POST", body: { notify_plans: !!on } }),
  markIntro:          (id)       => request(`/auth/intros/${encodeURIComponent(id)}`, { method: "POST" }),
  unmarkIntro:        (id)       => request(`/auth/intros/${encodeURIComponent(id)}`, { method: "DELETE" }),
  inviteAFriend:      ()         => request("/auth/invite-a-friend", { method: "POST" }),
  reclaimSquad:       (token)    => request("/auth/account/reclaim", { method: "POST", body: { token }, suppressAuthRedirect: true }),

  // Teams (multi-team). Active team = the account's squad_id (from /me).
  getTeams:      ()      => request("/teams"),
  createTeam:    (data)  => request("/teams",              { method: "POST",   body: data || {} }),
  activateTeam:  (id)    => request(`/teams/${id}/activate`, { method: "POST" }),
  deleteTeam:    (id)    => request(`/teams/${id}`,        { method: "DELETE" }),
  // Assistant coaches (T3.2)
  getAssistants:        ()      => request("/teams/assistants"),
  createAssistantInvite:()      => request("/teams/assistant-invite", { method: "POST" }),
  removeAssistant:      (accId) => request(`/teams/assistants/${accId}`, { method: "DELETE" }),
  makeAssistantHead:    (accId) => request(`/teams/assistants/${accId}/make-head`, { method: "POST" }),
  leaveTeam:            (id)    => request(`/teams/${id}/leave`,  { method: "POST" }),
  previewAssistInvite:  (token) => request("/teams/assist-preview", { method: "POST", body: { token }, suppressAuthRedirect: true }),
  joinAsAssistant:      (token) => request("/teams/join",       { method: "POST", body: { token } }),

  // Squad
  getTeamInfo:   ()           => request("/squad/info"),
  updateTeamInfo:(data)       => request("/squad/info",           { method: "PUT",    body: data }),
  updateMatch:   (id, data)   => request(`/matches/${id}`,        { method: "PUT",    body: data }),
  getPlayers:    ()           => request("/squad/players"),
  addPlayer:     (data)       => request("/squad/players",        { method: "POST",   body: data }),
  updatePlayer:  (id, data)   => request(`/squad/players/${id}`,  { method: "PUT",    body: data }),
  deletePlayer:  (id)         => request(`/squad/players/${id}`,  { method: "DELETE" }),

  // Matches
  getMatches:        ()   => request("/matches/"),
  createMatch:       (d)  => request("/matches/",              { method: "POST",   body: d }),
  getMatch:          (id) => request(`/matches/${id}`),
  generateRotation:  (id, body) => request(`/matches/${id}/rotation`, { method: "POST", body: body || {} }),
  blankRotation:     (id, body) => request(`/matches/${id}/blank-rotation`, { method: "POST", body: body || {} }),
  adjustRotation:    (id, edits, lockedSlots) => request(`/matches/${id}/adjust`, { method: "POST", body: { edits, locked_slots: lockedSlots } }),
  startMatch:        (id) => request(`/matches/${id}/start`,    { method: "POST" }),
  unstartMatch:      (id) => request(`/matches/${id}/unstart`,  { method: "POST" }),
  updateProgress:    (id, slot, status) => request(`/matches/${id}/progress`, { method: "POST", body: { current_slot: slot, ...(status ? { status } : {}) } }),
  removePlayer:      (id, playerId, fromSlot) => request(`/matches/${id}/remove-player`, { method: "POST", body: { player_id: playerId, from_slot: fromSlot } }),
  reinstatePlayer:   (id, playerId) => request(`/matches/${id}/reinstate-player`, { method: "POST", body: { player_id: playerId } }),
  deleteMatch:       (id) => request(`/matches/${id}`,          { method: "DELETE" }),
  // Matchday control + server clock, and the head coach's plan actions
  takeControl:       (id) => request(`/matches/${id}/take-control`, { method: "POST" }),
  setTimer:          (id, running, elapsedMs) => request(`/matches/${id}/timer`, { method: "PUT", body: { running, elapsed_ms: elapsedMs } }),
  reviewMatch:       (id, reviewed) => request(`/matches/${id}/review`, { method: "POST", body: { reviewed } }),
  setMatchOwner:     (id, accountId) => request(`/matches/${id}/owner`, { method: "PUT", body: { account_id: accountId } }),
  saveGoals:         (id, goals, opponentGoals, hideScore, ownGoals) => request(`/matches/${id}/goals`, { method: "POST", body: { goals, opponent_goals: opponentGoals || 0, ...(ownGoals == null ? {} : { own_goals: ownGoals }), ...(hideScore == null ? {} : { hide_score: hideScore ? 1 : 0 }) } }),
  getSeasonStats:    ()   => request("/matches/stats/season"),
  getOwedTime:       ()   => request("/matches/stats/owed"),
  getPlayerHistory:  (id) => request(`/matches/stats/player/${id}`),

  // Config
  getGameConfigs:    ()   => request("/matches/config/game-configs"),

  // Tournaments
  getTournaments:       ()        => request("/tournaments/"),
  createTournament:     (data)    => request("/tournaments/",             { method: "POST",   body: data }),
  getTournament:        (id)      => request(`/tournaments/${id}`),
  deleteTournament:     (id)      => request(`/tournaments/${id}`,        { method: "DELETE" }),
  reviewTournament:     (id, reviewed) => request(`/tournaments/${id}/review`, { method: "POST", body: { reviewed } }),
  setTournamentOwner:   (id, accountId) => request(`/tournaments/${id}/owner`, { method: "PUT", body: { account_id: accountId } }),
  addTournamentMatch:   (id, data)=> request(`/tournaments/${id}/matches`,{ method: "POST",   body: data }),
  addTournamentMatchesBatch: (id, data) => request(`/tournaments/${id}/matches/batch`, { method: "POST", body: data }),
  addGuestPlayer:       (id, data)=> request(`/tournaments/${id}/players`,{ method: "POST",   body: data }),
  removeGuestPlayer:    (id, pid) => request(`/tournaments/${id}/players/${pid}`, { method: "DELETE" }),
  getTournamentStats:   (id)      => request(`/tournaments/${id}/stats`),
  getAllTournamentStats: ()       => request("/tournaments/stats/all"),
  updateTournament:     (id, data)=> request(`/tournaments/${id}`,        { method: "PUT",    body: data }),
  setAvailablePlayers:   (id, ids)      => request(`/tournaments/${id}/set-available-players`, { method: "POST", body: { available_player_ids: ids } }),
  setPositionOverrides:  (id, overrides) => request(`/tournaments/${id}/set-position-overrides`, { method: "POST", body: { overrides } }),
  updateMatchOpponent:   (tid, mid, name) => request(`/tournaments/${tid}/matches/${mid}/opponent`, { method: "PATCH", body: { opponent: name } }),

  // Feedback
  submitFeedback:        (description, context) => request("/feedback/", { method: "POST", body: { description, context } }),
};
