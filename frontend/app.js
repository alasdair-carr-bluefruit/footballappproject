import { api } from "./api.js";

// ── State ─────────────────────────────────────────────────────────────────────
let currentSlot = 0;
let showingReport = false;
let showingChanges = false;
let editMode = false;
let matchStarted = false; // true once "Start Match" has been tapped
let lockedSlots = new Set(); // slot indices locked by coach edits
let pendingSwap = null; // {slotIndex, posKey, currentPlayerName}
let dragState = null; // {slotIndex, posKey, playerName} for drag-and-drop
let matchData = null; // { match, slots, warnings }
const goalCounts = {}; // { playerName: count }
let gameConfigs = null; // cached from /api/matches/config/game-configs
let selectedSize = 5;
let selectedHomeAway = "home";
let teamInfo = { team_name: "My Team", team_logo: "" }; // cached squad info
let shirtNumbers = {}; // { playerName: shirtNumber } — populated from squad API
let removedPlayers = {}; // { playerId: fromSlot } — players removed mid-match
let pendingActionPlayer = null; // { id, name } for player-action overlay
let pendingDeletePlayerId = null; // player id awaiting delete confirmation
let pitchBackContext = "season"; // "season" | "tournament" — where pitch back button goes
let squadBackContext = "landing"; // "landing" | "season" — where squad back button goes
let activeTournamentId = null; // tournament currently open in lobby
let activeTournamentStage = "group"; // "group" | "knockout" — for add-match panel

// Returns true if this player's shirt number is shared and they are the LATER entry
// (i.e. the "duplicate" — their number shows in red)
function isShirtConflict(name) {
  const num = shirtNumbers[name];
  if (num == null) return false;
  const allNames = Object.keys(shirtNumbers);
  const firstOwner = allNames.find(n => shirtNumbers[n] === num);
  return firstOwner !== name;
}

// ── Screen management ─────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => { s.hidden = true; });
  document.getElementById(id).hidden = false;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function parseFormation(notation) {
  const [d, m, f] = notation.split("-").map(Number);
  return { defense: d, midfield: m, forward: f };
}

const DEF_KEYS = { 1: ["CB"], 2: ["CB","CB2"], 3: ["LB","CB","RB"], 4: ["LB","CB","CB2","RB"] };
const MID_KEYS = { 1: ["CM"], 2: ["LM","RM"], 3: ["LM","CM","RM"], 4: ["LM","CM","CM2","RM"], 5: ["LM","CM","CM2","RM","CAM"] };
const FWD_KEYS = { 1: ["CF"], 2: ["CF","CF2"], 3: ["LW","CF","RW"] };
const _DEF_SET = new Set(["LB","CB","CB2","RB"]);
const _MID_SET = new Set(["LM","CM","CM2","RM","CAM"]);
const _FWD_SET = new Set(["LW","CF","CF2","RW"]);

function formationPositions(notation) {
  const { defense, midfield, forward } = parseFormation(notation);
  return [...(DEF_KEYS[defense] || []), ...(MID_KEYS[midfield] || []), ...(FWD_KEYS[forward] || [])];
}

function normalizePos(pos) {
  if (_DEF_SET.has(pos)) return "DEF";
  if (_MID_SET.has(pos)) return "MID";
  if (_FWD_SET.has(pos)) return "FWD";
  return pos;
}

function slotCountForPlayer(playerName) {
  if (!matchData) return 0;
  return matchData.slots.filter(s => Object.values(s.lineup).some(p => p.name === playerName)).length;
}

// Load team info once on startup
api.getTeamInfo().then(info => { if (info) teamInfo = info; }).catch(() => {});

// ── First-launch tutorial ─────────────────────────────────────────────────────
(function initScreen() {
  if (!localStorage.getItem("gaffer_onboarded")) {
    showScreen("screen-tutorial");
  } else {
    showScreen("screen-landing");
  }
})();

// Tutorial logo upload
document.getElementById("tutorial-logo-btn").addEventListener("click", () => {
  document.getElementById("tutorial-logo-input").click();
});
document.getElementById("tutorial-logo-input").addEventListener("change", e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    const img = document.getElementById("tutorial-logo-img");
    img.src = ev.target.result;
    img.hidden = false;
    document.getElementById("tutorial-logo-placeholder").hidden = true;
  };
  reader.readAsDataURL(file);
});

document.getElementById("btn-tutorial-start").addEventListener("click", async () => {
  const name = document.getElementById("tutorial-team-name").value.trim();
  if (!name) {
    document.getElementById("tutorial-team-name").focus();
    return;
  }
  const logoImg = document.getElementById("tutorial-logo-img");
  const logo = logoImg.hidden ? "" : (logoImg.src || "");
  await api.updateTeamInfo({ team_name: name, team_logo: logo }).catch(() => {});
  teamInfo = { team_name: name, team_logo: logo };
  localStorage.setItem("gaffer_onboarded", "1");
  showScreen("screen-landing");
  showSquadTip();
});

function showSquadTip() {
  if (localStorage.getItem("gaffer_squad_tip_dismissed")) return;
  document.getElementById("squad-tip").hidden = false;
  document.getElementById("btn-squad-management").classList.add("mode-card-highlight");
}

document.getElementById("btn-squad-tip-dismiss").addEventListener("click", () => {
  document.getElementById("squad-tip").hidden = true;
  document.getElementById("btn-squad-management").classList.remove("mode-card-highlight");
  localStorage.setItem("gaffer_squad_tip_dismissed", "1");
});

// ── Landing screen ────────────────────────────────────────────────────────────
document.getElementById("btn-season-mode").addEventListener("click", () => loadHome());
document.getElementById("btn-tournament-mode").addEventListener("click", () => loadTournamentHome());
document.getElementById("btn-squad-management").addEventListener("click", () => {
  // Dismiss squad tip once they visit squad management
  document.getElementById("squad-tip").hidden = true;
  document.getElementById("btn-squad-management").classList.remove("mode-card-highlight");
  localStorage.setItem("gaffer_squad_tip_dismissed", "1");
  squadBackContext = "landing";
  loadSquad();
});

// ── Home screen ───────────────────────────────────────────────────────────────
async function loadHome() {
  showScreen("screen-home");
  const list = document.getElementById("match-list");
  list.innerHTML = "<li class='loading'>Loading…</li>";

  const matches = await api.getMatches().catch(() => []);
  list.innerHTML = "";

  const exportBar = document.getElementById("export-bar");
  document.getElementById("export-dropdown").hidden = true;

  if (matches.length === 0) {
    list.innerHTML = "<li class='empty-state'>No matches yet — tap New Match to start</li>";
    exportBar.hidden = true;
    return;
  }

  exportBar.hidden = false;

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
    li.innerHTML = `
      <div class="match-item-main">
        <span class="match-item-date">${dateStr}</span>
        <span class="match-item-opponent">vs ${opponent}</span>
        ${sizeBadge}
        ${statusBadge}
      </div>
      <button class="btn-icon match-delete" data-id="${m.id}" title="Delete match">✕</button>
    `;
    li.querySelector(".match-item-main").addEventListener("click", () => openMatch(m.id));
    li.querySelector(".match-delete").addEventListener("click", async e => {
      e.stopPropagation();
      if (confirm(`Delete match vs ${opponent}?`)) {
        await api.deleteMatch(m.id).catch(err => alert(err.message));
        loadHome();
      }
    });
    list.appendChild(li);
  });
}

function enterPitchView(data) {
  matchData = data;
  showingReport = false;
  showingChanges = false;
  editMode = false;
  lockedSlots = new Set(data.locked_slots || []);
  removedPlayers = data.removed_players || {};
  Object.keys(goalCounts).forEach(k => delete goalCounts[k]);

  // Determine match state
  const status = data.match?.status || "planned";
  matchStarted = status !== "planned";
  currentSlot = matchStarted ? (data.match?.current_slot || 0) : 0;

  showScreen("screen-pitch");
  document.querySelector(".pitch-wrapper").style.display = "";
  document.querySelector(".bench-section").style.display = "";
  document.getElementById("report-section").style.display = "none";

  // Generate progress dots dynamically
  const dotsContainer = document.getElementById("progress-dots");
  dotsContainer.innerHTML = "";
  dotsContainer.style.display = "";
  for (let i = 0; i < matchData.slots.length; i++) {
    const dot = document.createElement("div");
    dot.className = "progress-dot";
    dotsContainer.appendChild(dot);
  }

  render();
}

async function openMatch(matchId) {
  // Ensure shirt numbers are current
  api.getPlayers().then(players => {
    shirtNumbers = {};
    players.forEach(p => { if (p.shirt_number != null) shirtNumbers[p.name] = p.shirt_number; });
  }).catch(() => {});

  const data = await api.getMatch(matchId).catch(err => { alert(err.message); return null; });
  if (!data) return;

  if (!data.slots || data.slots.length === 0) {
    const generated = await api.generateRotation(matchId).catch(err => {
      alert("Could not generate rotation: " + err.message);
      return null;
    });
    if (!generated) return;
    enterPitchView(generated);
  } else {
    enterPitchView(data);
  }
}

document.getElementById("btn-go-new-match").addEventListener("click", async () => {
  document.getElementById("match-date").value = new Date().toISOString().split("T")[0];
  document.getElementById("opponent-input").value = "";
  document.getElementById("btn-generate").disabled = false;
  document.getElementById("btn-generate").textContent = "Generate Rotation ▶";
  document.getElementById("fairness-slider").value = 0;
  updateFairnessLabel(0);
  document.getElementById("rotation-slider").value = 50;
  updateRotationLabel(50);

  // Load game configs if not cached
  if (!gameConfigs) {
    gameConfigs = await api.getGameConfigs().catch(() => null);
  }

  // Set default size selection
  selectSize(5);
  showScreen("screen-new-match");
});

// ── Team size & formation picker ────────────────────────────────────────────
function selectSize(size) {
  selectedSize = size;
  document.querySelectorAll(".size-btn").forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.size) === size);
  });
  updateFormationOptions();
}

function updateFormationOptions() {
  const select = document.getElementById("formation-select");
  select.innerHTML = "";
  if (gameConfigs && gameConfigs[String(selectedSize)]) {
    const cfg = gameConfigs[String(selectedSize)];
    cfg.formations.forEach(f => {
      const opt = document.createElement("option");
      opt.value = f.notation;
      opt.textContent = f.notation;
      if (f.notation === cfg.default_formation) opt.selected = true;
      select.appendChild(opt);
    });
  } else {
    // Fallback for when configs aren't loaded
    const defaults = { 5: "1-2-1", 6: "1-3-1", 7: "2-3-1", 9: "3-3-2", 11: "4-4-2" };
    const opt = document.createElement("option");
    opt.value = defaults[selectedSize] || "1-2-1";
    opt.textContent = opt.value;
    select.appendChild(opt);
  }
}

