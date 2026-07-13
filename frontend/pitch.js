import { api } from "./api.js";
import { state, refreshShirtNumbers } from "./state.js";
import { loadHome } from "./season.js";
import { loadTournamentLobby } from "./tournament.js";

// NOTE on circular imports: pitch.js needs to navigate back into season.js
// (loadHome) and tournament.js (loadTournamentLobby) after a match ends or
// the coach backs out, while season.js/tournament.js both need to call INTO
// pitch.js (enterPitchView/openMatch) to display a match. This is a genuine
// mutual dependency, not an accident. It's safe because every cross-reference
// here is to a hoisted `function`/`async function` declaration, and every
// call happens inside an event listener or async handler — never at
// synchronous module top-level — so both sides are always fully loaded by
// the time either function actually runs.

// ── Formation layout helpers (pitch rendering only — NOT used by the
// season/tournament setup-form dropdowns, which build from `gameConfigs`) ──
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

// Returns true if this player's shirt number is shared and they are the LATER entry
// (i.e. the "duplicate" — their number shows in red)
function isShirtConflict(name) {
  const num = state.shirtNumbers[name];
  if (num == null) return false;
  const allNames = Object.keys(state.shirtNumbers);
  const firstOwner = allNames.find(n => state.shirtNumbers[n] === num);
  return firstOwner !== name;
}

function slotCountForPlayer(playerName) {
  if (!state.matchData) return 0;
  return state.matchData.slots.filter(s => Object.values(s.lineup).some(p => p.name === playerName)).length;
}

// ── Pitch helpers ─────────────────────────────────────────────────────────────
function slotObj(slotIndex) {
  return state.matchData.slots[slotIndex];
}

function periodLabel(slotIndex) {
  const label = state.matchData.match.period_label || "Quarter";
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

  const goals = state.goalCounts[name] || 0;
  const shirtNum = state.shirtNumbers[name];
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
      state.goalCounts[name] = Math.max(0, (state.goalCounts[name] || 0) - 1);
      render();
    });
    avatar.appendChild(goalBadge);
  }

  let pressTimer = null;
  div.addEventListener("pointerdown", () => {
    if (state.editMode || !state.matchStarted) return; // no goals while adjusting plan or reviewing
    pressTimer = setTimeout(() => {
      pressTimer = null;
      state.goalCounts[name] = (state.goalCounts[name] || 0) + 1;
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
      if (state.editMode || pressTimer !== null) {
        onSwapClick();
      }
    });
  }

  // Drag-and-drop for same-slot position swaps in edit mode
  if (dragData) {
    div.draggable = true;
    div.addEventListener("dragstart", e => {
      clearTimeout(pressTimer);
      state.dragState = { slotIndex: dragData.slotIndex, posKey: dragData.posKey, playerName: name };
      e.dataTransfer.effectAllowed = "move";
      setTimeout(() => div.classList.add("dragging"), 0);
    });
    div.addEventListener("dragover", e => {
      if (state.dragState && state.dragState.slotIndex === dragData.slotIndex && state.dragState.posKey !== dragData.posKey) {
        e.preventDefault();
        div.classList.add("drag-over");
      }
    });
    div.addEventListener("dragleave", () => div.classList.remove("drag-over"));
    div.addEventListener("dragend", () => {
      div.classList.remove("dragging");
      state.dragState = null;
    });
    div.addEventListener("drop", e => {
      e.preventDefault();
      div.classList.remove("drag-over");
      if (!state.dragState || state.dragState.slotIndex !== dragData.slotIndex || state.dragState.posKey === dragData.posKey) return;
      // Same slot, different position — swap locally
      const slot = state.matchData.slots[dragData.slotIndex];
      const playerA = slot.lineup[state.dragState.posKey];
      const playerB = slot.lineup[dragData.posKey];
      slot.lineup[state.dragState.posKey] = playerB;
      slot.lineup[dragData.posKey] = playerA;
      state.lockedSlots.add(dragData.slotIndex);
      state.dragState = null;
      render();
    });
  }

  return div;
}

