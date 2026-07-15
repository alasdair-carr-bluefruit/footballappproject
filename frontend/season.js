import { api } from "./api.js";
import { state, ensureGameConfigs, displayPos } from "./state.js";
import { showScreen, enterManualAssignMode, openMatch, enterReviewView } from "./pitch.js";
import { selectSize, selectPeriods, updateFairnessLabel, getRotationValue } from "./setup-form.js";
import { showToast } from "./toast.js";
import { exportSpreadsheet } from "./share.js";

// ── Home screen ───────────────────────────────────────────────────────────────
async function loadHome() {
  showScreen("screen-home");
  const list = document.getElementById("match-list");
  list.innerHTML = "<li class='loading'>Loading…</li>";

  let matches;
  try {
    matches = await api.getMatches();
  } catch {
    // A connection failure (offline, or the server still spinning up) is NOT the
    // same as "no matches" — say so and offer a retry instead of a misleading
    // empty list.
    list.innerHTML = "<li class='empty-state'>Couldn't reach the server — check your connection.</li>";
    showToast("Connection lost — couldn't load your matches.", {
      actionLabel: "Retry", action: () => loadHome(),
    });
    return;
  }
  list.innerHTML = "";

  if (matches.length === 0) {
    list.innerHTML = "<li class='empty-state'>No matches yet — tap New Match to start</li>";
    return;
  }

  matches.forEach(m => {
    const date = new Date(m.date + "T12:00:00");
    const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    const opponent = m.opponent || "Unknown opponent";
    const sizeBadge = `<span class="match-badge size-badge">${m.team_size || 5}v${m.team_size || 5}</span>`;

    let statusBadge = "";
    if (m.status === "completed") {
      const isHome = (m.home_away || "home") === "home";
      const ourG = m.our_goals || 0;
      const oppG = m.opponent_goals || 0;
      const homeScore = isHome ? ourG : oppG;
      const awayScore = isHome ? oppG : ourG;
      statusBadge = `<span class="match-badge match-badge-done">FT ${homeScore}–${awayScore}</span>`;
    } else if (m.status === "in_progress") {
      statusBadge = `<span class="match-badge match-badge-live">● Live</span>`;
    } else if (!m.has_rotation) {
      statusBadge = `<span class="match-badge">No rotation</span>`;
    }

    const li = document.createElement("li");
    li.className = "match-item";
    if (m.status === "completed") li.classList.add("match-item-done");
    // Planned matches can be re-edited (mirrors the tournament edit pencil); a
    // live/finished match's settings are frozen.
    const editBtn = m.status === "planned"
      ? `<button class="btn-icon match-edit" title="Edit match">✎</button>` : "";
    li.innerHTML = `
      <div class="match-item-main">
        <span class="match-item-date">${dateStr}</span>
        <span class="match-item-opponent">vs ${opponent}</span>
        ${sizeBadge}
        ${statusBadge}
      </div>
      ${editBtn}
      <button class="btn-icon match-delete" data-id="${m.id}" title="Delete match">✕</button>
    `;
    li.querySelector(".match-item-main").addEventListener("click", () => openMatch(m.id));
    li.querySelector(".match-edit")?.addEventListener("click", e => {
      e.stopPropagation();
      openEditMatch(m);
    });
    li.querySelector(".match-delete").addEventListener("click", async e => {
      e.stopPropagation();
      if (confirm(`Delete match vs ${opponent}?`)) {
        try {
          await api.deleteMatch(m.id);
          loadHome();
        } catch (err) {
          alert("Could not delete match: " + err.message);
        }
      }
    });
    list.appendChild(li);
  });
}

document.getElementById("btn-go-stats").addEventListener("click", loadStats);
document.getElementById("btn-home-back").addEventListener("click", () => showScreen("screen-landing"));

// ── New match screen ──────────────────────────────────────────────────────────
document.getElementById("btn-new-match-back").addEventListener("click", loadHome);

document.getElementById("btn-go-new-match").addEventListener("click", async () => {
  state.editingMatchId = null;
  document.getElementById("new-match-title").textContent = "New Match";
  document.getElementById("match-date").value = new Date().toISOString().split("T")[0];
  document.getElementById("opponent-input").value = "";
  document.getElementById("match-show-timer").checked = true;
  document.getElementById("btn-generate").disabled = false;
  document.getElementById("btn-generate").textContent = "Generate Rotation ▶";
  document.getElementById("fairness-slider").value = 0;
  updateFairnessLabel(0);
  // Reset rotation to All-rounder (default)
  const defRotRadio = document.querySelector('input[name="rotation"][value="100"]');
  if (defRotRadio) defRotRadio.checked = true;

  await ensureGameConfigs();

  // Set default size selection
  selectSize(5);
  showScreen("screen-new-match");
});

