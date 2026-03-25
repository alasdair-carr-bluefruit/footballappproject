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
  getPlayers:    ()           => request("/squad/players"),
  addPlayer:     (data)       => request("/squad/players",       { method: "POST",   body: data }),
  updatePlayer:  (id, data)   => request(`/squad/players/${id}`, { method: "PUT",    body: data }),
  deletePlayer:  (id)         => request(`/squad/players/${id}`, { method: "DELETE" }),

  // Matches
  getMatches:        ()   => request("/matches/"),
  createMatch:       (d)  => request("/matches/",              { method: "POST",   body: d }),
  getMatch:          (id) => request(`/matches/${id}`),
  generateRotation:  (id) => request(`/matches/${id}/rotation`, { method: "POST" }),
  deleteMatch:       (id) => request(`/matches/${id}`,          { method: "DELETE" }),
};