document.getElementById("size-picker").addEventListener("click", e => {
  const btn = e.target.closest(".size-btn");
  if (btn) selectSize(parseInt(btn.dataset.size));
});

document.getElementById("home-away-picker").addEventListener("click", e => {
  const btn = e.target.closest(".ha-btn");
  if (!btn) return;
  selectedHomeAway = btn.dataset.ha;
  document.querySelectorAll(".ha-btn").forEach(b => b.classList.toggle("active", b === btn));
});

function updateFairnessLabel(value) {
  const el = document.getElementById("fairness-value");
  const warn = document.getElementById("fairness-warning");
  const v = parseInt(value);
  if (v <= 15) el.textContent = "Equal play — everyone gets the same time";
  else if (v <= 40) el.textContent = "Mostly fair — slight edge for stronger players";
  else if (v <= 60) el.textContent = "Balanced — skill matters but everyone plays";
  else if (v <= 85) el.textContent = "Competitive — best players get more time";
  else el.textContent = "Win mode — strongest lineup prioritised";
  warn.hidden = v <= 85;
}

document.getElementById("fairness-slider").addEventListener("input", e => {
  updateFairnessLabel(e.target.value);
});

function updateRotationLabel(value) {
  const el = document.getElementById("rotation-value");
  const v = parseInt(value);
  if (v <= 15) el.textContent = "Specialist — players stay in one position";
  else if (v <= 40) el.textContent = "Mostly fixed — occasional position changes";
  else if (v <= 60) el.textContent = "Balanced — regular position rotation";
  else if (v <= 85) el.textContent = "High rotation — players try most positions";
  else el.textContent = "All-rounder — everyone plays everywhere";
}

document.getElementById("rotation-slider").addEventListener("input", e => {
  updateRotationLabel(e.target.value);
});

// Squad accessible from landing page only (btn-squad-management)
document.getElementById("btn-go-stats").addEventListener("click", loadStats);
document.getElementById("btn-home-back").addEventListener("click", () => showScreen("screen-landing"));

// ── New match screen ──────────────────────────────────────────────────────────
document.getElementById("btn-new-match-back").addEventListener("click", loadHome);

let pendingMatchConfig = null; // stored between config step and player selection step

// Step 1: Config form → show player availability
document.getElementById("btn-select-players").addEventListener("click", async () => {
  const date = document.getElementById("match-date").value || new Date().toISOString().split("T")[0];
  const opponent = document.getElementById("opponent-input").value.trim();
  const formation = document.getElementById("formation-select").value;
  const fairnessVal = parseInt(document.getElementById("fairness-slider").value);
  const fairness = fairnessVal <= 15 ? "equal" : "competitive";
  const rotation_intensity = parseInt(document.getElementById("rotation-slider").value);

  pendingMatchConfig = {
    date, opponent, team_size: selectedSize, formation,
    fairness, fairness_value: fairnessVal, rotation_intensity,
    home_away: selectedHomeAway,
  };

  // Load players and show availability panel
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

  document.getElementById("new-match-form").hidden = true;
  document.getElementById("availability-panel").hidden = false;
});

// Back from availability to config
document.getElementById("btn-avail-back").addEventListener("click", () => {
  document.getElementById("availability-panel").hidden = true;
  document.getElementById("new-match-form").hidden = false;
});

// Step 2: Generate with selected players
document.getElementById("btn-generate").addEventListener("click", async () => {
  const btn = document.getElementById("btn-generate");
  btn.disabled = true;
  btn.textContent = "Generating…";

  const selectedIds = [...document.querySelectorAll("#avail-list input:checked")].map(
    cb => parseInt(cb.value)
  );

  try {
    const match = await api.createMatch(pendingMatchConfig);
    const data = await api.generateRotation(match.id, { available_player_ids: selectedIds });
    // Reset form state
    document.getElementById("availability-panel").hidden = true;
    document.getElementById("new-match-form").hidden = false;
    btn.disabled = false;
    btn.textContent = "Generate Rotation ▶";
    enterPitchView(data);
  } catch (err) {
    alert("Error: " + err.message);
    btn.disabled = false;
    btn.textContent = "Generate Rotation ▶";
  }
});

// Prevent actual form submission
document.getElementById("new-match-form").addEventListener("submit", e => e.preventDefault());

// ── Squad screen ──────────────────────────────────────────────────────────────
let editingPlayerId = null;

async function loadSquad() {
  showScreen("screen-squad");
  closePlayerForm();

  // Populate team info fields
  const info = await api.getTeamInfo().catch(() => null);
  if (info) {
    teamInfo = info;
    document.getElementById("team-name-input").value = info.team_name || "";
    const img = document.getElementById("team-logo-img");
    const placeholder = document.getElementById("team-logo-placeholder");
    if (info.team_logo) {
      img.src = info.team_logo;
      img.hidden = false;
      placeholder.hidden = true;
    } else {
      img.hidden = true;
      placeholder.hidden = false;
    }
  }

  const players = await api.getPlayers().catch(() => []);

  // Rebuild shirt number map and detect conflicts
  shirtNumbers = {};
  const numberCount = {};
  players.forEach(p => {
    if (p.shirt_number != null) {
      shirtNumbers[p.name] = p.shirt_number;
      numberCount[p.shirt_number] = (numberCount[p.shirt_number] || 0) + 1;
    }
  });
  const conflictNumbers = new Set(Object.entries(numberCount).filter(([, n]) => n > 1).map(([k]) => parseInt(k)));

  // Track which conflict number has already been "claimed" (first occurrence = ok, subsequent = red)
  const seenNumbers = new Set();

  const list = document.getElementById("player-list");
  list.innerHTML = "";

  if (players.length === 0) {
    list.innerHTML = "<li class='empty-state'>No players yet</li>";
  }

  players.forEach(p => {
    const badges = [];
    const prefs = p.preferred_positions || [];
    if (prefs.length > 0) {
      prefs.forEach(pos => {
        const isBest = pos === p.best_position;
        const cls = isBest ? "badge badge-pos badge-best" : "badge badge-pos";
        badges.push(`<span class="${cls}">${pos}</span>`);
      });
    } else {
      // Legacy fallback
      if (p.gk_status === "specialist") badges.push('<span class="badge badge-gk">GK</span>');
      if (p.def_restricted) badges.push('<span class="badge badge-def">No DEF</span>');
    }

    let numberBadge = "";
    if (p.shirt_number != null) {
      const isConflict = conflictNumbers.has(p.shirt_number) && seenNumbers.has(p.shirt_number);
      if (conflictNumbers.has(p.shirt_number)) seenNumbers.add(p.shirt_number);
      numberBadge = `<span class="badge badge-number${isConflict ? " badge-number-conflict" : ""}">#${p.shirt_number}</span>`;
    }

    const li = document.createElement("li");
    li.className = "player-item";
    li.innerHTML = `
      <div class="player-item-info">
        <span class="player-item-name">${p.name}</span>
        <span class="player-item-badges">${numberBadge}${badges.join("")}</span>
      </div>
      <div class="player-item-actions">
        <button class="btn-sm" data-edit="${p.id}">Edit</button>
        <button class="btn-sm btn-danger" data-del="${p.id}">✕</button>
      </div>
    `;
    li.querySelector(`[data-edit]`).addEventListener("click", () => openPlayerForm(p));
    li.querySelector(`[data-del]`).addEventListener("click", () => {
      pendingDeletePlayerId = p.id;
      document.getElementById("delete-player-info").textContent =
        `Are you sure you want to remove ${p.name} from your squad? All previous match data including goals scored will be lost.`;
      document.getElementById("delete-player-overlay").hidden = false;
    });
    list.appendChild(li);
  });
}

function openPlayerForm(player = null) {
  editingPlayerId = player?.id ?? null;
  const form = document.getElementById("player-form");
  form.hidden = false;
  document.getElementById("form-title").textContent = player ? "Edit Player" : "Add Player";
  document.getElementById("input-name").value = player?.name ?? "";
  document.getElementById("input-skill").value = player?.skill_rating ?? 3;
  document.getElementById("input-shirt-number").value = player?.shirt_number ?? "";

  // Position checkboxes — derive from preferred_positions or legacy gk_status/def_restricted
  let prefs = player?.preferred_positions || [];
  if (prefs.length === 0 && player) {
    // Backward compat: derive from legacy fields
    if (player.gk_status === "specialist") prefs = ["GK"];
    else {
      prefs = [];
      if (!player.def_restricted) prefs.push("DEF");
      prefs.push("MID", "FWD");
      if (["preferred", "can_play"].includes(player.gk_status)) prefs.push("GK");
    }
  }
  document.querySelectorAll("#position-checkboxes input").forEach(cb => {
    cb.checked = prefs.includes(cb.value);
  });
  updateBestPositionOptions(prefs, player?.best_position || "");

  document.getElementById("input-name").focus();
}

function updateBestPositionOptions(selectedPositions, currentBest) {
  const sel = document.getElementById("input-best-position");
  sel.innerHTML = '<option value="">Not set</option>';
  selectedPositions.forEach(pos => {
    const opt = document.createElement("option");
    opt.value = pos;
    opt.textContent = pos;
    if (pos === currentBest) opt.selected = true;
    sel.appendChild(opt);
  });
}

// Update best position dropdown when checkboxes change
document.getElementById("position-checkboxes").addEventListener("change", () => {
  const checked = [...document.querySelectorAll("#position-checkboxes input:checked")].map(cb => cb.value);
  const currentBest = document.getElementById("input-best-position").value;
  updateBestPositionOptions(checked, checked.includes(currentBest) ? currentBest : "");
});

function closePlayerForm() {
  document.getElementById("player-form").hidden = true;
  editingPlayerId = null;
}

document.getElementById("btn-squad-back").addEventListener("click", () => {
  if (squadBackContext === "landing") showScreen("screen-landing");
  else loadHome();
});

// Team logo file input → preview
document.getElementById("team-logo-input").addEventListener("change", e => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = ev => {
    const dataUrl = ev.target.result;
    const img = document.getElementById("team-logo-img");
    img.src = dataUrl;
    img.hidden = false;
    document.getElementById("team-logo-placeholder").hidden = true;
  };
  reader.readAsDataURL(file);
});

// Save team name + logo
document.getElementById("btn-save-team-info").addEventListener("click", async () => {
  const name = document.getElementById("team-name-input").value.trim() || "My Team";
  const logo = document.getElementById("team-logo-img").hidden ? "" : document.getElementById("team-logo-img").src;
  const btn = document.getElementById("btn-save-team-info");
  btn.textContent = "Saving…";
  try {
    teamInfo = await api.updateTeamInfo({ team_name: name, team_logo: logo });
    btn.textContent = "Saved ✓";
    setTimeout(() => { btn.textContent = "Save"; }, 1500);
  } catch {
    btn.textContent = "Save";
  }
});
document.getElementById("btn-add-player").addEventListener("click", () => openPlayerForm());
document.getElementById("btn-cancel-player").addEventListener("click", closePlayerForm);

