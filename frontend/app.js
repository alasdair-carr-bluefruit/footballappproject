import { api } from "./api.js";

// ── State ─────────────────────────────────────────────────────────────────────
let currentSlot = 0;
let showingReport = false;
let matchData = null; // { match, slots, warnings }
const goalCounts = {}; // { playerName: count }

// ── Screen management ─────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => { s.hidden = true; });
  document.getElementById(id).hidden = false;
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

    const li = document.createElement("li");
    li.className = "match-item";
    li.innerHTML = `
      <div class="match-item-main">
        <span class="match-item-date">${dateStr}</span>
        <span class="match-item-opponent">vs ${opponent}</span>
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
  Object.keys(goalCounts).forEach(k => delete goalCounts[k]);
  showScreen("screen-pitch");
  // Reset any inline styles left over from a previous report view
  document.querySelector(".pitch-wrapper").style.display = "";
  document.querySelector(".bench-section").style.display = "";
  document.getElementById("report-section").style.display = "none";
  document.querySelector(".progress-dots").style.display = "";
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

document.getElementById("btn-go-new-match").addEventListener("click", () => {
  document.getElementById("match-date").value = new Date().toISOString().split("T")[0];
  document.getElementById("opponent-input").value = "";
  document.getElementById("btn-generate").disabled = false;
  document.getElementById("btn-generate").textContent = "Generate Rotation ▶";
  showScreen("screen-new-match");
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

  try {
    const match = await api.createMatch({ date, opponent });
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
  document.getElementById("input-name").focus();
}

function closePlayerForm() {
  document.getElementById("player-form").hidden = true;
  editingPlayerId = null;
}

document.getElementById("btn-squad-back").addEventListener("click", loadHome);
document.getElementById("btn-add-player").addEventListener("click", () => openPlayerForm());
document.getElementById("btn-cancel-player").addEventListener("click", closePlayerForm);

// Close when tapping the dark backdrop outside the form card
document.getElementById("player-form").addEventListener("click", e => {
  if (e.target === e.currentTarget) closePlayerForm();
});

document.querySelector("#player-form form").addEventListener("submit", async e => {
  e.preventDefault();
  const data = {
    name:           document.getElementById("input-name").value.trim(),
    gk_status:      document.getElementById("input-gk-status").value,
    def_restricted: document.getElementById("input-def-restricted").checked,
    skill_rating:   parseInt(document.getElementById("input-skill").value, 10),
  };
  if (!data.name) return;

  const id = editingPlayerId;
  closePlayerForm(); // close immediately — prevents double-save

  if (id !== null) {
    await api.updatePlayer(id, data).catch(err => alert(err.message));
  } else {
    await api.addPlayer(data).catch(err => alert(err.message));
  }
  loadSquad();
});

// ── Pitch helpers (same logic as v0.4, adapted for API data shape) ─────────────
function slotObj(slotIndex) {
  return matchData.slots[slotIndex];
}

function quarterLabel(slotIndex) {
  const q = Math.floor(slotIndex / 2) + 1;
  const h = slotIndex % 2 === 0 ? "a" : "b";
  return { q, h, label: `Q${q}${h}` };
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
  const { label } = quarterLabel(currentSlot);
  const incoming = incomingSubs(slot, nextSlot);
  const outgoing = outgoingSubs(slot, nextSlot);

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

  // Build replacement map for bench labels
  const replacementMap = new Map();
  if (nextSlot) {
    ["DEF", "MID1", "MID2", "FWD"].forEach(pos => {
      const cur = slot.lineup[pos]?.name;
      const nxt = nextSlot.lineup[pos]?.name;
      if (nxt && cur && nxt !== cur && incoming.has(nxt)) replacementMap.set(nxt, cur);
    });
    const curGk = slot.lineup.GK?.name;
    const nxtGk = nextSlot.lineup.GK?.name;
    if (nxtGk && curGk && nxtGk !== curGk && incoming.has(nxtGk)) replacementMap.set(nxtGk, curGk);
  }

  // Pitch
  const pitch = document.getElementById("pitch");
  pitch.innerHTML = "";

  const rows = [
    { key: "FWD",  label: "FWD" },
    { key: "MID",  label: "MID" },
    { key: "DEF",  label: "DEF" },
    { key: "GK",   label: "GK"  },
  ];

  rows.forEach(row => {
    const rowEl = document.createElement("div");
    rowEl.className = "pitch-row";

    if (row.key === "MID") {
      rowEl.classList.add("mid-row");
      ["MID1", "MID2"].forEach(pos => {
        const name = slot.lineup[pos]?.name ?? "?";
        rowEl.appendChild(playerCircle(name, "MID", incoming.has(name), outgoing.has(name)));
      });
    } else {
      const name = slot.lineup[row.key]?.name ?? "?";
      const isGk = row.key === "GK";
      rowEl.appendChild(playerCircle(name, row.label, incoming.has(name), outgoing.has(name), isGk));
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
    // Only say "On for X" if X is actually going to the bench, not just changing position
    const subLabel = incoming.has(p.name)
      ? `<span class="bench-arrow">↑ ${replacing && outgoing.has(replacing) ? `On for ${replacing}` : "On"}</span>`
      : "";

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
  if (currentSlot === matchData.slots.length - 1) {
    btnNext.textContent = "Full time ▶";
    btnNext.disabled = false;
  } else if (currentSlot % 2 === 0) {
    btnNext.textContent = "Next half ▶";
  } else {
    btnNext.textContent = "Next quarter ▶";
  }
}

// ── Report ────────────────────────────────────────────────────────────────────
function renderReport() {
  // Collect all players from first slot
  const allPlayers = [
    ...Object.values(matchData.slots[0].lineup),
    ...matchData.slots[0].bench,
  ].sort((a, b) => a.name.localeCompare(b.name));

  const perSlot = {};
  allPlayers.forEach(p => { perSlot[p.name] = Array(8).fill(null); });

  matchData.slots.forEach(slot => {
    Object.entries(slot.lineup).forEach(([pos, p]) => {
      const displayPos = pos.startsWith("MID") ? "MID" : pos;
      perSlot[p.name][slot.slot_index] = displayPos;
    });
  });

  const match = matchData.match;
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  document.getElementById("slot-label").textContent = "Full Time";
  document.getElementById("slot-counter").textContent = "Match report";
  document.getElementById("match-title").textContent = `${dateStr}  ·  vs ${match.opponent || "Unknown"}`;

  document.querySelector(".pitch-wrapper").style.display = "none";
  document.querySelector(".bench-section").style.display = "none";
  document.getElementById("report-section").style.display = "block";
  document.querySelector(".progress-dots").style.display = "none";

  const slotLabels = ["Q1a","Q1b","Q2a","Q2b","Q3a","Q3b","Q4a","Q4b"];
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

  document.getElementById("btn-prev").disabled = false;
  document.getElementById("btn-next").disabled = true;
  document.getElementById("btn-next").textContent = "Full time";
}

function showMatch() {
  showingReport = false;
  document.querySelector(".pitch-wrapper").style.display = "";
  document.querySelector(".bench-section").style.display = "";
  document.getElementById("report-section").style.display = "none";
  document.querySelector(".progress-dots").style.display = "";
  render();
}

// ── Pitch controls ────────────────────────────────────────────────────────────
document.getElementById("btn-next").addEventListener("click", () => {
  if (showingReport) return;
  if (currentSlot < matchData.slots.length - 1) {
    currentSlot++;
    render();
  } else {
    showingReport = true;
    renderReport();
  }
});

document.getElementById("btn-prev").addEventListener("click", () => {
  if (showingReport) { showMatch(); return; }
  if (currentSlot > 0) { currentSlot--; render(); }
});

// "Back to matches" from pitch header
document.getElementById("btn-pitch-back").addEventListener("click", loadHome);

// ── Init ──────────────────────────────────────────────────────────────────────
loadHome();
