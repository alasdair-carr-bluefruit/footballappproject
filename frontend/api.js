const BASE = "/api";

async function request(path, options = {}) {
  const init = { headers: { "Content-Type": "application/json" }, ...options };
  if (init.body && typeof init.body === "object") {
    init.body = JSON.stringify(init.body);
  }
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // Squad
  getTeamInfo:   ()           => request("/squad/info"),
  updateTeamInfo:(data)       => request("/squad/info",           { method: "PUT",    body: data }),
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
  saveGoals:         (id, goals, opponentGoals) => request(`/matches/${id}/goals`, { method: "POST", body: { goals, opponent_goals: opponentGoals || 0 } }),
  getSeasonStats:    ()   => request("/matches/stats/season"),
  getPlayerHistory:  (id) => request(`/matches/stats/player/${id}`),

  // Config
  getGameConfigs:    ()   => request("/matches/config/game-configs"),

  // Tournaments
  getTournaments:       ()        => request("/tournaments/"),
  createTournament:     (data)    => request("/tournaments/",             { method: "POST",   body: data }),
  getTournament:        (id)      => request(`/tournaments/${id}`),
  deleteTournament:     (id)      => request(`/tournaments/${id}`,        { method: "DELETE" }),
  addTournamentMatch:   (id, data)=> request(`/tournaments/${id}/matches`,{ method: "POST",   body: data }),
  addGuestPlayer:       (id, data)=> request(`/tournaments/${id}/players`,{ method: "POST",   body: data }),
  removeGuestPlayer:    (id, pid) => request(`/tournaments/${id}/players/${pid}`, { method: "DELETE" }),
  getTournamentStats:   (id)      => request(`/tournaments/${id}/stats`),
  updateTournament:     (id, data)=> request(`/tournaments/${id}`,        { method: "PUT",    body: data }),
  setAvailablePlayers:   (id, ids)      => request(`/tournaments/${id}/set-available-players`, { method: "POST", body: { available_player_ids: ids } }),
  setPositionOverrides:  (id, overrides) => request(`/tournaments/${id}/set-position-overrides`, { method: "POST", body: { overrides } }),
  updateMatchOpponent:   (tid, mid, name) => request(`/tournaments/${tid}/matches/${mid}/opponent`, { method: "PATCH", body: { opponent: name } }),

  // Feedback
  submitFeedback:        (description, context) => request("/feedback/", { method: "POST", body: { description, context } }),
};