document.getElementById("player-form").addEventListener("click", e => {
  if (e.target === e.currentTarget) closePlayerForm();
});

document.querySelector("#player-form form").addEventListener("submit", async e => {
  e.preventDefault();
  const preferred = [...document.querySelectorAll("#position-checkboxes input:checked")].map(cb => cb.value);
  const bestPos = document.getElementById("input-best-position").value;

  // Derive gk_status from position selections
  let gkStatus;
  if (preferred.includes("GK") && preferred.length === 1) {
    gkStatus = "specialist"; // GK only
  } else if (bestPos === "GK") {
    gkStatus = "preferred"; // GK is their best position
  } else if (preferred.includes("GK")) {
    gkStatus = "can_play"; // Can play GK among other positions
  } else {
    gkStatus = "emergency_only"; // GK not selected
  }

  // Derive def_restricted: if positions are specified and DEF isn't among them
  const defRestricted = preferred.length > 0 && !preferred.includes("DEF");

  const shirtRaw = document.getElementById("input-shirt-number").value.trim();
  const data = {
    name:                document.getElementById("input-name").value.trim(),
    gk_status:           gkStatus,
    def_restricted:      defRestricted,
    skill_rating:        parseInt(document.getElementById("input-skill").value, 10),
    preferred_positions: preferred,
    best_position:       bestPos,
    shirt_number:        shirtRaw !== "" ? parseInt(shirtRaw, 10) : null,
  };
  if (!data.name) return;

  const id = editingPlayerId;
  closePlayerForm();

  if (id !== null) {
    await api.updatePlayer(id, data).catch(err => alert(err.message));
  } else {
    await api.addPlayer(data).catch(err => alert(err.message));
  }
  loadSquad();
});

// ── Pitch helpers ─────────────────────────────────────────────────────────────
function slotObj(slotIndex) {
  return matchData.slots[slotIndex];
}

function periodLabel(slotIndex) {
  const label = matchData.match.period_label || "Quarter";
  const short = label === "Half" ? "H" : "Q";
  const p = Math.floor(slotIndex / 2) + 1;
  const h = slotIndex % 2 === 0 ? "a" : "b";
  return { p, h, label: `${short}${p}${h}`, periodLabel: label };
}

function slotPlayerNames(slot) {
  return new Set(Object.values(slot.lineup).map(p => p.name));
}

function incomingSubs(cur, nxt) {
  if (!nxt) return new Set();
  const curNames = slotPlayerNames(cur);
  return new Set(Object.values(nxt.lineup).map(p => p.name).filter(n => !curNames.has(n)));
}

function outgoingSubs(cur, nxt) {
  if (!nxt) return new Set();
  const nxtNames = slotPlayerNames(nxt);
  return new Set(Object.values(cur.lineup).map(p => p.name).filter(n => !nxtNames.has(n)));
}

// ── Pitch rendering ───────────────────────────────────────────────────────────
function playerCircle(name, role, isIncoming, isOutgoing, isGk = false, onSwapClick = null, dragData = null) {
  const div = document.createElement("div");
  div.className = "player-circle tappable";
  if (isIncoming) div.classList.add("incoming");
  if (isGk) div.classList.add("is-gk");

  const goals = goalCounts[name] || 0;
  const shirtNum = shirtNumbers[name];
  const avatarContent = shirtNum != null ? String(shirtNum) : name.slice(0, 3).toUpperCase();
  const avatarConflict = shirtNum != null && isShirtConflict(name) ? " number-conflict" : "";
  div.innerHTML = `
    <div class="circle-avatar${avatarConflict}">${avatarContent}</div>
    <div class="circle-name">${name}</div>
    <div class="circle-role">${role}</div>
  `;

  const avatar = div.querySelector(".circle-avatar");

  if (isGk) {
    const gloves = document.createElement("span");
    gloves.className = "gk-gloves";
    gloves.textContent = "🧤";
    avatar.appendChild(gloves);
  }

  if (isIncoming) {
    const badge = document.createElement("div");
    badge.className = "sub-badge sub-in";
    badge.textContent = "↑";
    avatar.appendChild(badge);
  } else if (isOutgoing) {
    const badge = document.createElement("div");
    badge.className = "sub-badge sub-out";
    badge.textContent = "↓";
    avatar.appendChild(badge);
  }

  if (goals > 0) {
    const goalBadge = document.createElement("div");
    goalBadge.className = "goal-badge";
    goalBadge.textContent = `⚽ ${goals}`;
    goalBadge.addEventListener("click", e => {
      e.stopPropagation();
      goalCounts[name] = Math.max(0, (goalCounts[name] || 0) - 1);
      render();
    });
    avatar.appendChild(goalBadge);
  }

  let pressTimer = null;
  div.addEventListener("pointerdown", () => {
    if (editMode || !matchStarted) return; // no goals while adjusting plan or reviewing
    pressTimer = setTimeout(() => {
      pressTimer = null;
      goalCounts[name] = (goalCounts[name] || 0) + 1;
      div.classList.add("goal-scored");
      setTimeout(() => div.classList.remove("goal-scored"), 600);
      if (navigator.vibrate) navigator.vibrate(80);
      render();
    }, 600);
  });
  div.addEventListener("pointerup",    () => clearTimeout(pressTimer));
  div.addEventListener("pointerleave", () => clearTimeout(pressTimer));

  if (onSwapClick) {
    div.addEventListener("click", (e) => {
      // In edit mode there's no pressTimer (goal recording disabled), so always fire.
      // In live mode only fire on short tap, not after a long-press goal.
      if (editMode || pressTimer !== null) {
        onSwapClick();
      }
    });
  }

  // Drag-and-drop for same-slot position swaps in edit mode
  if (dragData) {
    div.draggable = true;
    div.addEventListener("dragstart", e => {
      clearTimeout(pressTimer);
      dragState = { slotIndex: dragData.slotIndex, posKey: dragData.posKey, playerName: name };
      e.dataTransfer.effectAllowed = "move";
      setTimeout(() => div.classList.add("dragging"), 0);
    });
    div.addEventListener("dragover", e => {
      if (dragState && dragState.slotIndex === dragData.slotIndex && dragState.posKey !== dragData.posKey) {
        e.preventDefault();
        div.classList.add("drag-over");
      }
    });
    div.addEventListener("dragleave", () => div.classList.remove("drag-over"));
    div.addEventListener("dragend", () => {
      div.classList.remove("dragging");
      dragState = null;
    });
    div.addEventListener("drop", e => {
      e.preventDefault();
      div.classList.remove("drag-over");
      if (!dragState || dragState.slotIndex !== dragData.slotIndex || dragState.posKey === dragData.posKey) return;
      // Same slot, different position — swap locally
      const slot = matchData.slots[dragData.slotIndex];
      const playerA = slot.lineup[dragState.posKey];
      const playerB = slot.lineup[dragData.posKey];
      slot.lineup[dragState.posKey] = playerB;
      slot.lineup[dragData.posKey] = playerA;
      lockedSlots.add(dragData.slotIndex);
      dragState = null;
      render();
    });
  }

  return div;
}

