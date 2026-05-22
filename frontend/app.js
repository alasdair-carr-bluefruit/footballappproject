import { api } from "./api.js";

// ── State ─────────────────────────────────────────────────────────────────────
let currentSlot = 0;
let showingReport = false;
let showingChanges = false;
let matchData = null; // { match, slots, warnings }
const goalCounts = {}; // { playerName: count }
let gameConfigs = null; // cached from /api/matches/config/game-configs
let selectedSize = 5;

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

function formationPositions(notation) {
  const { defense, midfield, forward } = parseFormation(notation);
  const positions = [];
  for (let i = 1; i <= defense; i++) positions.push(i === 1 ? "DEF" : `DEF${i}`);
  for (let i = 1; i <= midfield; i++) positions.push(`MID${i}`);
  for (let i = 1; i <= forward; i++) positions.push(i === 1 ? "FWD" : `FWD${i}`);
  return positions;
}

function normalizePos(pos) {
  if (pos.startsWith("MID")) return "MID";
  if (pos.startsWith("DEF")) return "DEF";
  if (pos.startsWith("FWD")) return "FWD";
  return pos;
}

// ── Home screen ───────────────────────────────────────────────────────────────
async function loadHome() {
  showScreen("screen-home");
  const list = document.getElementById("match-list");
  list.innerHTML = "<li class='loading'>Loading…</li>";

  const matches = await api.getMatches().catch(() => []);
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

    const li = document.createElement("li");
    li.className = "match-item";
    li.innerHTML = `
      <div class="match-item-main">
        <span class="match-item-date">${dateStr}</span>
        <span class="match-item-opponent">vs ${opponent}</span>
        ${sizeBadge}
        ${m.has_rotation ? "" : "<span class='match-badge'>No rotation</span>"}
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
  currentSlot = 0;
  showingReport = false;
  showingChanges = false;
  Object.keys(goalCounts).forEach(k => delete goalCounts[k]);
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

document.getElementById("btn-go-squad").addEventListener("click", loadSquad);

// ── New match screen ──────────────────────────────────────────────────────────
document.getElementById("btn-new-match-back").addEventListener("click", loadHome);

document.getElementById("new-match-form").addEventListener("submit", async e => {
  e.preventDefault();
  const btn = document.getElementById("btn-generate");
  btn.disabled = true;
  btn.textContent = "Generating…";

  const date = document.getElementById("match-date").value || new Date().toISOString().split("T")[0];
  const opponent = document.getElementById("opponent-input").value.trim();
  const formation = document.getElementById("formation-select").value;
  const fairness = parseInt(document.getElementById("fairness-slider").value) === 0 ? "equal" : "competitive";

  try {
    const match = await api.createMatch({
      date, opponent, team_size: selectedSize, formation, fairness,
    });
    const data = await api.generateRotation(match.id);
    enterPitchView(data);
  } catch (err) {
    alert("Error: " + err.message);
    btn.disabled = false;
    btn.textContent = "Generate Rotation ▶";
  }
});

// ── Squad screen ──────────────────────────────────────────────────────────────
let editingPlayerId = null;

async function loadSquad() {
  showScreen("screen-squad");
  closePlayerForm();
  const players = await api.getPlayers().catch(() => []);
  const list = document.getElementById("player-list");
  list.innerHTML = "";

  if (players.length === 0) {
    list.innerHTML = "<li class='empty-state'>No players yet</li>";
  }

  players.forEach(p => {
    const badges = [];
    if (p.gk_status === "specialist") badges.push('<span class="badge badge-gk">GK Specialist</span>');
    else if (p.gk_status === "preferred") badges.push('<span class="badge badge-gkpref">GK Preferred</span>');
    else if (p.gk_status === "can_play") badges.push('<span class="badge badge-gkcan">GK Can Play</span>');
    else if (p.gk_status === "emergency_only") badges.push('<span class="badge badge-emergency">Emergency GK</span>');
    if (p.def_restricted) badges.push('<span class="badge badge-def">No DEF</span>');
    if (p.best_position) badges.push(`<span class="badge badge-pos">${p.best_position}</span>`);

    const li = document.createElement("li");
    li.className = "player-item";
    li.innerHTML = `
      <div class="player-item-info">
        <span class="player-item-name">${p.name}</span>
        <span class="player-item-badges">${badges.join("")}</span>
      </div>
      <div class="player-item-actions">
        <button class="btn-sm" data-edit="${p.id}">Edit</button>
        <button class="btn-sm btn-danger" data-del="${p.id}">✕</button>
      </div>
    `;
    li.querySelector(`[data-edit]`).addEventListener("click", () => openPlayerForm(p));
    li.querySelector(`[data-del]`).addEventListener("click", async () => {
      await api.deletePlayer(p.id).catch(err => alert(err.message));
      loadSquad();
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
  document.getElementById("input-gk-status").value = player?.gk_status ?? "can_play";
  document.getElementById("input-def-restricted").checked = player?.def_restricted ?? false;
  document.getElementById("input-skill").value = player?.skill_rating ?? 3;

  // Position checkboxes
  const prefs = player?.preferred_positions || [];
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

document.getElementById("btn-squad-back").addEventListener("click", loadHome);
document.getElementById("btn-add-player").addEventListener("click", () => openPlayerForm());
document.getElementById("btn-cancel-player").addEventListener("click", closePlayerForm);

document.getElementById("player-form").addEventListener("click", e => {
  if (e.target === e.currentTarget) closePlayerForm();
});

document.querySelector("#player-form form").addEventListener("submit", async e => {
  e.preventDefault();
  const preferred = [...document.querySelectorAll("#position-checkboxes input:checked")].map(cb => cb.value);
  const data = {
    name:                document.getElementById("input-name").value.trim(),
    gk_status:           document.getElementById("input-gk-status").value,
    def_restricted:      document.getElementById("input-def-restricted").checked,
    skill_rating:        parseInt(document.getElementById("input-skill").value, 10),
    preferred_positions: preferred,
    best_position:       document.getElementById("input-best-position").value,
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
function playerCircle(name, role, isIncoming, isOutgoing, isGk = false) {
  const div = document.createElement("div");
  div.className = "player-circle tappable";
  if (isIncoming) div.classList.add("incoming");
  if (isGk) div.classList.add("is-gk");

  const goals = goalCounts[name] || 0;
  const initials = name.slice(0, 3).toUpperCase();
  div.innerHTML = `
    <div class="circle-avatar">${initials}</div>
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

  const { defense, midfield, forward } = parseFormation(formation);

  // Build rows: FWD, MID, DEF, GK (top to bottom)
  const rows = [
    { type: "FWD", count: forward },
    { type: "MID", count: midfield },
    { type: "DEF", count: defense },
    { type: "GK", count: 1 },
  ];

  rows.forEach(row => {
    const rowEl = document.createElement("div");
    rowEl.className = "pitch-row";
    if (row.count > 1) rowEl.classList.add("multi-row");

    for (let i = 1; i <= row.count; i++) {
      let posKey;
      if (row.type === "GK") {
        posKey = "GK";
      } else if (row.type === "MID") {
        posKey = `MID${i}`;
      } else if (row.type === "DEF") {
        posKey = i === 1 ? "DEF" : `DEF${i}`;
      } else {
        posKey = i === 1 ? "FWD" : `FWD${i}`;
      }
      const name = slot.lineup[posKey]?.name ?? "?";
      const displayRole = row.type;
      const isGk = row.type === "GK";
      rowEl.appendChild(playerCircle(name, displayRole, incoming.has(name), outgoing.has(name), isGk));
    }

    pitch.appendChild(rowEl);
  });

  // Bench
  const bench = document.getElementById("bench-list");
  bench.innerHTML = "";
  slot.bench.forEach(p => {
    const li = document.createElement("li");
    li.className = "bench-player";
    if (incoming.has(p.name)) li.classList.add("incoming");

    const initials = p.name.slice(0, 3).toUpperCase();
    const replacing = replacementMap.get(p.name);
    const subLabel = replacing ? `<span class="bench-arrow">↑ On for ${replacing}</span>` : "";

    li.innerHTML = `
      <span class="bench-avatar">${initials}</span>
      <span class="bench-name">${p.name}</span>
      ${subLabel}
    `;
    bench.appendChild(li);
  });

  // Buttons
  document.getElementById("btn-prev").disabled = currentSlot === 0;
  const btnNext = document.getElementById("btn-next");
  btnNext.disabled = false;
  if (currentSlot === matchData.slots.length - 1) {
    btnNext.textContent = "Full time ▶";
  } else {
    btnNext.textContent = "Next ▶";
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
  document.getElementById("btn-next").disabled = true;
  document.getElementById("btn-next").textContent = "Full time";
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
document.getElementById("btn-next").addEventListener("click", () => {
  if (showingReport) return;
  if (showingChanges) {
    showingChanges = false;
    showMatch();
    return;
  }
  if (currentSlot < matchData.slots.length - 1) {
    currentSlot++;
    if (currentSlot % 2 === 0 && currentSlot > 0) {
      showingChanges = true;
      renderChanges();
    } else {
      render();
    }
  } else {
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

document.getElementById("btn-pitch-back").addEventListener("click", loadHome);

// ── Init ──────────────────────────────────────────────────────────────────────
loadHome();