function render() {
  const slot = slotObj(state.currentSlot);
  const nextSlot = state.matchData.slots[state.currentSlot + 1] || null;
  const { label } = periodLabel(state.currentSlot);
  const formation = state.matchData.match.formation || "1-2-1";
  const teamSize = state.matchData.match.team_size || 5;

  // Only show sub arrows on 'a' slots (mid-period transitions)
  const isMidPeriod = state.currentSlot % 2 === 0 && nextSlot;
  const incoming = isMidPeriod ? incomingSubs(slot, nextSlot) : new Set();
  const outgoing = isMidPeriod ? outgoingSubs(slot, nextSlot) : new Set();

  const match = state.matchData.match;
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  document.getElementById("match-title").textContent =
    `${dateStr}  ·  vs ${match.opponent || "Unknown"}`;
  document.getElementById("slot-label").textContent = label;
  document.getElementById("slot-counter").textContent =
    `Slot ${state.currentSlot + 1} of ${state.matchData.slots.length}`;

  const skillEl = document.getElementById("slot-skill");
  const skillTotal = slot.skill_total || 0;
  if (skillTotal > 0) {
    skillEl.textContent = `⚡ ${skillTotal}`;
    skillEl.hidden = false;
  } else {
    skillEl.hidden = true;
  }

  const dots = document.querySelectorAll(".progress-dot");
  const totalSlotDots = state.matchData.slots.length;
  dots.forEach((dot, i) => {
    const isFinalDot = i === totalSlotDots;
    dot.classList.toggle("active", !isFinalDot && i === state.currentSlot);
    dot.classList.toggle("done", !isFinalDot && i < state.currentSlot);
    if (isFinalDot) { dot.classList.remove("active", "done"); }
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
  if (state.editMode) pitch.classList.add("edit-mode");

  // Whiteboard mode — paper look when adjusting plan
  const pitchWrapper = document.querySelector(".pitch-wrapper");
  const benchSection = document.querySelector(".bench-section");
  pitchWrapper?.classList.toggle("whiteboard", state.editMode);
  benchSection?.classList.toggle("whiteboard", state.editMode);
  document.getElementById("edit-mode-badge").classList.toggle("visible", state.editMode);

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
      const player = slot.lineup[posKey];
      const name = player?.name ?? "";
      const isEmpty = !name;
      const isGk = posKey === "GK";
      const swapHandler = state.editMode ? () => openSwapPicker(state.currentSlot, posKey, name) : null;
      const dragData = state.editMode && !isEmpty ? { slotIndex: state.currentSlot, posKey } : null;
      const circle = playerCircle(name || posKey, posKey, incoming.has(name), outgoing.has(name), isGk, swapHandler, dragData);
      if (isEmpty) circle.classList.add("empty-slot");
      rowEl.appendChild(circle);
    });

    pitch.appendChild(rowEl);
  });

  // Build set of removed player IDs for quick lookup
  const removedIds = new Set(Object.keys(state.removedPlayers).map(Number));

  // Bench
  const bench = document.getElementById("bench-list");
  bench.innerHTML = "";
  slot.bench.forEach(p => {
    const isRemoved = removedIds.has(p.id);
    const li = document.createElement("li");
    li.className = "bench-player";
    if (incoming.has(p.name)) li.classList.add("incoming");
    if (isRemoved) li.classList.add("bench-removed");

    const shirtNum = state.shirtNumbers[p.name];
    const avatarContent = shirtNum != null ? String(shirtNum) : p.name.slice(0, 3).toUpperCase();
    const replacing = replacementMap.get(p.name);
    const subLabel = replacing ? `<span class="bench-arrow">↑ On for ${replacing}</span>` : "";
    const removedLabel = isRemoved ? `<span class="bench-removed-badge">Removed</span>` : "";

    li.innerHTML = `
      <span class="bench-avatar">${avatarContent}</span>
      <span class="bench-name">${p.name}</span>
      ${subLabel}${removedLabel}
    `;

    if (state.matchStarted) {
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
  const isCompleted = state.matchData.match.status === "completed";
  const isLastSlot = state.currentSlot === state.matchData.slots.length - 1;
  document.getElementById("live-pitch-badge").classList.toggle("visible", state.matchStarted && !isCompleted);

  // Manual assign bar: visible in review mode when not already in manual/edit mode
  const manualAssignBar = document.getElementById("manual-assign-bar");
  if (manualAssignBar) {
    manualAssignBar.hidden = state.matchStarted || state.editMode || state.manualRotationMode || state.showingReport;
  }

  if (!state.matchStarted) {
    // Review mode: coach browses the plan before starting
    startMatchBar.hidden = state.editMode;
    endMatchBar.hidden = true;
    liveBadge.hidden = true;
    btnPrev.disabled = state.currentSlot === 0 || state.editMode;
    btnNext.disabled = state.editMode;
    btnNext.textContent = (isLastSlot && !state.editMode) ? "Summary ▶" : "Next ▶";
    btnAdjust.hidden = false;
    btnAdjust.textContent = state.editMode ? "Done" : "Tinker";
  } else {
    // Live mode (in_progress or completed)
    startMatchBar.hidden = true;
    endMatchBar.hidden = isCompleted;
    liveBadge.hidden = isCompleted;
    // "Return to plan review" only available before any slot has been advanced
    document.getElementById("btn-return-plan").hidden = state.currentSlot !== 0 || isCompleted;
    btnPrev.disabled = state.currentSlot === 0 || state.editMode;
    btnNext.disabled = state.editMode || (isCompleted && isLastSlot);
    btnNext.textContent = isLastSlot ? "Match Report ▶" : "Next ▶";

    // Past slots (already played) — hide Tinker to prevent editing history
    const isPastSlot = state.currentSlot < (state.matchData.match.current_slot || 0);
    if (isPastSlot || isCompleted) {
      btnAdjust.hidden = true;
    } else {
      btnAdjust.hidden = false;
      btnAdjust.textContent = state.editMode ? "Done" : "Tinker";
    }
  }

  // Show locked badge in slot label
  const slotLabelEl = document.getElementById("slot-label");
  if (state.lockedSlots.has(state.currentSlot)) {
    slotLabelEl.innerHTML += ' <span class="slot-locked-badge">LOCKED</span>';
  }

  // New-period clock prompt: at the start of a new quarter/half in a live match,
  // offer to reset the clock (unless already handled for this slot)
  const hint = document.getElementById("new-period-hint");
  const atNewPeriod = state.matchStarted && !isCompleted && !state.showingReport
    && state.currentSlot > 0 && state.currentSlot % 2 === 0;
  if (atNewPeriod && state.newPeriodHintSlot !== state.currentSlot) {
    const label = (state.matchData.match.period_label || "Quarter").toLowerCase();
    document.getElementById("new-period-hint-text").textContent =
      `New ${label} — reset the match clock?`;
    hint.hidden = false;
  } else {
    hint.hidden = true;
  }
}

// ── Quarter-break changes interstitial ────────────────────────────────────────
function renderChanges() {
  const prevSlot = slotObj(state.currentSlot - 1);
  const nextSlot = slotObj(state.currentSlot);
  const prevP = Math.floor((state.currentSlot - 1) / 2) + 1;
  const nextP = Math.floor(state.currentSlot / 2) + 1;
  const pLabel = (state.matchData.match.period_label || "Quarter") === "Half" ? "H" : "Q";

  const off = outgoingSubs(prevSlot, nextSlot);
  const on  = incomingSubs(prevSlot, nextSlot);
  const formation = state.matchData.match.formation || "1-2-1";

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

  const match = state.matchData.match;
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  document.getElementById("match-title").textContent =
    `${dateStr}  ·  vs ${match.opponent || "Unknown"}`;
  document.getElementById("slot-label").textContent = `${pLabel}${prevP} → ${pLabel}${nextP}`;
  document.getElementById("slot-counter").textContent =
    off.size === 0 ? "No changes" : `${off.size} change${off.size !== 1 ? "s" : ""}`;
  document.getElementById("slot-skill").hidden = true;

  const dots = document.querySelectorAll(".progress-dot");
  dots.forEach((dot, i) => {
    dot.classList.toggle("active", false);
    dot.classList.toggle("done", i < state.currentSlot);
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
  const periodLbl = (state.matchData.match.period_label || "Quarter") === "Half" ? "Half" : "Quarter";
  btnNext.textContent = `Start ${periodLbl} ${nextP} ▶`;
}

// ── Report ────────────────────────────────────────────────────────────────────
function renderReport() {
  const allPlayers = [
    ...Object.values(state.matchData.slots[0].lineup),
    ...state.matchData.slots[0].bench,
  ].sort((a, b) => a.name.localeCompare(b.name));

  const totalSlots = state.matchData.slots.length;
  const perSlot = {};
  allPlayers.forEach(p => { perSlot[p.name] = Array(totalSlots).fill(null); });

  state.matchData.slots.forEach(slot => {
    Object.entries(slot.lineup).forEach(([pos, p]) => {
      const displayPos = normalizePos(pos);
      perSlot[p.name][slot.slot_index] = displayPos;
    });
  });

  const match = state.matchData.match;
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const pLabel = (match.period_label || "Quarter") === "Half" ? "H" : "Q";

  document.getElementById("slot-label").textContent = state.matchStarted ? "Full Time" : "Summary";
  document.getElementById("slot-counter").textContent = state.matchStarted ? "Match report" : "All slots";
  document.getElementById("slot-skill").hidden = true;
  document.getElementById("match-title").textContent = `${dateStr}  ·  vs ${match.opponent || "Unknown"}`;

  document.querySelector(".pitch-wrapper").style.display = "none";
  document.querySelector(".bench-section").style.display = "none";
  document.getElementById("report-section").style.display = "block";

  // Keep progress dots visible — activate the Final dot
  document.getElementById("progress-dots").style.display = "";
  const allDots = document.querySelectorAll(".progress-dot");
  allDots.forEach((dot, i) => {
    const isFinalDot = dot.classList.contains("progress-dot-final");
    dot.classList.toggle("active", isFinalDot);
    dot.classList.toggle("done", !isFinalDot);
  });

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
    const goals = state.goalCounts[name] || 0;

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
  const skillChipsHtml = state.matchData.slots.map((slot, i) =>
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
  if (state.matchStarted) {
    document.getElementById("btn-next").disabled = false;
    document.getElementById("btn-next").textContent = "End Match";
  } else {
    document.getElementById("btn-next").disabled = true;
    document.getElementById("btn-next").textContent = "Next ▶";
  }
  document.getElementById("btn-adjust").hidden = true;
  // End Match bar: visible in live mode on report view
  const endBar = document.getElementById("end-match-bar");
  if (endBar) endBar.hidden = !state.matchStarted || state.matchData.match.status === "completed";
  document.getElementById("start-match-bar").hidden = true;
  document.getElementById("manual-assign-bar").hidden = true;
}

function showMatch() {
  state.showingReport = false;
  state.showingChanges = false;
  document.querySelector(".pitch-wrapper").style.display = "";
  document.querySelector(".bench-section").style.display = "";
  document.getElementById("report-section").style.display = "none";
  document.getElementById("progress-dots").style.display = "";
  render();
}

function enterPitchView(data) {
  state.matchData = data;
  state.showingReport = false;
  state.showingChanges = false;
  if (!state.manualRotationMode) state.editMode = false;
  state.manualRotationMode = data.manual_mode || false;
  state.lockedSlots = new Set(data.locked_slots || []);
  state.removedPlayers = data.removed_players || {};
  Object.keys(state.goalCounts).forEach(k => delete state.goalCounts[k]);

  // Determine match state
  const status = data.match?.status || "planned";
  state.matchStarted = status !== "planned";
  state.currentSlot = state.matchStarted ? (data.match?.current_slot || 0) : 0;

  // Timer: a persistent count-up clock, running only while the match is live
  if (status === "in_progress") {
    resumeMatchTimer();
  } else {
    stopTimerTicker();
  }

  showScreen("screen-pitch");
  document.querySelector(".pitch-wrapper").style.display = "";
  document.querySelector(".bench-section").style.display = "";
  document.getElementById("report-section").style.display = "none";

  // Generate progress dots dynamically (one per slot + a "Final" summary dot)
  const dotsContainer = document.getElementById("progress-dots");
  dotsContainer.innerHTML = "";
  dotsContainer.style.display = "";
  for (let i = 0; i < state.matchData.slots.length; i++) {
    const dot = document.createElement("div");
    dot.className = "progress-dot";
    dotsContainer.appendChild(dot);
  }
  const finalDot = document.createElement("div");
  finalDot.className = "progress-dot progress-dot-final";
  dotsContainer.appendChild(finalDot);

  render();
}

// Wraps enterPitchView for the two "assign positions manually" entry points
// (new-match screen's "or assign positions manually" and the in-pitch-view
// "Manual assign" bar) — both used to set these two flags inline themselves.
function enterManualAssignMode(data) {
  state.manualRotationMode = true;
  state.editMode = true;
  enterPitchView(data);
}

async function openMatch(matchId, backContext = "season") {
  // Route the pitch "back" button explicitly per entry path rather than via a
  // sticky global: season matches reset to "season", tournament matches pass
  // "tournament". Fixes the latent bug where opening any tournament match left
  // pitchBackContext stuck on "tournament" for every later season match.
  state.pitchBackContext = backContext;

  // Ensure shirt numbers are current
  refreshShirtNumbers();

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

// Manual assign from within pitch view (works for both season and tournament matches)
document.getElementById("btn-manual-slots-pitch").addEventListener("click", async () => {
  const btn = document.getElementById("btn-manual-slots-pitch");
  btn.disabled = true;
  btn.textContent = "Setting up…";
  try {
    const data = await api.blankRotation(state.matchData.match.id);
    enterManualAssignMode(data);
  } catch (err) {
    alert("Error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "or assign positions manually";
  }
});

// ── Pitch controls ────────────────────────────────────────────────────────────
document.getElementById("btn-start-match-cta").addEventListener("click", () => doStartMatch());

document.getElementById("btn-next").addEventListener("click", async () => {
  if (state.showingReport) {
    if (state.matchStarted) doEndMatch();
    return;
  }
  if (state.showingChanges) {
    state.showingChanges = false;
    showMatch();
    return;
  }
  if (state.currentSlot < state.matchData.slots.length - 1) {
    const prevSlotObj = state.matchData.slots[state.currentSlot];
    state.currentSlot++;
    // Persist progress when advancing beyond the furthest reached slot
    if (state.matchStarted && state.currentSlot > (state.matchData.match.current_slot || 0)) {
      state.matchData.match.current_slot = state.currentSlot;
      api.updateProgress(state.matchData.match.id, state.currentSlot).catch(() => {});
    }

    // Manual mode: carry prev slot's lineup into the next empty slot, then auto-tinker
    if (state.manualRotationMode) {
      const nextSlotObj = state.matchData.slots[state.currentSlot];
      const nextIsEmpty = Object.keys(nextSlotObj.lineup || {}).length === 0;
      const prevHasLineup = Object.keys(prevSlotObj.lineup || {}).length > 0;
      if (nextIsEmpty && prevHasLineup) {
        const edits = { [state.currentSlot]: {} };
        Object.entries(prevSlotObj.lineup).forEach(([pos, player]) => {
          if (player && player.id != null) edits[state.currentSlot][pos] = player.id;
        });
        const slotsToLock = state.matchData.slots.map(s => s.slot_index);
        const statusEl = document.getElementById("adjust-status");
        statusEl.hidden = false;
        try {
          const result = await api.adjustRotation(state.matchData.match.id, edits, slotsToLock);
          state.matchData.slots = result.slots;
          if (result.locked_slots) state.lockedSlots = new Set(result.locked_slots);
        } catch (_) { /* carry forward failed, slot stays empty */ }
        statusEl.hidden = true;
      }
      state.editMode = true; // always auto-tinker in manual mode when moving to next slot
      render();
      return;
    }

    if (state.currentSlot % 2 === 0 && state.currentSlot > 0) {
      state.showingChanges = true;
      renderChanges();
    } else {
      render();
    }
  } else {
    // Last slot — show match report
    state.showingReport = true;
    renderReport();
  }
});

document.getElementById("btn-prev").addEventListener("click", () => {
  if (state.showingReport) { showMatch(); return; }
  if (state.showingChanges) {
    state.showingChanges = false;
    state.currentSlot--;
    showMatch();
    return;
  }
  if (state.currentSlot > 0) {
    state.currentSlot--;
    render();
  }
});

// ── End match ─────────────────────────────────────────────────────────────────
document.getElementById("btn-end-match").addEventListener("click", () => {
  const isLastSlot = state.currentSlot === state.matchData.slots.length - 1;
  if (state.showingReport || isLastSlot) {
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
  clearMatchTimer();
  // Save goals and mark match completed, then show Full Time screen
  if (state.matchData?.match.id) {
    const oppGoals = state.matchData.match.opponent_goals || 0;
    await api.saveGoals(state.matchData.match.id, state.goalCounts, oppGoals).catch(() => {});
    await api.updateProgress(state.matchData.match.id, state.currentSlot, "completed").catch(() => {});
    state.matchData.match.status = "completed";
  }
  await showFulltime();
}

// ── Match timer ───────────────────────────────────────────────────────────────
// A single count-up match clock, started when the coach taps Start Match. State
// lives in localStorage keyed by match id, so the clock reflects real elapsed
// time regardless of navigating between quarters, going back to the match list,
// or reloading the page — it never resets to 0:00 until the match ends.
function timerKey() {
  return state.matchData?.match?.id != null ? `gaffer_timer_${state.matchData.match.id}` : null;
}

function readTimer() {
  const key = timerKey();
  if (!key) return null;
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch (_) {
    return null;
  }
}

function writeTimer(timerState) {
  const key = timerKey();
  if (key) localStorage.setItem(key, JSON.stringify(timerState));
}

// Elapsed seconds, accounting for any paused intervals
function timerElapsedSecs(timerState) {
  if (!timerState) return 0;
  const end = timerState.pausedAt ?? Date.now();
  return Math.max(0, (end - timerState.startedAt - (timerState.pausedAccumMs || 0)) / 1000);
}

// Called from Start Match — begins a fresh clock for this match
function beginMatchTimer() {
  writeTimer({ startedAt: Date.now(), pausedAt: null, pausedAccumMs: 0 });
  startTimerTicker();
}

// Called on re-entering a live match — resume the existing clock (or start one
// if none is stored, e.g. it was cleared)
function resumeMatchTimer() {
  if (!readTimer()) writeTimer({ startedAt: Date.now(), pausedAt: null, pausedAccumMs: 0 });
  startTimerTicker();
}

// Reset the clock to 0:00 (running) — used from the reset button and the
// new-period prompt
function resetMatchTimer() {
  writeTimer({ startedAt: Date.now(), pausedAt: null, pausedAccumMs: 0 });
  updateTimerDisplay();
}

// Stop ticking + hide, but KEEP the stored clock so it persists across navigation
function stopTimerTicker() {
  clearInterval(state.timerInterval);
  state.timerInterval = null;
  document.getElementById("match-timer").hidden = true;
}

// End the clock for good (full time / return to plan)
function clearMatchTimer() {
  const key = timerKey();
  if (key) localStorage.removeItem(key);
  stopTimerTicker();
}

function startTimerTicker() {
  clearInterval(state.timerInterval);
  state.timerInterval = setInterval(updateTimerDisplay, 500);
  updateTimerDisplay();
}

function updateTimerDisplay() {
  const wrap = document.getElementById("match-timer");
  const timerState = readTimer();
  if (!state.matchStarted || state.showingReport || !timerState) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  const total = Math.floor(timerElapsedSecs(timerState));
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  document.getElementById("timer-display").textContent = `${mm}:${ss}`;
  const paused = timerState.pausedAt != null;
  document.getElementById("btn-timer-pause").textContent = paused ? "▶" : "⏸";
  // Reset is only offered while paused — prevents accidental resets during play
  document.getElementById("btn-timer-reset").hidden = !paused;
}

document.getElementById("btn-timer-pause").addEventListener("click", () => {
  const timerState = readTimer();
  if (!timerState) return;
  if (timerState.pausedAt == null) {
    timerState.pausedAt = Date.now();
  } else {
    timerState.pausedAccumMs = (timerState.pausedAccumMs || 0) + (Date.now() - timerState.pausedAt);
    timerState.pausedAt = null;
  }
  writeTimer(timerState);
  updateTimerDisplay();
});

document.getElementById("btn-timer-reset").addEventListener("click", () => {
  if (readTimer() && confirm("Reset the match clock to 0:00?")) resetMatchTimer();
});

document.getElementById("btn-new-period-reset").addEventListener("click", () => {
  resetMatchTimer();
  state.newPeriodHintSlot = state.currentSlot;
  document.getElementById("new-period-hint").hidden = true;
});

document.getElementById("btn-new-period-dismiss").addEventListener("click", () => {
  state.newPeriodHintSlot = state.currentSlot;
  document.getElementById("new-period-hint").hidden = true;
});

// ── Start match ───────────────────────────────────────────────────────────────
async function doStartMatch() {
  try {
    await api.startMatch(state.matchData.match.id);
    state.matchStarted = true;
    state.matchData.match.status = "in_progress";
    state.matchData.match.current_slot = 0;
    state.currentSlot = 0;          // kick off at the first slot regardless of plan-review position
    state.newPeriodHintSlot = null; // clear any dismissed-hint state from a previous match
    beginMatchTimer();
    render();
    showGoalTip();
  } catch (err) {
    alert("Could not start match: " + err.message);
  }
}

function showGoalTip() {
  const tip = document.getElementById("goal-tip");
  tip.hidden = false;
  clearTimeout(showGoalTip._timer);
  showGoalTip._timer = setTimeout(() => { tip.hidden = true; }, 6000);
}

document.getElementById("btn-goal-tip-dismiss").addEventListener("click", () => {
  document.getElementById("goal-tip").hidden = true;
  clearTimeout(showGoalTip._timer);
});

document.getElementById("btn-return-plan").addEventListener("click", async () => {
  try {
    await api.unstartMatch(state.matchData.match.id);
    state.matchStarted = false;
    state.matchData.match.status = "planned";
    clearMatchTimer();
    render();
  } catch (err) {
    alert("Could not return to plan review: " + err.message);
  }
});

// ── Player removal ─────────────────────────────────────────────────────────────
function openPlayerActionMenu(player) {
  state.pendingActionPlayer = player;
  document.getElementById("player-action-title").textContent = player.name;
  document.getElementById("player-action-overlay").hidden = false;
}

function openReinstateOverlay(player) {
  state.pendingActionPlayer = player;
  document.getElementById("reinstate-title").textContent = player.name;
  document.getElementById("reinstate-info").textContent =
    `${player.name} was removed from the match. Reinstate them from slot ${state.currentSlot + 1} onward?`;
  document.getElementById("reinstate-overlay").hidden = false;
}

document.getElementById("btn-action-cancel").addEventListener("click", () => {
  document.getElementById("player-action-overlay").hidden = true;
  state.pendingActionPlayer = null;
});

document.getElementById("btn-action-goal").addEventListener("click", () => {
  document.getElementById("player-action-overlay").hidden = true;
  if (state.pendingActionPlayer) {
    state.goalCounts[state.pendingActionPlayer.name] = (state.goalCounts[state.pendingActionPlayer.name] || 0) + 1;
    if (navigator.vibrate) navigator.vibrate(80);
    render();
  }
  state.pendingActionPlayer = null;
});

document.getElementById("btn-action-remove").addEventListener("click", async () => {
  document.getElementById("player-action-overlay").hidden = true;
  if (!state.pendingActionPlayer || !state.matchData) { state.pendingActionPlayer = null; return; }

  const player = state.pendingActionPlayer;
  state.pendingActionPlayer = null;

  const statusEl = document.getElementById("adjust-status");
  statusEl.hidden = false;
  try {
    const result = await api.removePlayer(state.matchData.match.id, player.id, state.currentSlot);
    statusEl.hidden = true;
    state.removedPlayers = result.removed_players || {};
    state.matchData.slots = result.slots;
    state.matchData.warnings = result.warnings;
    render();
    showFairnessInfo(result.fairness_warnings);
  } catch (err) {
    statusEl.hidden = true;
    alert("Could not remove player: " + err.message);
  }
});

document.getElementById("btn-reinstate-cancel").addEventListener("click", () => {
  document.getElementById("reinstate-overlay").hidden = true;
  state.pendingActionPlayer = null;
});

document.getElementById("btn-reinstate-confirm").addEventListener("click", async () => {
  document.getElementById("reinstate-overlay").hidden = true;
  if (!state.pendingActionPlayer || !state.matchData) { state.pendingActionPlayer = null; return; }

  const player = state.pendingActionPlayer;
  state.pendingActionPlayer = null;

  const statusEl = document.getElementById("adjust-status");
  statusEl.hidden = false;
  try {
    const result = await api.reinstatePlayer(state.matchData.match.id, player.id);
    statusEl.hidden = true;
    state.removedPlayers = result.removed_players || {};
    state.matchData.slots = result.slots;
    state.matchData.warnings = result.warnings;
    render();
    showFairnessInfo(result.fairness_warnings);
  } catch (err) {
    statusEl.hidden = true;
    alert("Could not reinstate player: " + err.message);
  }
});

// ── Edit mode (adjust plan) ────────────────────────────────────────────────────
document.getElementById("btn-adjust").addEventListener("click", () => {
  state.editMode = !state.editMode;
  const btn = document.getElementById("btn-adjust");
  btn.textContent = state.editMode ? "Done" : "Tinker";
  render();
});

document.getElementById("btn-swap-cancel").addEventListener("click", () => {
  document.getElementById("swap-overlay").hidden = true;
  state.pendingSwap = null;
});

document.getElementById("btn-fairness-cancel").addEventListener("click", () => {
  document.getElementById("fairness-overlay").hidden = true;
});

function openSwapPicker(slotIndex, posKey, currentPlayerName) {
  state.pendingSwap = { slotIndex, posKey, currentPlayerName };
  const slot = state.matchData.slots[slotIndex];
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
    if (p.name !== currentPlayerName) {
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
  if (!state.pendingSwap || !state.matchData) return;

  const { slotIndex, posKey, currentPlayerName } = state.pendingSwap;
  const slot = state.matchData.slots[slotIndex];

  // Build the edit: figure out if this is a bench swap or position swap
  const edits = {};
  const isOnPitch = Object.entries(slot.lineup).find(([, p]) => p.name === newPlayerName);

  if (isOnPitch) {
    // Position-only swap: both players already in this slot, swap positions.
    // Include both positions in the edit so the backend persists the change.
    const [otherPos] = isOnPitch;
    const currentPlayer = slot.lineup[posKey];
    edits[slotIndex] = { [posKey]: newPlayerId, [otherPos]: currentPlayer.id };
  } else {
    // Bench swap: replace current player with bench player
    edits[slotIndex] = { [posKey]: newPlayerId };
  }

  const statusEl = document.getElementById("adjust-status");
  statusEl.hidden = false;

  // In manual mode keep every slot locked so the algorithm never auto-fills empties
  const slotsToLock = state.manualRotationMode
    ? state.matchData.slots.map(s => s.slot_index)
    : [...state.lockedSlots];

  try {
    const result = await api.adjustRotation(
      state.matchData.match.id, edits, slotsToLock,
    );

    statusEl.hidden = true;

    // Check for fairness warnings (skip in manual assign mode)
    if (!state.manualRotationMode && result.fairness_warnings && result.fairness_warnings.length > 0) {
      showFairnessWarning(result);
      return;
    }

    applyAdjustResult(result);
  } catch (err) {
    statusEl.hidden = true;
    alert("Could not adjust: " + err.message);
  }
  state.pendingSwap = null;
}

function fillFairnessList(warnings) {
  const list = document.getElementById("fairness-list");
  list.innerHTML = "";
  warnings.forEach(w => {
    const li = document.createElement("li");
    li.className = "fairness-item";
    const cls = w.diff < 0 ? "fairness-loss" : "fairness-gain";
    const verb = w.diff < 0 ? "loses" : "gains";
    li.innerHTML = `${w.player} <span class="${cls}">${verb} ${Math.abs(w.diff)} slot${Math.abs(w.diff) !== 1 ? "s" : ""}</span> (${w.before} → ${w.after})`;
    list.appendChild(li);
  });
}

function showFairnessWarning(result) {
  fillFairnessList(result.fairness_warnings);
  document.getElementById("btn-fairness-cancel").hidden = false;
  const confirmBtn = document.getElementById("btn-fairness-confirm");
  confirmBtn.textContent = "Apply anyway";

  // Wire confirm button to apply
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

// Informational variant: the recalculation has already been applied (e.g. after
// removing or reinstating a player) — show who gained/lost time, no decision needed
function showFairnessInfo(warnings) {
  if (!warnings || warnings.length === 0) return;
  fillFairnessList(warnings);
  document.getElementById("btn-fairness-cancel").hidden = true;
  const confirmBtn = document.getElementById("btn-fairness-confirm");
  confirmBtn.textContent = "OK";
  const handler = () => {
    document.getElementById("fairness-overlay").hidden = true;
    document.getElementById("btn-fairness-cancel").hidden = false;
    confirmBtn.textContent = "Apply anyway";
    confirmBtn.removeEventListener("click", handler);
  };
  confirmBtn.addEventListener("click", handler);
  document.getElementById("fairness-overlay").hidden = false;
}

function applyAdjustResult(result) {
  state.matchData.slots = result.slots;
  state.matchData.warnings = result.warnings;
  if (result.locked_slots) {
    state.lockedSlots = new Set(result.locked_slots);
  }
  render();
}

// Save goals when leaving pitch view via back button (no opponent goals known yet)
async function saveGoalsIfNeeded() {
  if (!state.matchData || !state.matchData.match.id) return;
  const hasGoals = Object.values(state.goalCounts).some(v => v > 0);
  if (hasGoals) {
    await api.saveGoals(state.matchData.match.id, state.goalCounts, state.matchData.match.opponent_goals || 0).catch(() => {});
  }
}

document.getElementById("btn-pitch-back").addEventListener("click", async () => {
  stopTimerTicker();
  await saveGoalsIfNeeded();
  if (state.pitchBackContext === "tournament" && state.activeTournamentId) {
    loadTournamentLobby(state.activeTournamentId);
  } else {
    loadHome();
  }
});

// ── Full time screen ───────────────────────────────────────────────────────────
async function showFulltime() {
  const match = state.matchData.match;
  const ourGoals = Object.values(state.goalCounts).reduce((sum, n) => sum + n, 0);
  const oppGoals = match.opponent_goals || 0;

  const isHome = (match.home_away || "home") === "home";
  const ourName = state.teamInfo.team_name || "My Team";
  const oppName = match.opponent || "Opponent";

  // Populate team blocks depending on home/away
  document.getElementById("ft-home-name").textContent = isHome ? ourName : oppName;
  document.getElementById("ft-away-name").textContent = isHome ? oppName : ourName;
  document.getElementById("ft-our-score").textContent = isHome ? ourGoals : oppGoals;
  document.getElementById("ft-their-score").textContent = isHome ? oppGoals : ourGoals;

  // Team logo
  const logoEl = document.getElementById("ft-home-logo");
  if (isHome && state.teamInfo.team_logo) {
    logoEl.innerHTML = `<img src="${state.teamInfo.team_logo}" alt="${ourName}" class="ft-logo-img" />`;
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
  const scorers = Object.entries(state.goalCounts).filter(([, n]) => n > 0);
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
  const ourGoals = Object.values(state.goalCounts).reduce((sum, n) => sum + n, 0);
  const isHome = (state.matchData?.match.home_away || "home") === "home";
  document.getElementById("ft-our-score").textContent = isHome ? ourGoals : oppGoals;
  document.getElementById("ft-their-score").textContent = isHome ? oppGoals : ourGoals;
});


document.getElementById("btn-ft-done").addEventListener("click", async () => {
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  if (state.matchData?.match.id) {
    await api.saveGoals(state.matchData.match.id, state.goalCounts, oppGoals).catch(() => {});
  }
  if (state.pitchBackContext === "tournament" && state.activeTournamentId) {
    loadTournamentLobby(state.activeTournamentId);
  } else {
    loadHome();
  }
});

// ── Share result (canvas image) ───────────────────────────────────────────────
function buildResultBlob() {
  const match = state.matchData.match;
  const ourGoals = Object.values(state.goalCounts).reduce((sum, n) => sum + n, 0);
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  const isHome = (match.home_away || "home") === "home";
  const homeTeam = isHome ? (state.teamInfo.team_name || "My Team") : (match.opponent || "Opponent");
  const awayTeam = isHome ? (match.opponent || "Opponent") : (state.teamInfo.team_name || "My Team");
  const homeGoals = isHome ? ourGoals : oppGoals;
  const awayGoals = isHome ? oppGoals : ourGoals;

  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const scorers = Object.entries(state.goalCounts).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);

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
      while (text.length > 1 && ctx.measureText(text + "…").width > maxW) text = text.slice(0, -1);
      return text + "…";
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
    ctx.fillText(`${homeGoals} – ${awayGoals}`, W / 2, 210);

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
  if (state.teamInfo.team_logo) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => draw(img).then(resolve);
      img.onerror = () => draw(null).then(resolve);
      img.src = state.teamInfo.team_logo;
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
  const match = state.matchData.match;
  const isHome = (match.home_away || "home") === "home";
  const home = isHome ? (state.teamInfo.team_name || "My Team") : (match.opponent || "Opponent");
  const away = isHome ? (match.opponent || "Opponent") : (state.teamInfo.team_name || "My Team");
  const ourGoals = Object.values(state.goalCounts).reduce((sum, n) => sum + n, 0);
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  const hg = isHome ? ourGoals : oppGoals;
  const ag = isHome ? oppGoals : ourGoals;
  const file = new File([blob], "result.png", { type: "image/png" });
  const title = `FT: ${home} ${hg}–${ag} ${away}`;
  if (navigator.share && navigator.canShare?.({ files: [file] })) {
    await navigator.share({ files: [file], title }).catch(() => {});
  } else if (navigator.share) {
    await navigator.share({ title, text: `FULL TIME\n${home} ${hg}–${ag} ${away}` }).catch(() => {});
  } else {
    downloadBlob(blob, `FT-${match.date}.png`);
  }
});

document.getElementById("btn-ft-save").addEventListener("click", async () => {
  const blob = await buildResultBlob();
  downloadBlob(blob, `FT-${state.matchData.match.date}.png`);
});

export { enterPitchView, enterManualAssignMode, openMatch, showScreen };

// ── Screen management (leaf helper, kept here to avoid a circular import
// between screens.js/season.js/tournament.js — every module needs it, and it
// has no dependency of its own) ────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => { s.hidden = true; });
  document.getElementById(id).hidden = false;
}