function render() {
  const slot = slotObj(currentSlot);
  const nextSlot = matchData.slots[currentSlot + 1] || null;
  const { label } = periodLabel(currentSlot);
  const formation = matchData.match.formation || "1-2-1";
  const teamSize = matchData.match.team_size || 5;

  // Only show sub arrows on 'a' slots (mid-period transitions)
  const isMidPeriod = currentSlot % 2 === 0 && nextSlot;
  const incoming = isMidPeriod ? incomingSubs(slot, nextSlot) : new Set();
  const outgoing = isMidPeriod ? outgoingSubs(slot, nextSlot) : new Set();

  const match = matchData.match;
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  document.getElementById("match-title").textContent =
    `${dateStr}  ·  vs ${match.opponent || "Unknown"}`;
  document.getElementById("slot-label").textContent = label;
  document.getElementById("slot-counter").textContent =
    `Slot ${currentSlot + 1} of ${matchData.slots.length}`;

  const dots = document.querySelectorAll(".progress-dot");
  dots.forEach((dot, i) => {
    dot.classList.toggle("active", i === currentSlot);
    dot.classList.toggle("done", i < currentSlot);
  });

  // Build replacement map for bench display
  const replacementMap = new Map();
  if (nextSlot && isMidPeriod) {
    const unpairedOut = new Set(outgoing);
    const allPos = ["GK", ...formationPositions(formation)];
    allPos.forEach(pos => {
      const cur = slot.lineup[pos]?.name;
      const nxt = nextSlot.lineup[pos]?.name;
      if (nxt && cur && incoming.has(nxt) && outgoing.has(cur)) {
        replacementMap.set(nxt, cur);
        unpairedOut.delete(cur);
      }
    });
    const leftoverOut = [...unpairedOut];
    let li = 0;
    incoming.forEach(inName => {
      if (!replacementMap.has(inName) && leftoverOut[li]) {
        replacementMap.set(inName, leftoverOut[li++]);
      }
    });
  }

  // Dynamic pitch rendering based on formation
  const pitch = document.getElementById("pitch");
  pitch.innerHTML = "";
  pitch.className = teamSize >= 9 ? "pitch pitch-large" : "pitch";
  if (editMode) pitch.classList.add("edit-mode");

  // Whiteboard mode — paper look when adjusting plan
  const pitchWrapper = document.querySelector(".pitch-wrapper");
  const benchSection = document.querySelector(".bench-section");
  pitchWrapper?.classList.toggle("whiteboard", editMode);
  benchSection?.classList.toggle("whiteboard", editMode);
  document.getElementById("edit-mode-badge").classList.toggle("visible", editMode);

  const { defense, midfield, forward } = parseFormation(formation);

  // Build rows: FWD, MID, DEF, GK (top to bottom on screen)
  const rows = [
    { keys: FWD_KEYS[forward] || [] },
    { keys: MID_KEYS[midfield] || [] },
    { keys: DEF_KEYS[defense] || [] },
    { keys: ["GK"] },
  ];

  rows.forEach(row => {
    const rowEl = document.createElement("div");
    rowEl.className = "pitch-row";
    if (row.keys.length > 1) rowEl.classList.add("multi-row");

    row.keys.forEach(posKey => {
      const name = slot.lineup[posKey]?.name ?? "?";
      const isGk = posKey === "GK";
      const swapHandler = editMode && !isGk ? () => openSwapPicker(currentSlot, posKey, name) : null;
      const dragData = editMode && !isGk ? { slotIndex: currentSlot, posKey } : null;
      rowEl.appendChild(playerCircle(name, posKey, incoming.has(name), outgoing.has(name), isGk, swapHandler, dragData));
    });

    pitch.appendChild(rowEl);
  });

  // Build set of removed player IDs for quick lookup
  const removedIds = new Set(Object.keys(removedPlayers).map(Number));

  // Bench
  const bench = document.getElementById("bench-list");
  bench.innerHTML = "";
  slot.bench.forEach(p => {
    const isRemoved = removedIds.has(p.id);
    const li = document.createElement("li");
    li.className = "bench-player";
    if (incoming.has(p.name)) li.classList.add("incoming");
    if (isRemoved) li.classList.add("bench-removed");

    const shirtNum = shirtNumbers[p.name];
    const avatarContent = shirtNum != null ? String(shirtNum) : p.name.slice(0, 3).toUpperCase();
    const replacing = replacementMap.get(p.name);
    const subLabel = replacing ? `<span class="bench-arrow">↑ On for ${replacing}</span>` : "";
    const removedLabel = isRemoved ? `<span class="bench-removed-badge">Removed</span>` : "";

    li.innerHTML = `
      <span class="bench-avatar">${avatarContent}</span>
      <span class="bench-name">${p.name}</span>
      ${subLabel}${removedLabel}
    `;

    if (matchStarted) {
      if (isRemoved) {
        li.addEventListener("click", () => openReinstateOverlay(p));
      } else {
        let benchPressTimer = null;
        li.addEventListener("pointerdown", () => {
          benchPressTimer = setTimeout(() => {
            benchPressTimer = null;
            openPlayerActionMenu(p);
          }, 600);
        });
        li.addEventListener("pointerup",    () => clearTimeout(benchPressTimer));
        li.addEventListener("pointerleave", () => clearTimeout(benchPressTimer));
      }
    }

    bench.appendChild(li);
  });

  // Buttons
  const btnPrev = document.getElementById("btn-prev");
  const btnNext = document.getElementById("btn-next");
  const btnAdjust = document.getElementById("btn-adjust");
  const startMatchBar = document.getElementById("start-match-bar");
  const liveBadge = document.getElementById("live-badge");

  const endMatchBar = document.getElementById("end-match-bar");
  const isCompleted = matchData.match.status === "completed";
  const isLastSlot = currentSlot === matchData.slots.length - 1;

  if (!matchStarted) {
    // Review mode: coach browses the plan before starting
    startMatchBar.hidden = false;
    endMatchBar.hidden = true;
    liveBadge.hidden = true;
    btnPrev.disabled = currentSlot === 0 || editMode;
    btnNext.disabled = editMode || isLastSlot;
    btnNext.textContent = "Next ▶";
    btnAdjust.hidden = false;
    btnAdjust.textContent = editMode ? "Done" : "Tinker";
  } else {
    // Live mode (in_progress or completed)
    startMatchBar.hidden = true;
    endMatchBar.hidden = isCompleted;
    liveBadge.hidden = isCompleted;
    btnPrev.disabled = currentSlot === 0 || editMode;
    btnNext.disabled = editMode || (isCompleted && isLastSlot);
    btnNext.textContent = isLastSlot ? "Match Report ▶" : "Next ▶";

    // Past slots (already played) — hide Tinker to prevent editing history
    const isPastSlot = currentSlot < (matchData.match.current_slot || 0);
    if (isPastSlot || isCompleted) {
      btnAdjust.hidden = true;
    } else {
      btnAdjust.hidden = false;
      btnAdjust.textContent = editMode ? "Done" : "Tinker";
    }
  }

  // Show locked badge in slot label
  const slotLabelEl = document.getElementById("slot-label");
  if (lockedSlots.has(currentSlot)) {
    slotLabelEl.innerHTML += ' <span class="slot-locked-badge">LOCKED</span>';
  }
}

// ── Quarter-break changes interstitial ────────────────────────────────────────
function renderChanges() {
  const prevSlot = slotObj(currentSlot - 1);
  const nextSlot = slotObj(currentSlot);
  const prevP = Math.floor((currentSlot - 1) / 2) + 1;
  const nextP = Math.floor(currentSlot / 2) + 1;
  const pLabel = (matchData.match.period_label || "Quarter") === "Half" ? "H" : "Q";

  const off = outgoingSubs(prevSlot, nextSlot);
  const on  = incomingSubs(prevSlot, nextSlot);
  const formation = matchData.match.formation || "1-2-1";

  const replacementMap = new Map();
  const unpairedOut = new Set(off);
  const allPos = ["GK", ...formationPositions(formation)];
  allPos.forEach(pos => {
    const cur = prevSlot.lineup[pos]?.name;
    const nxt = nextSlot.lineup[pos]?.name;
    if (nxt && cur && on.has(nxt) && off.has(cur)) {
      replacementMap.set(nxt, cur);
      unpairedOut.delete(cur);
    }
  });
  const leftoverOut = [...unpairedOut];
  let li = 0;
  on.forEach(inName => {
    if (!replacementMap.has(inName) && leftoverOut[li]) {
      replacementMap.set(inName, leftoverOut[li++]);
    }
  });

  const match = matchData.match;
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  document.getElementById("match-title").textContent =
    `${dateStr}  ·  vs ${match.opponent || "Unknown"}`;
  document.getElementById("slot-label").textContent = `${pLabel}${prevP} → ${pLabel}${nextP}`;
  document.getElementById("slot-counter").textContent =
    off.size === 0 ? "No changes" : `${off.size} change${off.size !== 1 ? "s" : ""}`;

  const dots = document.querySelectorAll(".progress-dot");
  dots.forEach((dot, i) => {
    dot.classList.toggle("active", false);
    dot.classList.toggle("done", i < currentSlot);
  });

  document.querySelector(".pitch-wrapper").style.display = "none";
  document.querySelector(".bench-section").style.display = "none";
  document.getElementById("report-section").style.display = "block";
  document.getElementById("start-match-bar").hidden = true;

  const list = document.getElementById("report-list");
  list.innerHTML = "";

  if (off.size === 0) {
    const emptyLi = document.createElement("li");
    emptyLi.className = "changes-empty";
    emptyLi.textContent = "No changes — same lineup continues";
    list.appendChild(emptyLi);
  } else {
    on.forEach(name => {
      const replacing = replacementMap.get(name);
      const item = document.createElement("li");
      item.className = "changes-row";
      item.innerHTML = `
        <span class="changes-in">↑ ${name}</span>
        ${replacing ? `<span class="changes-for">on for</span><span class="changes-out">↓ ${replacing}</span>` : ""}
      `;
      list.appendChild(item);
    });
  }

  document.getElementById("btn-prev").disabled = false;
  const btnNext = document.getElementById("btn-next");
  btnNext.disabled = false;
  const periodLbl = (matchData.match.period_label || "Quarter") === "Half" ? "Half" : "Quarter";
  btnNext.textContent = `Start ${periodLbl} ${nextP} ▶`;
}

// ── Report ────────────────────────────────────────────────────────────────────
function renderReport() {
  const allPlayers = [
    ...Object.values(matchData.slots[0].lineup),
    ...matchData.slots[0].bench,
  ].sort((a, b) => a.name.localeCompare(b.name));

  const totalSlots = matchData.slots.length;
  const perSlot = {};
  allPlayers.forEach(p => { perSlot[p.name] = Array(totalSlots).fill(null); });

  matchData.slots.forEach(slot => {
    Object.entries(slot.lineup).forEach(([pos, p]) => {
      const displayPos = normalizePos(pos);
      perSlot[p.name][slot.slot_index] = displayPos;
    });
  });

  const match = matchData.match;
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const pLabel = (match.period_label || "Quarter") === "Half" ? "H" : "Q";

  document.getElementById("slot-label").textContent = "Full Time";
  document.getElementById("slot-counter").textContent = "Match report";
  document.getElementById("match-title").textContent = `${dateStr}  ·  vs ${match.opponent || "Unknown"}`;

  document.querySelector(".pitch-wrapper").style.display = "none";
  document.querySelector(".bench-section").style.display = "none";
  document.getElementById("report-section").style.display = "block";
  document.getElementById("progress-dots").style.display = "none";

  // Generate slot labels dynamically
  const slotLabels = [];
  for (let i = 0; i < totalSlots; i++) {
    const p = Math.floor(i / 2) + 1;
    const h = i % 2 === 0 ? "a" : "b";
    slotLabels.push(`${pLabel}${p}${h}`);
  }

  const list = document.getElementById("report-list");
  list.innerHTML = "";

  allPlayers.forEach(({ name }) => {
    const slots = perSlot[name];
    const count = slots.filter(Boolean).length;
    const goals = goalCounts[name] || 0;

    const chipsHtml = slots.map((pos, i) => {
      if (!pos) return `<span class="slot-chip bench" title="${slotLabels[i]}">–</span>`;
      return `<span class="slot-chip pos-${pos.toLowerCase()}" title="${slotLabels[i]}: ${pos}">
        <span class="chip-quarter">${slotLabels[i]}</span>
        <span class="chip-pos">${pos}</span>
      </span>`;
    }).join("");

    const goalHtml = goals > 0 ? `<span class="report-goals">⚽ ${goals}</span>` : "";

    const li = document.createElement("li");
    li.className = "report-row";
    li.innerHTML = `
      <div class="report-name-row">
        <span class="report-name">${name}</span>
        ${goalHtml}
        <span class="report-slots">${count} slot${count !== 1 ? "s" : ""}</span>
      </div>
      <div class="slot-chips">${chipsHtml}</div>
    `;
    list.appendChild(li);
  });

  // Skill totals row
  const skillLi = document.createElement("li");
  skillLi.className = "report-row report-row-skill";
  const skillChipsHtml = matchData.slots.map((slot, i) =>
    `<span class="slot-chip skill-chip" title="${slotLabels[i]}: skill ${slot.skill_total ?? "?"}">
      <span class="chip-quarter">${slotLabels[i]}</span>
      <span class="chip-pos">${slot.skill_total ?? "?"}</span>
    </span>`
  ).join("");
  skillLi.innerHTML = `
    <div class="report-name-row">
      <span class="report-name">Skill total</span>
    </div>
    <div class="slot-chips">${skillChipsHtml}</div>
  `;
  list.appendChild(skillLi);

  document.getElementById("btn-prev").disabled = false;
  document.getElementById("btn-next").disabled = false;
  document.getElementById("btn-next").textContent = "◀ Back to slots";
  // End Match bar: visible in live mode on report view
  const endBar = document.getElementById("end-match-bar");
  if (endBar) endBar.hidden = !matchStarted || matchData.match.status === "completed";
  document.getElementById("start-match-bar").hidden = true;
}