// Edit a planned match — reopen the setup form pre-filled (mirrors the tournament
// edit pencil). On Generate/Manual the match is updated in place, then re-planned.
async function openEditMatch(m) {
  await ensureGameConfigs();
  state.editingMatchId = m.id;
  document.getElementById("new-match-title").textContent = "Edit Match";
  document.getElementById("match-date").value = m.date;
  document.getElementById("opponent-input").value = m.opponent || "";

  state.selectedHomeAway = m.home_away || "home";
  document.querySelectorAll(".ha-btn").forEach(b =>
    b.classList.toggle("active", b.dataset.ha === state.selectedHomeAway));

  // Size rebuilds formation options + default length/periods; then apply the
  // match's own stored structure/length/timer on top.
  selectSize(m.team_size || 5);
  selectPeriods(m.quarters === 2 ? 2 : 4);
  document.getElementById("formation-select").value = m.formation;
  document.getElementById("match-length").value = String(m.quarter_length_mins ?? 10);
  document.getElementById("match-show-timer").checked = m.show_timer !== 0;

  document.getElementById("fairness-slider").value = m.fairness_value || 0;
  updateFairnessLabel(m.fairness_value || 0);
  const rot = String(m.rotation_intensity ?? 100);
  const rotRadio = document.querySelector(`input[name="rotation"][value="${rot}"]`)
    || document.querySelector('input[name="rotation"][value="100"]');
  if (rotRadio) rotRadio.checked = true;

  document.getElementById("btn-generate").disabled = false;
  document.getElementById("btn-generate").textContent = "Generate Rotation ▶";
  showScreen("screen-new-match");
}

document.getElementById("home-away-picker").addEventListener("click", e => {
  const btn = e.target.closest(".ha-btn");
  if (!btn) return;
  state.selectedHomeAway = btn.dataset.ha;
  document.querySelectorAll(".ha-btn").forEach(b => b.classList.toggle("active", b === btn));
});

// Step 1: Config form → player selection screen
document.getElementById("btn-select-players").addEventListener("click", async () => {
  const date = document.getElementById("match-date").value || new Date().toISOString().split("T")[0];
  const opponent = document.getElementById("opponent-input").value.trim();
  const formation = document.getElementById("formation-select").value;
  const fairnessVal = parseInt(document.getElementById("fairness-slider").value);
  const fairness = fairnessVal <= 15 ? "equal" : "competitive";
  const rotation_intensity = getRotationValue();
  const halves = state.selectedPeriods === 2;
  const lengthDefault = halves ? 30 : 10;
  const maxLen = halves ? 45 : 22.5;
  const lengthVal = parseFloat(document.getElementById("match-length").value);
  if (Number.isFinite(lengthVal) && lengthVal > maxLen) {
    alert(`Minutes per ${halves ? "half" : "quarter"} can't be more than ${maxLen}.`);
    document.getElementById("match-length").focus();
    return;
  }
  const quarter_length_mins = Number.isFinite(lengthVal) && lengthVal > 0 ? lengthVal : lengthDefault;
  const show_timer = document.getElementById("match-show-timer").checked ? 1 : 0;

  state.pendingMatchConfig = {
    date, opponent, team_size: state.selectedSize, formation,
    fairness, fairness_value: fairnessVal, rotation_intensity,
    home_away: state.selectedHomeAway,
    quarters: state.selectedPeriods,
    quarter_length_mins,
    show_timer,
  };

  const players = await api.getPlayers().catch(() => []);
  const list = document.getElementById("avail-list");
  list.innerHTML = "";
  players.forEach(p => {
    const li = document.createElement("li");
    li.className = "avail-item";
    li.innerHTML = `
      <label class="avail-label">
        <input type="checkbox" value="${p.id}" checked />
        <span class="avail-name">${p.name}</span>
      </label>
    `;
    list.appendChild(li);
  });

  showScreen("screen-match-squad");
});

// Back from player selection to config
document.getElementById("btn-match-squad-back").addEventListener("click", () => {
  showScreen("screen-new-match");
});

// Create a new match, or update the one being edited, and return its id.
async function persistMatchConfig() {
  if (state.editingMatchId) {
    await api.updateMatch(state.editingMatchId, state.pendingMatchConfig);
    return state.editingMatchId;
  }
  const match = await api.createMatch(state.pendingMatchConfig);
  return match.id;
}

// Step 2: Generate with selected players
document.getElementById("btn-generate").addEventListener("click", async () => {
  const btn = document.getElementById("btn-generate");
  btn.disabled = true;
  btn.textContent = "Generating…";

  const selectedIds = [...document.querySelectorAll("#avail-list input:checked")].map(
    cb => parseInt(cb.value)
  );

  try {
    const matchId = await persistMatchConfig();
    const data = await api.generateRotation(matchId, { available_player_ids: selectedIds });
    state.editingMatchId = null;
    btn.disabled = false;
    btn.textContent = "Generate Rotation ▶";
    enterReviewView(data);
  } catch (err) {
    alert("Error: " + err.message);
    btn.disabled = false;
    btn.textContent = "Generate Rotation ▶";
  }
});