function showMatch() {
  showingReport = false;
  showingChanges = false;
  document.querySelector(".pitch-wrapper").style.display = "";
  document.querySelector(".bench-section").style.display = "";
  document.getElementById("report-section").style.display = "none";
  document.getElementById("progress-dots").style.display = "";
  render();
}

// ── Pitch controls ────────────────────────────────────────────────────────────
document.getElementById("btn-start-match-cta").addEventListener("click", () => doStartMatch());

document.getElementById("btn-next").addEventListener("click", async () => {
  if (showingReport) {
    // From report: "Next" just closes report back to last slot (End Match button ends it)
    showMatch();
    return;
  }
  if (showingChanges) {
    showingChanges = false;
    showMatch();
    return;
  }
  if (currentSlot < matchData.slots.length - 1) {
    currentSlot++;
    // Persist progress when advancing beyond the furthest reached slot
    if (matchStarted && currentSlot > (matchData.match.current_slot || 0)) {
      matchData.match.current_slot = currentSlot;
      api.updateProgress(matchData.match.id, currentSlot).catch(() => {});
    }
    if (currentSlot % 2 === 0 && currentSlot > 0) {
      showingChanges = true;
      renderChanges();
    } else {
      render();
    }
  } else {
    // Last slot — show match report
    showingReport = true;
    renderReport();
  }
});

document.getElementById("btn-prev").addEventListener("click", () => {
  if (showingReport) { showMatch(); return; }
  if (showingChanges) {
    showingChanges = false;
    currentSlot--;
    showMatch();
    return;
  }
  if (currentSlot > 0) { currentSlot--; render(); }
});

// ── End match ─────────────────────────────────────────────────────────────────
document.getElementById("btn-end-match").addEventListener("click", () => {
  const isLastSlot = currentSlot === matchData.slots.length - 1;
  if (showingReport || isLastSlot) {
    // At the end of the match — no confirmation needed
    doEndMatch();
  } else {
    // Mid-match early end — ask for confirmation
    document.getElementById("end-match-overlay").hidden = false;
  }
});

document.getElementById("btn-end-cancel").addEventListener("click", () => {
  document.getElementById("end-match-overlay").hidden = true;
});

document.getElementById("btn-end-confirm").addEventListener("click", () => {
  document.getElementById("end-match-overlay").hidden = true;
  doEndMatch();
});

async function doEndMatch() {
  // Save goals and mark match completed, then show Full Time screen
  if (matchData?.match.id) {
    const oppGoals = matchData.match.opponent_goals || 0;
    await api.saveGoals(matchData.match.id, goalCounts, oppGoals).catch(() => {});
    await api.updateProgress(matchData.match.id, currentSlot, "completed").catch(() => {});
    matchData.match.status = "completed";
  }
  await showFulltime();
}

// ── Start match ───────────────────────────────────────────────────────────────
async function doStartMatch() {
  try {
    await api.startMatch(matchData.match.id);
    matchStarted = true;
    matchData.match.status = "in_progress";
    matchData.match.current_slot = 0;
    render();
  } catch (err) {
    alert("Could not start match: " + err.message);
  }
}

// ── Player removal ─────────────────────────────────────────────────────────────
function openPlayerActionMenu(player) {
  pendingActionPlayer = player;
  document.getElementById("player-action-title").textContent = player.name;
  document.getElementById("player-action-overlay").hidden = false;
}

function openReinstateOverlay(player) {
  pendingActionPlayer = player;
  document.getElementById("reinstate-title").textContent = player.name;
  document.getElementById("reinstate-info").textContent =
    `${player.name} was removed from the match. Reinstate them from slot ${currentSlot + 1} onward?`;
  document.getElementById("reinstate-overlay").hidden = false;
}

document.getElementById("btn-action-cancel").addEventListener("click", () => {
  document.getElementById("player-action-overlay").hidden = true;
  pendingActionPlayer = null;
});

document.getElementById("btn-action-goal").addEventListener("click", () => {
  document.getElementById("player-action-overlay").hidden = true;
  if (pendingActionPlayer) {
    goalCounts[pendingActionPlayer.name] = (goalCounts[pendingActionPlayer.name] || 0) + 1;
    if (navigator.vibrate) navigator.vibrate(80);
    render();
  }
  pendingActionPlayer = null;
});

document.getElementById("btn-action-remove").addEventListener("click", async () => {
  document.getElementById("player-action-overlay").hidden = true;
  if (!pendingActionPlayer || !matchData) { pendingActionPlayer = null; return; }

  const player = pendingActionPlayer;
  pendingActionPlayer = null;

  const statusEl = document.getElementById("adjust-status");
  statusEl.hidden = false;
  try {
    const result = await api.removePlayer(matchData.match.id, player.id, currentSlot);
    statusEl.hidden = true;
    removedPlayers = result.removed_players || {};
    matchData.slots = result.slots;
    matchData.warnings = result.warnings;
    render();
  } catch (err) {
    statusEl.hidden = true;
    alert("Could not remove player: " + err.message);
  }
});

document.getElementById("btn-reinstate-cancel").addEventListener("click", () => {
  document.getElementById("reinstate-overlay").hidden = true;
  pendingActionPlayer = null;
});

document.getElementById("btn-reinstate-confirm").addEventListener("click", async () => {
  document.getElementById("reinstate-overlay").hidden = true;
  if (!pendingActionPlayer || !matchData) { pendingActionPlayer = null; return; }

  const player = pendingActionPlayer;
  pendingActionPlayer = null;

  const statusEl = document.getElementById("adjust-status");
  statusEl.hidden = false;
  try {
    const result = await api.reinstatePlayer(matchData.match.id, player.id);
    statusEl.hidden = true;
    removedPlayers = result.removed_players || {};
    matchData.slots = result.slots;
    matchData.warnings = result.warnings;
    render();
  } catch (err) {
    statusEl.hidden = true;
    alert("Could not reinstate player: " + err.message);
  }
});

// ── Delete player modal ────────────────────────────────────────────────────────
document.getElementById("btn-delete-player-cancel").addEventListener("click", () => {
  document.getElementById("delete-player-overlay").hidden = true;
  pendingDeletePlayerId = null;
});

document.getElementById("btn-delete-player-confirm").addEventListener("click", async () => {
  document.getElementById("delete-player-overlay").hidden = true;
  if (!pendingDeletePlayerId) return;
  const id = pendingDeletePlayerId;
  pendingDeletePlayerId = null;
  await api.deletePlayer(id).catch(err => alert(err.message));
  loadSquad();
});

// ── Edit mode (adjust plan) ────────────────────────────────────────────────────
document.getElementById("btn-adjust").addEventListener("click", () => {
  editMode = !editMode;
  const btn = document.getElementById("btn-adjust");
  btn.textContent = editMode ? "Done" : "Tinker";
  render();
});

document.getElementById("btn-swap-cancel").addEventListener("click", () => {
  document.getElementById("swap-overlay").hidden = true;
  pendingSwap = null;
});

document.getElementById("btn-fairness-cancel").addEventListener("click", () => {
  document.getElementById("fairness-overlay").hidden = true;
});

function openSwapPicker(slotIndex, posKey, currentPlayerName) {
  pendingSwap = { slotIndex, posKey, currentPlayerName };
  const slot = matchData.slots[slotIndex];
  const onPitchNames = new Set(Object.values(slot.lineup).map(p => p.name));

  document.getElementById("swap-title").textContent = `Replace ${currentPlayerName}`;
  const list = document.getElementById("swap-list");
  list.innerHTML = "";

  // Show bench players as swap options
  slot.bench.forEach(p => {
    const count = slotCountForPlayer(p.name);
    const li = document.createElement("li");
    li.className = "swap-item";
    li.innerHTML = `<span class="swap-name">${p.name}</span><span class="swap-pos">Bench · ${count} slot${count !== 1 ? "s" : ""}</span>`;
    li.addEventListener("click", () => executeSwap(p.id, p.name));
    list.appendChild(li);
  });

  // Also show other on-pitch players (position swap)
  Object.entries(slot.lineup).forEach(([pos, p]) => {
    if (p.name !== currentPlayerName && pos !== "GK") {
      const count = slotCountForPlayer(p.name);
      const li = document.createElement("li");
      li.className = "swap-item";
      li.innerHTML = `<span class="swap-name">${p.name}</span><span class="swap-pos">${pos} · ${count} slot${count !== 1 ? "s" : ""}</span>`;
      li.addEventListener("click", () => executeSwap(p.id, p.name));
      list.appendChild(li);
    }
  });

  document.getElementById("swap-overlay").hidden = false;
}

async function executeSwap(newPlayerId, newPlayerName) {
  document.getElementById("swap-overlay").hidden = true;
  if (!pendingSwap || !matchData) return;

  const { slotIndex, posKey, currentPlayerName } = pendingSwap;
  const slot = matchData.slots[slotIndex];

  // Build the edit: figure out if this is a bench swap or position swap
  const edits = {};
  const isOnPitch = Object.entries(slot.lineup).find(([, p]) => p.name === newPlayerName);

  if (isOnPitch) {
    // Position-only swap: both players already in this slot, just swap their positions.
    // No playing time changes for anyone — handle locally, no API call needed.
    const [otherPos] = isOnPitch;
    const currentPlayer = slot.lineup[posKey];
    slot.lineup[posKey] = slot.lineup[otherPos];
    slot.lineup[otherPos] = currentPlayer;
    lockedSlots.add(slotIndex);
    pendingSwap = null;
    render();
    return;
  }

  // Bench swap: replace current player with bench player
  edits[slotIndex] = { [posKey]: newPlayerId };

  const statusEl = document.getElementById("adjust-status");
  statusEl.hidden = false;

  try {
    const result = await api.adjustRotation(
      matchData.match.id, edits, [...lockedSlots],
    );

    statusEl.hidden = true;

    // Check for fairness warnings
    if (result.fairness_warnings && result.fairness_warnings.length > 0) {
      showFairnessWarning(result);
      return;
    }

    applyAdjustResult(result);
  } catch (err) {
    statusEl.hidden = true;
    alert("Could not adjust: " + err.message);
  }
  pendingSwap = null;
}

function showFairnessWarning(result) {
  const list = document.getElementById("fairness-list");
  list.innerHTML = "";
  result.fairness_warnings.forEach(w => {
    const li = document.createElement("li");
    li.className = "fairness-item";
    const cls = w.diff < 0 ? "fairness-loss" : "fairness-gain";
    const verb = w.diff < 0 ? "loses" : "gains";
    li.innerHTML = `${w.player} <span class="${cls}">${verb} ${Math.abs(w.diff)} slot${Math.abs(w.diff) !== 1 ? "s" : ""}</span> (${w.before} → ${w.after})`;
    list.appendChild(li);
  });

  // Wire confirm button to apply
  const confirmBtn = document.getElementById("btn-fairness-confirm");
  const handler = () => {
    document.getElementById("fairness-overlay").hidden = true;
    document.getElementById("adjust-status").hidden = false;
    setTimeout(() => {
      applyAdjustResult(result);
      document.getElementById("adjust-status").hidden = true;
    }, 600);
    confirmBtn.removeEventListener("click", handler);
  };
  confirmBtn.addEventListener("click", handler);

  document.getElementById("fairness-overlay").hidden = false;
}

function applyAdjustResult(result) {
  matchData.slots = result.slots;
  matchData.warnings = result.warnings;
  if (result.locked_slots) {
    lockedSlots = new Set(result.locked_slots);
  }
  render();
}

// Save goals when leaving pitch view via back button (no opponent goals known yet)
async function saveGoalsIfNeeded() {
  if (!matchData || !matchData.match.id) return;
  const hasGoals = Object.values(goalCounts).some(v => v > 0);
  if (hasGoals) {
    await api.saveGoals(matchData.match.id, goalCounts, matchData.match.opponent_goals || 0).catch(() => {});
  }
}

document.getElementById("btn-pitch-back").addEventListener("click", async () => {
  await saveGoalsIfNeeded();
  if (pitchBackContext === "tournament" && activeTournamentId) {
    loadTournamentLobby(activeTournamentId);
  } else {
    loadHome();
  }
});

// ── Full time screen ───────────────────────────────────────────────────────────
async function showFulltime() {
  const match = matchData.match;
  const ourGoals = Object.values(goalCounts).reduce((sum, n) => sum + n, 0);
  const oppGoals = match.opponent_goals || 0;

  const isHome = (match.home_away || "home") === "home";
  const ourName = teamInfo.team_name || "My Team";
  const oppName = match.opponent || "Opponent";

  // Populate team blocks depending on home/away
  document.getElementById("ft-home-name").textContent = isHome ? ourName : oppName;
  document.getElementById("ft-away-name").textContent = isHome ? oppName : ourName;
  document.getElementById("ft-our-score").textContent = isHome ? ourGoals : oppGoals;
  document.getElementById("ft-their-score").textContent = isHome ? oppGoals : ourGoals;

  // Team logo
  const logoEl = document.getElementById("ft-home-logo");
  if (isHome && teamInfo.team_logo) {
    logoEl.innerHTML = `<img src="${teamInfo.team_logo}" alt="${ourName}" class="ft-logo-img" />`;
  } else {
    logoEl.textContent = isHome ? ourName.slice(0, 2).toUpperCase() : oppName.slice(0, 2).toUpperCase();
  }

  // Date + venue
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const venue = isHome ? "Home" : "Away";
  document.getElementById("ft-meta").textContent = `${dateStr}  ·  ${venue}`;

  // Opponent goals input
  document.getElementById("ft-opp-input").value = oppGoals;

  // Goal scorers
  const scorers = Object.entries(goalCounts).filter(([, n]) => n > 0);
  const scorersSection = document.getElementById("ft-scorers-section");
  const scorersList = document.getElementById("ft-scorers-list");
  if (scorers.length > 0) {
    scorers.sort((a, b) => b[1] - a[1]);
    scorersList.innerHTML = scorers.map(([name, n]) =>
      `<span class="ft-scorer">${name}${n > 1 ? ` (×${n})` : ""}</span>`
    ).join("");
    scorersSection.hidden = false;
  } else {
    scorersSection.hidden = true;
  }

  showScreen("screen-fulltime");
}

// Update score display live as opponent goals change
document.getElementById("ft-opp-input").addEventListener("input", e => {
  const oppGoals = Math.max(0, parseInt(e.target.value) || 0);
  const ourGoals = Object.values(goalCounts).reduce((sum, n) => sum + n, 0);
  const isHome = (matchData?.match.home_away || "home") === "home";
  document.getElementById("ft-our-score").textContent = isHome ? ourGoals : oppGoals;
  document.getElementById("ft-their-score").textContent = isHome ? oppGoals : ourGoals;
});


document.getElementById("btn-ft-done").addEventListener("click", async () => {
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  if (matchData?.match.id) {
    await api.saveGoals(matchData.match.id, goalCounts, oppGoals).catch(() => {});
  }
  if (pitchBackContext === "tournament" && activeTournamentId) {
    loadTournamentLobby(activeTournamentId);
  } else {
    loadHome();
  }
});

// ── Stats screen ──────────────────────────────────────────────────────────────
document.getElementById("btn-stats-back").addEventListener("click", loadHome);

async function loadStats() {
  showScreen("screen-stats");
  const list = document.getElementById("stats-list");
  list.innerHTML = "<li class='loading'>Loading…</li>";

  const stats = await api.getSeasonStats().catch(() => []);
  list.innerHTML = "";

  if (stats.length === 0) {
    list.innerHTML = "<li class='empty-state'>No stats yet — play some matches first</li>";
    return;
  }

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
    `<span class="history-pos-badge pos-${pos.toLowerCase()}">${pos} ×${n}</span>`
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
      `<span class="slot-chip pos-${pos.toLowerCase()}">${pos}</span>`
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

// ── Share result (canvas image) ───────────────────────────────────────────────
function buildResultBlob() {
  const match = matchData.match;
  const ourGoals = Object.values(goalCounts).reduce((sum, n) => sum + n, 0);
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  const isHome = (match.home_away || "home") === "home";
  const homeTeam = isHome ? (teamInfo.team_name || "My Team") : (match.opponent || "Opponent");
  const awayTeam = isHome ? (match.opponent || "Opponent") : (teamInfo.team_name || "My Team");
  const homeGoals = isHome ? ourGoals : oppGoals;
  const awayGoals = isHome ? oppGoals : ourGoals;

  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const scorers = Object.entries(goalCounts).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);

  function draw(logoImg) {
    // Logical dimensions (2× canvas for HiDPI sharpness)
    const W = 600;
    const H = 270 + (scorers.length > 0 ? 28 + scorers.length * 40 : 0);
    const SCALE = 2;
    const canvas = document.createElement("canvas");
    canvas.width = W * SCALE;
    canvas.height = H * SCALE;
    const ctx = canvas.getContext("2d");
    ctx.scale(SCALE, SCALE);

    // Background — Pitch Deep
    ctx.fillStyle = "#0E3A29";
    ctx.fillRect(0, 0, W, H);

    // Subtle centre-line texture
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2); ctx.stroke();

    // Top accent bar — Pitch green
    ctx.fillStyle = "#1A5C42";
    ctx.fillRect(0, 0, W, 6);

    // "FULL TIME" amber pill
    ctx.font = "bold 13px system-ui, sans-serif";
    const pillPad = 20;
    const pillTW = ctx.measureText("FULL TIME").width;
    const pillW = pillTW + pillPad * 2;
    const pillH = 30;
    const pillX = W / 2 - pillW / 2;
    const pillY = 22;
    ctx.fillStyle = "#F5B544";
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(pillX, pillY, pillW, pillH, 15);
    } else {
      ctx.rect(pillX, pillY, pillW, pillH);
    }
    ctx.fill();
    ctx.fillStyle = "#1A1F1C";
    ctx.textAlign = "center";
    ctx.fillText("FULL TIME", W / 2, pillY + 20);

    // Date
    ctx.fillStyle = "rgba(242,244,238,0.4)";
    ctx.font = "14px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(dateStr, W / 2, 76);

    // Divider
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(40, 92); ctx.lineTo(W - 40, 92); ctx.stroke();

    // Helper: truncate to maxWidth
    function trunc(text, maxW) {
      if (ctx.measureText(text).width <= maxW) return text;
      while (text.length > 1 && ctx.measureText(text + "\u2026").width > maxW) text = text.slice(0, -1);
      return text + "\u2026";
    }

    // Logo badge (circular clip, top-left of home team name area)
    const logoSize = 36;
    const logoX = 40;
    const logoY = 104;
    if (logoImg) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(logoX + logoSize / 2, logoY + logoSize / 2, logoSize / 2, 0, Math.PI * 2);
      ctx.clip();
      ctx.drawImage(logoImg, logoX, logoY, logoSize, logoSize);
      ctx.restore();
    }

    // Team names — offset right if logo present
    const nameOffsetX = logoImg ? logoX + logoSize + 8 : logoX;
    const nameMax = W / 2 - nameOffsetX - 10;
    ctx.font = "bold 21px system-ui, sans-serif";
    ctx.fillStyle = "rgba(242,244,238,0.9)";
    ctx.textAlign = "left";
    ctx.fillText(trunc(homeTeam, nameMax), nameOffsetX, 128);
    ctx.textAlign = "right";
    ctx.fillText(trunc(awayTeam, W / 2 - 60), W - 40, 128);

    // Score — large, centered
    ctx.fillStyle = "#F2F4EE";
    ctx.font = "bold 72px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(`${homeGoals} \u2013 ${awayGoals}`, W / 2, 210);

    // Scorers section
    if (scorers.length > 0) {
      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      ctx.beginPath(); ctx.moveTo(40, 228); ctx.lineTo(W - 40, 228); ctx.stroke();

      ctx.fillStyle = "rgba(242,244,238,0.6)";
      ctx.font = "17px system-ui, sans-serif";
      ctx.textAlign = "center";
      let y = 258;
      scorers.forEach(([pName, n]) => {
        ctx.fillText(`${pName}${n > 1 ? `  \xD7${n}` : ""}`, W / 2, y);
        y += 40;
      });
    }

    // Gaffer wordmark watermark
    ctx.fillStyle = "rgba(242,244,238,0.2)";
    ctx.font = "12px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Gaffer", W / 2, H - 12);

    return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  }

  // Load team logo if available, then draw
  if (teamInfo.team_logo) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => draw(img).then(resolve);
      img.onerror = () => draw(null).then(resolve);
      img.src = teamInfo.team_logo;
    });
  }
  return draw(null);
}

function downloadBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

document.getElementById("btn-ft-share").addEventListener("click", async () => {
  const blob = await buildResultBlob();
  const match = matchData.match;
  const isHome = (match.home_away || "home") === "home";
  const home = isHome ? (teamInfo.team_name || "My Team") : (match.opponent || "Opponent");
  const away = isHome ? (match.opponent || "Opponent") : (teamInfo.team_name || "My Team");
  const ourGoals = Object.values(goalCounts).reduce((sum, n) => sum + n, 0);
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  const hg = isHome ? ourGoals : oppGoals;
  const ag = isHome ? oppGoals : ourGoals;
  const file = new File([blob], "result.png", { type: "image/png" });
  const title = `FT: ${home} ${hg}\u2013${ag} ${away}`;
  if (navigator.share && navigator.canShare?.({ files: [file] })) {
    await navigator.share({ files: [file], title }).catch(() => {});
  } else if (navigator.share) {
    await navigator.share({ title, text: `FULL TIME\n${home} ${hg}\u2013${ag} ${away}` }).catch(() => {});
  } else {
    downloadBlob(blob, `FT-${match.date}.png`);
  }
});