// Manual slot assignment — blank rotation, all slots empty, tinkering mode on
document.getElementById("btn-manual-slots").addEventListener("click", async () => {
  const btn = document.getElementById("btn-manual-slots");
  btn.disabled = true;
  btn.textContent = "Setting up…";

  const selectedIds = [...document.querySelectorAll("#avail-list input:checked")].map(
    cb => parseInt(cb.value)
  );

  try {
    const matchId = await persistMatchConfig();
    const data = await api.blankRotation(matchId, { available_player_ids: selectedIds });
    state.editingMatchId = null;
    btn.disabled = false;
    btn.textContent = "or assign positions manually";
    enterManualAssignMode(data);
  } catch (err) {
    alert("Error: " + err.message);
    btn.disabled = false;
    btn.textContent = "or assign positions manually";
  }
});

// Prevent actual form submission
document.getElementById("new-match-form").addEventListener("submit", e => e.preventDefault());

// ── Stats screen ──────────────────────────────────────────────────────────────
document.getElementById("btn-stats-back").addEventListener("click", loadHome);
document.getElementById("btn-export-stats").addEventListener("click", () =>
  exportSpreadsheet("/matches/export/season.xlsx", { fallbackName: "season-stats.xlsx", title: "Season Stats" }),
);

async function loadStats() {
  showScreen("screen-stats");
  const list = document.getElementById("stats-list");
  list.innerHTML = "<li class='loading'>Loading…</li>";
  document.getElementById("btn-export-stats").hidden = true;

  const stats = await api.getSeasonStats().catch(() => []);
  list.innerHTML = "";

  if (stats.length === 0) {
    list.innerHTML = "<li class='empty-state'>No stats yet — play some matches first</li>";
    return;
  }
  document.getElementById("btn-export-stats").hidden = false;

  const header = document.createElement("li");
  header.className = "stats-header";
  header.innerHTML = `
    <span class="stats-name">Player</span>
    <span class="stats-col">Matches</span>
    <span class="stats-col">Slots</span>
    <span class="stats-col">Goals</span>
  `;
  list.appendChild(header);

  stats.forEach(s => {
    const li = document.createElement("li");
    li.className = "stats-row stats-row-tap";
    li.innerHTML = `
      <span class="stats-name">${s.name}</span>
      <span class="stats-col">${s.matches_available}</span>
      <span class="stats-col">${s.slots_played}</span>
      <span class="stats-col">${s.goals || "–"}</span>
      <span class="stats-chevron">›</span>
    `;
    li.addEventListener("click", () => loadPlayerHistory(s.id, s.name));
    list.appendChild(li);
  });
}

// ── Player history screen ─────────────────────────────────────────────────────
document.getElementById("btn-history-back").addEventListener("click", loadStats);

async function loadPlayerHistory(playerId, playerName) {
  showScreen("screen-player-history");
  document.getElementById("history-player-name").textContent = playerName;
  document.getElementById("history-totals").innerHTML = "<div class='loading'>Loading…</div>";
  document.getElementById("history-list").innerHTML = "";

  const data = await api.getPlayerHistory(playerId).catch(() => null);
  if (!data) {
    document.getElementById("history-totals").innerHTML = "<div class='empty-state'>Could not load history</div>";
    return;
  }

  const t = data.totals;
  const posEntries = Object.entries(t.positions).filter(([, n]) => n > 0);
  const posHtml = posEntries.map(([pos, n]) =>
    `<span class="history-pos-badge pos-${pos.toLowerCase()}">${displayPos(pos)} ×${n}</span>`
  ).join("");

  document.getElementById("history-totals").innerHTML = `
    <div class="history-total-grid">
      <div class="history-stat"><span class="history-stat-val">${t.matches_available}</span><span class="history-stat-lbl">Matches</span></div>
      <div class="history-stat"><span class="history-stat-val">${t.slots_played}</span><span class="history-stat-lbl">Slots</span></div>
      <div class="history-stat"><span class="history-stat-val">${t.goals}</span><span class="history-stat-lbl">Goals</span></div>
    </div>
    ${posHtml ? `<div class="history-pos-row">${posHtml}</div>` : ""}
  `;

  const list = document.getElementById("history-list");
  if (data.matches.length === 0) {
    list.innerHTML = "<li class='empty-state'>No matches played yet</li>";
    return;
  }

  data.matches.forEach(m => {
    const date = new Date(m.date + "T12:00:00");
    const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
    const posChips = m.positions.map(pos =>
      `<span class="slot-chip pos-${pos.toLowerCase()}">${displayPos(pos)}</span>`
    ).join("");
    const goalsHtml = m.goals > 0 ? `<span class="history-match-goals">⚽ ${m.goals}</span>` : "";

    const li = document.createElement("li");
    li.className = "history-match-row";
    li.innerHTML = `
      <div class="history-match-header">
        <span class="history-match-date">${dateStr}</span>
        <span class="history-match-opp">vs ${m.opponent}</span>
        ${goalsHtml}
        <span class="history-match-slots">${m.slots_played} slot${m.slots_played !== 1 ? "s" : ""}</span>
      </div>
      <div class="history-match-pos">${posChips || "<span class='history-bench'>Did not play</span>"}</div>
    `;
    list.appendChild(li);
  });
}

export { loadHome };