document.getElementById("btn-ft-save").addEventListener("click", async () => {
  const blob = await buildResultBlob();
  downloadBlob(blob, `FT-${matchData.match.date}.png`);
});

// ── Season export ─────────────────────────────────────────────────────────────
function buildMatchesCsv(matches) {
  const rows = [
    ["Date", "Opponent", "Size", "Formation", "Home/Away", "Has Rotation"],
    ...matches.map(m => {
      const d = new Date(m.date + "T12:00:00");
      return [
        d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
        m.opponent || "", `${m.team_size || 5}v${m.team_size || 5}`,
        m.formation || "", m.home_away || "home", m.has_rotation ? "Yes" : "No",
      ];
    }),
  ];
  const csv = rows.map(r => r.map(cell => {
    const s = String(cell ?? "");
    return s.includes(",") || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
  }).join(",")).join("\n");
  return csv;
}

document.getElementById("btn-export-matches").addEventListener("click", async () => {
  const matches = await api.getMatches().catch(() => []);
  const csv = buildMatchesCsv(matches);
  const file = new File([csv], "season-matches.csv", { type: "text/csv" });

  // Mobile: native share sheet shows Excel, Sheets, etc.
  if (navigator.canShare?.({ files: [file] })) {
    await navigator.share({ files: [file], title: "Season Matches" }).catch(() => {});
    return;
  }

  // Desktop: toggle dropdown
  const dropdown = document.getElementById("export-dropdown");
  dropdown.hidden = !dropdown.hidden;

  document.getElementById("btn-export-csv").onclick = () => {
    downloadBlob(new Blob([csv], { type: "text/csv" }), "season-matches.csv");
    dropdown.hidden = true;
  };

  document.getElementById("btn-export-sheets").onclick = async () => {
    const rows = [
      ["Date", "Opponent", "Size", "Formation", "Home/Away", "Has Rotation"],
      ...matches.map(m => {
        const d = new Date(m.date + "T12:00:00");
        return [d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
          m.opponent || "", `${m.team_size || 5}v${m.team_size || 5}`, m.formation || "",
          m.home_away || "home", m.has_rotation ? "Yes" : "No"];
      }),
    ];
    const tsv = rows.map(r => r.map(c => String(c ?? "").replace(/\t/g, " ")).join("\t")).join("\n");
    await navigator.clipboard.writeText(tsv).catch(() => {});
    window.open("https://sheets.new", "_blank");
    const toast = document.createElement("div");
    toast.className = "sheets-toast";
    toast.textContent = "Data copied \u2014 paste with Ctrl+V / \u2318V into the new sheet";
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
    dropdown.hidden = true;
  };
});

// Close dropdown when clicking outside
document.addEventListener("click", e => {
  const bar = document.getElementById("export-bar");
  if (bar && !bar.contains(e.target)) {
    const dd = document.getElementById("export-dropdown");
    if (dd) dd.hidden = true;
  }
});

// ── Tournament Mode ───────────────────────────────────────────────────────────

let tournamentSelectedSize = 5;
let activeTournamentData = null; // full detail from GET /tournaments/{id}

// ── Tournament Home ───────────────────────────────────────────────────────────
async function loadTournamentHome() {
  showScreen("screen-tournament-home");
  const list = document.getElementById("tournament-list");
  list.innerHTML = "<li class='loading'>Loading…</li>";

  const tournaments = await api.getTournaments().catch(() => []);
  list.innerHTML = "";

  if (tournaments.length === 0) {
    list.innerHTML = "<li class='empty-state'>No tournaments yet — tap New Tournament to start</li>";
    return;
  }

  tournaments.forEach(t => {
    const date = new Date(t.date + "T12:00:00");
    const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    const matchCount = t.match_count ?? 0;
    const li = document.createElement("li");
    li.className = "match-item";
    li.innerHTML = `
      <div class="match-item-main">
        <span class="match-item-date">${dateStr}</span>
        <span class="match-item-opponent">${t.name || "Tournament"}</span>
        <span class="match-badge size-badge">${t.team_size || 5}v${t.team_size || 5}</span>
        <span class="match-badge">${matchCount} match${matchCount !== 1 ? "es" : ""}</span>
      </div>
      <button class="btn-icon match-delete" data-id="${t.id}" title="Delete tournament">✕</button>
    `;
    li.querySelector(".match-item-main").addEventListener("click", () => loadTournamentLobby(t.id));
    li.querySelector(".match-delete").addEventListener("click", async e => {
      e.stopPropagation();
      if (confirm(`Delete tournament "${t.name}"? This will remove all matches.`)) {
        await api.deleteTournament(t.id).catch(err => alert(err.message));
        loadTournamentHome();
      }
    });
    list.appendChild(li);
  });
}

document.getElementById("btn-tournament-home-back").addEventListener("click", () => showScreen("screen-landing"));
document.getElementById("btn-new-tournament").addEventListener("click", async () => {
  // Ensure game configs loaded
  if (!gameConfigs) {
    gameConfigs = await api.getGameConfigs().catch(() => null);
  }
  // Reset form
  document.getElementById("tournament-name-input").value = "";
  document.getElementById("tournament-date").value = new Date().toISOString().split("T")[0];
  document.getElementById("tournament-duration").value = "10";
  document.getElementById("tournament-halftime").checked = false;
  document.getElementById("tournament-fairness-slider").value = 50;
  updateTournamentFairnessLabel(50);
  document.getElementById("tournament-rotation-slider").value = 50;
  updateTournamentRotationLabel(50);
  document.getElementById("tournament-num-matches").value = "4";
  tournamentSelectSize(5);
  showScreen("screen-new-tournament");
});

// ── New tournament form ────────────────────────────────────────────────────────
document.getElementById("btn-new-tournament-back").addEventListener("click", loadTournamentHome);

function tournamentSelectSize(size) {
  tournamentSelectedSize = size;
  document.querySelectorAll("#tournament-size-picker .size-btn").forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.size) === size);
  });
  updateTournamentFormationOptions();
}

function updateTournamentFormationOptions() {
  const select = document.getElementById("tournament-formation-select");
  select.innerHTML = "";
  if (gameConfigs && gameConfigs[String(tournamentSelectedSize)]) {
    const cfg = gameConfigs[String(tournamentSelectedSize)];
    cfg.formations.forEach(f => {
      const opt = document.createElement("option");
      opt.value = f.notation;
      opt.textContent = f.notation;
      if (f.notation === cfg.default_formation) opt.selected = true;
      select.appendChild(opt);
    });
  } else {
    const defaults = { 5: "1-2-1", 6: "1-3-1", 7: "2-3-1", 9: "3-3-2" };
    const opt = document.createElement("option");
    opt.value = defaults[tournamentSelectedSize] || "1-2-1";
    opt.textContent = opt.value;
    select.appendChild(opt);
  }
}

document.getElementById("tournament-size-picker").addEventListener("click", e => {
  const btn = e.target.closest(".size-btn");
  if (btn) tournamentSelectSize(parseInt(btn.dataset.size));
});

function updateTournamentFairnessLabel(value) {
  const el = document.getElementById("tournament-fairness-value");
  const v = parseInt(value);
  if (v <= 15) el.textContent = "Equal play — everyone gets the same time";
  else if (v <= 40) el.textContent = "Mostly fair — slight edge for stronger players";
  else if (v <= 60) el.textContent = "Balanced — skill matters but everyone plays";
  else if (v <= 85) el.textContent = "Competitive — best players get more time";
  else el.textContent = "Win mode — strongest lineup prioritised";
}

document.getElementById("tournament-fairness-slider").addEventListener("input", e => {
  updateTournamentFairnessLabel(e.target.value);
});

function updateTournamentRotationLabel(value) {
  const el = document.getElementById("tournament-rotation-value");
  const v = parseInt(value);
  if (v <= 15) el.textContent = "Specialist — players stay in one position";
  else if (v <= 40) el.textContent = "Mostly fixed — occasional position changes";
  else if (v <= 60) el.textContent = "Balanced — regular position rotation";
  else if (v <= 85) el.textContent = "High rotation — players try most positions";
  else el.textContent = "All-rounder — everyone plays everywhere";
}

document.getElementById("tournament-rotation-slider").addEventListener("input", e => {
  updateTournamentRotationLabel(e.target.value);
});

let pendingTournamentId = null;
let pendingNumMatches = 4;

document.getElementById("new-tournament-form").addEventListener("submit", async e => {
  e.preventDefault();
  const name = document.getElementById("tournament-name-input").value.trim();
  const date = document.getElementById("tournament-date").value;
  const formation = document.getElementById("tournament-formation-select").value;
  const duration = parseInt(document.getElementById("tournament-duration").value) || 10;
  const hasHalftime = document.getElementById("tournament-halftime").checked;
  const fairnessValue = parseInt(document.getElementById("tournament-fairness-slider").value);
  const rotationIntensity = parseInt(document.getElementById("tournament-rotation-slider").value);
  pendingNumMatches = Math.max(1, parseInt(document.getElementById("tournament-num-matches").value) || 1);

  if (!name) {
    document.getElementById("tournament-name-input").focus();
    return;
  }

  const btn = document.getElementById("btn-create-tournament");
  btn.disabled = true;
  btn.textContent = "Creating…";

  const tournament = await api.createTournament({
    name,
    date: date || new Date().toISOString().split("T")[0],
    team_size: tournamentSelectedSize,
    formation,
    match_duration_mins: duration,
    has_halftime: hasHalftime,
    fairness_value: fairnessValue,
    rotation_intensity: rotationIntensity,
  }).catch(err => { alert(err.message); return null; });

  btn.disabled = false;
  btn.textContent = "Next: Select Players →";

  if (!tournament) return;
  pendingTournamentId = tournament.id;
  loadTournamentSquadScreen(tournament.id, pendingNumMatches);
});

// ── Tournament Squad Selection ────────────────────────────────────────────────
async function loadTournamentSquadScreen(tournamentId, numMatches) {
  activeTournamentId = tournamentId;
  showScreen("screen-tournament-squad");

  const desc = document.getElementById("tournament-squad-desc");
  desc.textContent = `Select who's available today. ${numMatches} match${numMatches !== 1 ? "es" : ""} will be generated.`;

  const ul = document.getElementById("tournament-squad-list");
  ul.innerHTML = "<li class='loading'>Loading players…</li>";

  const players = await api.getPlayers().catch(() => []);
  ul.innerHTML = "";

  if (players.length === 0) {
    ul.innerHTML = "<li class='empty-state'>No players in squad — add some in Squad Management first</li>";
    return;
  }

  players.forEach(p => {
    const li = document.createElement("li");
    li.className = "avail-item";
    li.innerHTML = `
      <label class="avail-label">
        <input type="checkbox" class="avail-check" data-pid="${p.id}" checked />
        <span class="avail-name">${p.name}</span>
        <span class="avail-skill">★${p.skill_rating}</span>
      </label>
    `;
    ul.appendChild(li);
  });

  // Also show any guest players already added
  renderTournamentSquadGuests(tournamentId);
}

async function renderTournamentSquadGuests(tournamentId) {
  const data = await api.getTournament(tournamentId).catch(() => null);
  if (!data) return;
  const guests = data.guest_players || [];
  const ul = document.getElementById("tournament-squad-list");
  // Remove any previously rendered guest rows
  ul.querySelectorAll(".avail-item-guest").forEach(el => el.remove());
  guests.forEach(p => {
    const li = document.createElement("li");
    li.className = "avail-item avail-item-guest";
    li.innerHTML = `
      <label class="avail-label">
        <input type="checkbox" class="avail-check" data-pid="${p.id}" checked />
        <span class="avail-name">${p.name}</span>
        <span class="avail-guest-tag">Guest</span>
        <span class="avail-skill">★${p.skill_rating}</span>
        <button class="btn-icon avail-remove-guest" data-pid="${p.id}" title="Remove">✕</button>
      </label>
    `;
    li.querySelector(".avail-remove-guest").addEventListener("click", async e => {
      e.preventDefault(); e.stopPropagation();
      await api.removeGuestPlayer(tournamentId, p.id).catch(() => {});
      renderTournamentSquadGuests(tournamentId);
    });
    ul.appendChild(li);
  });
}

document.getElementById("btn-tournament-squad-back").addEventListener("click", loadTournamentHome);

document.getElementById("btn-tournament-add-guest").addEventListener("click", () => {
  document.getElementById("guest-name").value = "";
  document.getElementById("guest-skill").value = "3";
  document.getElementById("guest-gk-status").value = "can_play";
  document.getElementById("guest-form-overlay").hidden = false;
  document.getElementById("guest-name").focus();
});

document.getElementById("btn-generate-all-matches").addEventListener("click", async () => {
  const checkedBoxes = document.querySelectorAll("#tournament-squad-list .avail-check:checked");
  const availablePlayerIds = Array.from(checkedBoxes).map(cb => parseInt(cb.dataset.pid));
  const teamSize = activeTournamentData?.tournament?.team_size || tournamentSelectedSize || 5;

  if (availablePlayerIds.length < teamSize) {
    alert(`Select at least ${teamSize} players.`);
    return;
  }

  const btn = document.getElementById("btn-generate-all-matches");
  btn.disabled = true;

  for (let i = 1; i <= pendingNumMatches; i++) {
    btn.textContent = `Generating ${i} of ${pendingNumMatches}…`;
    await api.addTournamentMatch(activeTournamentId, {
      opponent: `Match ${i}`,
      stage: "group",
      available_player_ids: availablePlayerIds,
    }).catch(() => {});
  }

  btn.disabled = false;
  btn.textContent = "Generate Matches ▶";
  loadTournamentLobby(activeTournamentId);
});

// ── Tournament Lobby ──────────────────────────────────────────────────────────
async function loadTournamentLobby(id) {
  activeTournamentId = id;
  showScreen("screen-tournament-lobby");

  document.getElementById("lobby-match-list").innerHTML = "<li class='loading'>Loading…</li>";
  document.getElementById("add-match-panel").hidden = true;

  const data = await api.getTournament(id).catch(err => {
    alert(err.message);
    loadTournamentHome();
    return null;
  });
  if (!data) return;

  activeTournamentData = data;
  const t = data.tournament;
  document.getElementById("lobby-title").textContent = t.name || "Tournament";

  // Summary
  const date = new Date(t.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  document.getElementById("lobby-summary").innerHTML =
    `<span class="match-badge size-badge">${t.team_size}v${t.team_size}</span>` +
    `<span class="match-badge">${t.formation}</span>` +
    `<span class="match-badge">${dateStr}</span>` +
    `<span class="match-badge">${t.match_duration_mins} min matches</span>`;

  // Match list
  renderLobbyMatches(data.matches);

  // Guest players strip
  renderLobbyGuests(data.guest_players, t.id);
}

document.getElementById("btn-lobby-back").addEventListener("click", loadTournamentHome);

function renderLobbyMatches(matches) {
  const list = document.getElementById("lobby-match-list");
  list.innerHTML = "";

  if (!matches || matches.length === 0) {
    list.innerHTML = "<li class='empty-state'>No matches yet — add one below</li>";
    return;
  }

  matches.forEach(m => {
    const stageLabel = m.tournament_stage === "knockout" ? "KO" : `G${m.match_number || ""}`;
    let statusBadge = "";
    if (m.status === "completed") {
      statusBadge = `<span class="match-badge match-badge-done">FT</span>`;
    } else if (m.status === "in_progress") {
      statusBadge = `<span class="match-badge match-badge-live">● Live</span>`;
    }
    const li = document.createElement("li");
    li.className = "match-item";
    if (m.status === "completed") li.classList.add("match-item-done");
    li.innerHTML = `
      <div class="match-item-main">
        <span class="match-badge">${stageLabel}</span>
        <span class="match-item-opponent">vs ${m.opponent || "TBD"}</span>
        ${statusBadge}
      </div>
    `;
    li.querySelector(".match-item-main").addEventListener("click", () => {
      pitchBackContext = "tournament";
      openMatch(m.id);
    });
    list.appendChild(li);
  });
}

function renderLobbyGuests(guestPlayers, tournamentId) {
  const container = document.getElementById("lobby-guest-list");
  container.innerHTML = "";
  if (!guestPlayers || guestPlayers.length === 0) return;

  guestPlayers.forEach(p => {
    const row = document.createElement("div");
    row.className = "guest-player-row";
    row.innerHTML = `
      <span class="avail-name">${p.name}</span>
      <span class="avail-guest-tag">Guest</span>
      <span class="avail-skill">★${p.skill_rating}</span>
      <button class="btn-icon avail-remove-guest" data-pid="${p.id}" title="Remove guest">✕</button>
    `;
    row.querySelector(".avail-remove-guest").addEventListener("click", async () => {
      await api.removeGuestPlayer(tournamentId, p.id).catch(err => alert(err.message));
      loadTournamentLobby(tournamentId);
    });
    container.appendChild(row);
  });
}

// ── Add match panel ───────────────────────────────────────────────────────────
function openAddMatchPanel(stage) {
  activeTournamentStage = stage;
  document.getElementById("add-match-title").textContent =
    stage === "knockout" ? "Add Knockout Match" : "Add Group Match";
  document.getElementById("add-match-opponent").value = "";
  document.getElementById("knockout-options").hidden = stage !== "knockout";
  document.getElementById("knockout-fairness-slider").value = 75;
  updateKnockoutFairnessLabel(75);
  document.getElementById("add-match-panel").hidden = false;
}

document.getElementById("btn-add-group-match").addEventListener("click", () => openAddMatchPanel("group"));
document.getElementById("btn-add-knockout-match").addEventListener("click", () => openAddMatchPanel("knockout"));
document.getElementById("btn-add-match-cancel").addEventListener("click", () => {
  document.getElementById("add-match-panel").hidden = true;
});

function updateKnockoutFairnessLabel(value) {
  const el = document.getElementById("knockout-fairness-label");
  const v = parseInt(value);
  if (v <= 40) el.textContent = "Balanced — skill matters but everyone plays";
  else if (v <= 70) el.textContent = "Competitive — best players get more time";
  else el.textContent = "Win mode — strongest lineup prioritised";
}

document.getElementById("knockout-fairness-slider").addEventListener("input", e => {
  updateKnockoutFairnessLabel(e.target.value);
});

// Guest player form (overlay)
document.getElementById("btn-show-add-guest").addEventListener("click", () => {
  document.getElementById("guest-name").value = "";
  document.getElementById("guest-skill").value = "3";
  document.getElementById("guest-gk-status").value = "can_play";
  document.getElementById("guest-form-overlay").hidden = false;
  document.getElementById("guest-name").focus();
});

document.getElementById("btn-add-guest-cancel").addEventListener("click", () => {
  document.getElementById("guest-form-overlay").hidden = true;
});

document.getElementById("guest-player-form").addEventListener("submit", async e => {
  e.preventDefault();
  const name = document.getElementById("guest-name").value.trim();
  if (!name) { document.getElementById("guest-name").focus(); return; }
  const gkStatus = document.getElementById("guest-gk-status").value;
  const skill = parseInt(document.getElementById("guest-skill").value) || 3;

  const btn = document.getElementById("btn-add-guest-confirm");
  btn.disabled = true;
  btn.textContent = "Adding…";

  const guest = await api.addGuestPlayer(activeTournamentId, {
    name, gk_status: gkStatus, skill_rating: skill,
  }).catch(err => { alert(err.message); return null; });

  btn.disabled = false;
  btn.textContent = "Add Player";
  if (!guest) return;

  document.getElementById("guest-form-overlay").hidden = true;
  loadTournamentLobby(activeTournamentId);
});

// Generate tournament match
document.getElementById("btn-generate-tournament-match").addEventListener("click", async () => {
  const opponent = document.getElementById("add-match-opponent").value.trim();
  if (!opponent) {
    document.getElementById("add-match-opponent").focus();
    return;
  }

  // Use all players currently in the tournament (squad + any guests)
  const t = activeTournamentData;
  const availablePlayerIds = [
    ...(t?.squad_players || []),
    ...(t?.guest_players || []),
  ].map(p => p.id);

  if (availablePlayerIds.length < (t?.tournament?.team_size || 5)) {
    alert(`Need at least ${t?.tournament?.team_size || 5} players. Add more from the squad or add a temporary player.`);
    return;
  }

  const btn = document.getElementById("btn-generate-tournament-match");
  btn.disabled = true;
  btn.textContent = "Generating…";

  const body = {
    opponent,
    stage: activeTournamentStage,
    available_player_ids: availablePlayerIds,
  };

  if (activeTournamentStage === "knockout") {
    body.knockout_fairness_value = parseInt(document.getElementById("knockout-fairness-slider").value);
  }

  const result = await api.addTournamentMatch(activeTournamentId, body).catch(err => {
    alert(err.message);
    return null;
  });

  btn.disabled = false;
  btn.textContent = "Generate ▶";

  if (!result) return;

  document.getElementById("add-match-panel").hidden = true;
  pitchBackContext = "tournament";

  // Update shirt numbers cache
  api.getPlayers().then(players => {
    shirtNumbers = {};
    players.forEach(p => { if (p.shirt_number != null) shirtNumbers[p.name] = p.shirt_number; });
  }).catch(() => {});

  enterPitchView(result);
});

// ── Init: handled in initScreen() above ───────────────────────────────────────
