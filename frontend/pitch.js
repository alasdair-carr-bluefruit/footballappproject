import { api } from "./api.js";
import { state, refreshShirtNumbers, displayPos } from "./state.js";
import { loadHome } from "./season.js";
import { loadTournamentLobby } from "./tournament.js";
import { showToast, withSaveToast } from "./toast.js";
import { BRAND, chalkAlpha, matchdayAlpha } from "./brand.js";

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

function slotCountForPlayer(playerName, md = state.matchData) {
  if (!md) return 0;
  return md.slots.filter(s => Object.values(s.lineup).some(p => p.name === playerName)).length;
}

// ── Plan grid (shared by the full-time report and the "Review the plan" screen)
// A player-row grid: one row per player, a chip per slot showing the position
// they play (or bench "–"), plus a per-player slot total and a skill-total row.
// Parameterised by `md` so the tournament review can stack one grid per match.
function planGridData(md) {
  const totalSlots = md.slots.length;
  const allPlayers = [
    ...Object.values(md.slots[0].lineup),
    ...md.slots[0].bench,
  ];
  // De-dupe by name (a player can appear in both lineup and bench across slots,
  // but slot 0's lineup+bench already covers everyone exactly once).
  const seen = new Set();
  const players = allPlayers.filter(p => (seen.has(p.name) ? false : seen.add(p.name)));
  players.sort((a, b) => a.name.localeCompare(b.name));

  const perSlot = {};
  players.forEach(p => { perSlot[p.name] = Array(totalSlots).fill(null); });
  md.slots.forEach(slot => {
    Object.entries(slot.lineup).forEach(([pos, p]) => {
      if (perSlot[p.name]) perSlot[p.name][slot.slot_index] = normalizePos(pos);
    });
  });

  const pLabel = (md.match.period_label || "Quarter") === "Half" ? "H" : "Q";
  const slotLabels = [];
  for (let i = 0; i < totalSlots; i++) {
    const p = Math.floor(i / 2) + 1;
    slotLabels.push(`${pLabel}${p}${i % 2 === 0 ? "a" : "b"}`);
  }
  return { players, perSlot, slotLabels, totalSlots };
}

// Players significantly under-slotted — flags bug #3. Compared against the FAIR
// SHARE (floor of total on-pitch slots ÷ squad), NOT the busiest player: a
// specialist keeper who plays every slot must not drag every outfielder into a
// false "under-slotted" alarm. The engine guarantees ~floor(total/n)-1 each, so
// anything below that (< fairShare-1) is a genuine shortfall.
function underSlotted(md = state.matchData) {
  const { players } = planGridData(md);
  const n = players.length;
  if (!n) return { items: [], fairShare: 0 };
  const totalPlayerSlots = md.slots.reduce((sum, s) => sum + Object.keys(s.lineup).length, 0);
  const fairShare = Math.floor(totalPlayerSlots / n);
  const counts = players.map(p => ({ name: p.name, count: slotCountForPlayer(p.name, md) }));
  return { items: counts.filter(c => c.count < fairShare - 1), fairShare };
}

// Fills `listEl` (a <ul>) with the per-player grid for `md`. Options:
//   underSlotted: Set<name> — rows to flag with a ⚠ marker
//   markChanges:  bool       — highlight chips where the position changed vs the
//                              previous slot (a sub-in/out or a positional move)
function buildPlanGrid(listEl, md = state.matchData, opts = {}) {
  const { players, perSlot, slotLabels } = planGridData(md);
  const flagged = opts.underSlotted || new Set();

  players.forEach(({ name }) => {
    const slots = perSlot[name];
    const count = slots.filter(Boolean).length;
    const goals = state.goalCounts[name] || 0;

    const chipsHtml = slots.map((pos, i) => {
      const changed = opts.markChanges && i > 0 && pos !== slots[i - 1] ? " chip-changed" : "";
      if (!pos) return `<span class="slot-chip bench${changed}" title="${slotLabels[i]}">–</span>`;
      return `<span class="slot-chip pos-${pos.toLowerCase()}${changed}" title="${slotLabels[i]}: ${displayPos(pos)}">
        <span class="chip-quarter">${slotLabels[i]}</span>
        <span class="chip-pos">${displayPos(pos)}</span>
      </span>`;
    }).join("");

    const goalHtml = goals > 0 ? `<span class="report-goals">⚽ ${goals}</span>` : "";
    const isUnder = flagged.has(name);
    const warnMark = isUnder ? `<span class="report-under-mark" title="Fewer slots than most players">⚠</span>` : "";

    const li = document.createElement("li");
    li.className = "report-row" + (isUnder ? " report-row-under" : "");
    li.innerHTML = `
      <div class="report-name-row">
        <span class="report-name">${warnMark}${name}</span>
        ${goalHtml}
        <span class="report-slots">${count} slot${count !== 1 ? "s" : ""}</span>
      </div>
      <div class="slot-chips">${chipsHtml}</div>
    `;
    listEl.appendChild(li);
  });

  // Skill totals row
  const skillLi = document.createElement("li");
  skillLi.className = "report-row report-row-skill";
  const skillChipsHtml = md.slots.map((slot, i) =>
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
  listEl.appendChild(skillLi);
}

// A player's short token label: the full name if it's ≤4 characters (short
// enough to squeeze into the circle / grid cell), otherwise the first 3
// letters. Shared by the pitch avatars and the position grid.
function abbrevName(name) {
  return (name.length <= 4 ? name : name.slice(0, 3)).toUpperCase();
}

// The compact token shown for a player in the position grid — shirt number if
// set, else the abbreviated name (matches the pitch avatars the coach reads).
function playerToken(name) {
  const num = state.shirtNumbers[name];
  return num != null ? String(num) : abbrevName(name);
}

// Compact POSITION-row grid for the "Review the plan" screen: one row per
// formation position (+GK), a column per slot, each cell the player token who
// fills it. Rows = team size (fixed), so it stays compact no matter how big the
// squad is — unlike the per-player report grid. Plus a per-slot skill row.
// `containerEl` is a block element; we build a CSS grid inside it.
function buildPositionGrid(containerEl, md = state.matchData, opts = {}) {
  const formation = md.match.formation || "1-2-1";
  const positions = ["GK", ...formationPositions(formation)];
  const { slotLabels } = planGridData(md);
  const flagged = opts.underSlotted || new Set();

  const cell = (cls, text, title) => {
    const el = document.createElement("span");
    el.className = cls;
    el.textContent = text;
    if (title) el.title = title;
    return el;
  };

  // Split into stacked grids of at most CHUNK slots (one grid per match-half), so
  // an 8-slot quarters match reads as two 4-column tables (Q1a–Q2b / Q3a–Q4b)
  // instead of one cramped 8-column strip. A 4-slot (halves) match stays single.
  const CHUNK = 4;
  for (let start = 0; start < md.slots.length; start += CHUNK) {
    const end = Math.min(start + CHUNK, md.slots.length);
    const cols = end - start;

    const grid = document.createElement("div");
    grid.className = start === 0 ? "plan-grid" : "plan-grid plan-grid-stacked";
    grid.style.gridTemplateColumns = `minmax(30px, auto) repeat(${cols}, minmax(0, 1fr))`;

    // Header: blank corner + slot labels for this chunk.
    grid.appendChild(cell("plan-corner", ""));
    for (let i = start; i < end; i++) grid.appendChild(cell("plan-cell plan-head", slotLabels[i]));

    // One row per position.
    positions.forEach(posKey => {
      const band = normalizePos(posKey).toLowerCase();
      grid.appendChild(cell(`plan-rowlabel pos-${band}`, displayPos(posKey)));
      for (let i = start; i < end; i++) {
        const p = md.slots[i].lineup[posKey];
        if (!p) { grid.appendChild(cell("plan-cell plan-empty", "·")); continue; }
        // Compare across the full plan (incl. the chunk boundary) so a sub at the
        // start of a chunk still flags as changed.
        const prev = i > 0 ? md.slots[i - 1].lineup[posKey]?.name : p.name;
        const changed = opts.markChanges && i > 0 && prev !== p.name ? " chip-changed" : "";
        const under = flagged.has(p.name) ? " under" : "";
        grid.appendChild(cell(`plan-cell pos-${band}${changed}${under}`, playerToken(p.name), p.name));
      }
    });

    // Skill-total row.
    grid.appendChild(cell("plan-rowlabel plan-skill-label", "⚡"));
    for (let i = start; i < end; i++) grid.appendChild(cell("plan-cell plan-skill", String(md.slots[i].skill_total ?? "?")));

    containerEl.appendChild(grid);
  }
}

// Wrapping "slots per player" strip — preserves the fairness overview the report
// grid gave, but compact (wraps instead of one row each). Under-slotted flagged.
function buildCountsStrip(md, flagged) {
  const { players } = planGridData(md);
  const counts = players
    .map(p => ({ name: p.name, count: slotCountForPlayer(p.name, md) }))
    .sort((a, b) => b.count - a.count);
  const wrap = document.createElement("div");
  wrap.className = "plan-counts";
  wrap.innerHTML = `<span class="plan-counts-title">Slots per player</span>` +
    counts.map(c =>
      `<span class="plan-count-chip${flagged.has(c.name) ? " under" : ""}">${c.name} <b>${c.count}</b></span>`
    ).join("");
  return wrap;
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

// The period (quarter/half) index a slot belongs to — slots pair up 2-per-period.
function periodOf(slotIndex) { return Math.floor(slotIndex / 2); }
// The period actually in play (tied to the running clock), independent of what's viewed.
function livePeriod() { return periodOf(state.liveSlot || 0); }

// Whether a goal can be recorded on the currently-viewed slot. In a live match the
// coach can freely browse past/future slots, but goals only belong to the live
// period; a completed match is edit-on-confirm (see confirmGoalEdit).
function canRecordGoalHere() {
  if (state.editMode || !state.matchStarted) return false;
  if (state.matchData?.match?.status === "completed") return true;
  return periodOf(state.currentSlot) === livePeriod();
}

// A finished match's report is read-only until the coach explicitly opts in.
// Guards both goal-edit paths (long-press to add, tap badge to remove) so goals
// can't be silently changed on a completed match — and, combined with restoring
// goalCounts on open, so an accidental tap can't overwrite the real tally.
function confirmGoalEdit() {
  if (state.matchData?.match?.status !== "completed") return true;
  if (state.reportEditUnlocked) return true;
  if (confirm("This match is finished. Edit the match report?")) {
    state.reportEditUnlocked = true;
    return true;
  }
  return false;
}

// ── Pitch rendering ───────────────────────────────────────────────────────────
function playerCircle(name, role, isIncoming, isOutgoing, isGk = false, onSwapClick = null, dragData = null) {
  const div = document.createElement("div");
  div.className = "player-circle tappable";
  if (isIncoming) div.classList.add("incoming");
  if (isGk) div.classList.add("is-gk");

  const goals = state.goalCounts[name] || 0;
  const shirtNum = state.shirtNumbers[name];
  const avatarContent = shirtNum != null ? String(shirtNum) : abbrevName(name);
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
      if (!canRecordGoalHere() || !confirmGoalEdit()) return;
      state.goalCounts[name] = Math.max(0, (state.goalCounts[name] || 0) - 1);
      render();
    });
    avatar.appendChild(goalBadge);
  }

  let pressTimer = null;
  div.addEventListener("pointerdown", () => {
    if (!canRecordGoalHere()) return; // no goals while adjusting, reviewing, or browsing a non-live period
    pressTimer = setTimeout(() => {
      pressTimer = null;
      if (!confirmGoalEdit()) return;
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
  const showLive = state.matchStarted && state.matchData.match.status !== "completed";
  const liveP = livePeriod();
  dots.forEach((dot, i) => {
    const isFinalDot = i === totalSlotDots;
    dot.classList.toggle("active", !isFinalDot && i === state.currentSlot);
    dot.classList.toggle("done", !isFinalDot && i < state.currentSlot);
    // Ring the dots of the period actually in play, so "where's live" is always visible.
    dot.classList.toggle("live", showLive && !isFinalDot && periodOf(i) === liveP);
    if (isFinalDot) { dot.classList.remove("active", "done", "live"); }
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
      const circle = playerCircle(name || posKey, displayPos(posKey), incoming.has(name), outgoing.has(name), isGk, swapHandler, dragData);
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

  // "◀ Plan" pill: back to the review grid, only while browsing an unstarted
  // plan on the pitch (hidden during tinkering and once the match is live).
  document.getElementById("btn-review-plan").hidden = state.matchStarted || state.editMode;

  // "◀ Full Time" pill: on a finished match the coach browses the slots on the
  // pitch; this returns them to the shareable Full Time card.
  document.getElementById("btn-fulltime-pill").hidden = !isCompleted;

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
    document.getElementById("btn-jump-live").hidden = true;
  } else {
    // Live mode (in_progress or completed)
    startMatchBar.hidden = true;
    // "End early" bar shows on live, non-final slots. On the final slot the Next
    // button itself becomes "End Match", so hide the bar there to avoid two
    // buttons both labelled "End Match".
    endMatchBar.hidden = isCompleted || isLastSlot;
    liveBadge.hidden = isCompleted;
    // "Return to plan review" only while the match hasn't progressed past period 1
    document.getElementById("btn-return-plan").hidden = state.liveSlot !== 0 || isCompleted;
    btnPrev.disabled = state.currentSlot === 0 || state.editMode;
    btnNext.disabled = state.editMode || (isCompleted && isLastSlot);
    btnNext.textContent = isLastSlot ? "End Match" : "Next ▶";

    // Already-played periods are frozen (can't rewrite history); the live period and
    // any future period the coach is previewing stay tinkerable.
    const isPlayedPeriod = periodOf(state.currentSlot) < livePeriod();
    if (isPlayedPeriod || isCompleted) {
      btnAdjust.hidden = true;
    } else {
      btnAdjust.hidden = false;
      btnAdjust.textContent = state.editMode ? "Done" : "Tinker";
    }
    // Offer a jump back to the live period whenever the coach has browsed away.
    const viewingLive = periodOf(state.currentSlot) === livePeriod();
    document.getElementById("btn-jump-live").hidden = isCompleted || viewingLive;
  }

  // When the End Match bar is visible it becomes the bottom-most element, so it
  // (not .controls) carries the safe-area inset — flag the screen for the CSS.
  document.getElementById("screen-pitch").classList.toggle("has-end-bar", !endMatchBar.hidden);

  // "Recalculate rest of match": only while tinkering a plan (not manual-assign,
  // not on the final slot — nothing follows it).
  document.getElementById("btn-recalc-following").hidden =
    !state.editMode || state.manualRotationMode || isLastSlot;

  // Slot-label badges: LIVE (this is the period in play) and LOCKED (coach-edited).
  const slotLabelEl = document.getElementById("slot-label");
  if (state.matchStarted && !isCompleted && periodOf(state.currentSlot) === livePeriod()) {
    slotLabelEl.innerHTML += ' <span class="slot-live-badge">● LIVE</span>';
  }
  if (state.lockedSlots.has(state.currentSlot)) {
    slotLabelEl.innerHTML += ' <span class="slot-locked-badge">LOCKED</span>';
  }

  // "Start next period?" prompt: shown when the coach has browsed to the first slot
  // of the period right after the live one. Starting it advances the live period and
  // resets the clock; "Just browsing" leaves the match where it is. This is the only
  // way the match progresses — plain Next/Prev just move the view.
  const hint = document.getElementById("new-period-hint");
  const viewedPeriod = periodOf(state.currentSlot);
  const atNextLivePeriodStart = state.matchStarted && !isCompleted && !state.showingReport
    && !state.manualRotationMode
    && state.currentSlot % 2 === 0
    && viewedPeriod === livePeriod() + 1;
  if (atNextLivePeriodStart && state.newPeriodHintSlot !== state.currentSlot) {
    const label = state.matchData.match.period_label || "Quarter";
    document.getElementById("new-period-hint-text").textContent =
      `Start ${label} ${viewedPeriod + 1}, or just browsing ahead?`;
    document.getElementById("btn-new-period-reset").textContent = `Start ${label.toLowerCase()}`;
    hint.hidden = false;
  } else {
    hint.hidden = true;
  }
}

// ── Report ────────────────────────────────────────────────────────────────────
function renderReport() {
  document.getElementById("btn-jump-live").hidden = true;
  document.getElementById("btn-review-plan").hidden = true;
  document.getElementById("btn-fulltime-pill").hidden = true;

  const match = state.matchData.match;
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

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

  const list = document.getElementById("report-list");
  list.innerHTML = "";
  buildPlanGrid(list, state.matchData);

  document.getElementById("btn-prev").disabled = false;
  if (state.matchStarted) {
    document.getElementById("btn-next").disabled = false;
    // The final-slot Next already reads "End Match" and brings the coach to this
    // summary; the confirm here finalises and opens Full Time.
    document.getElementById("btn-next").textContent = "Confirm ▶";
  } else {
    document.getElementById("btn-next").disabled = true;
    document.getElementById("btn-next").textContent = "Next ▶";
  }
  document.getElementById("btn-adjust").hidden = true;
  document.getElementById("btn-recalc-following").hidden = true;
  // End Match bar: hidden on the report. The report's own "End Match" (btn-next)
  // is the primary end action here; the bar's button is the live-pitch "end early"
  // affordance and would otherwise show a second, redundant End Match button.
  const endBar = document.getElementById("end-match-bar");
  if (endBar) endBar.hidden = true;
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

// Load a match's plan into `state` (shared by the pitch view and the review
// screen). Returns the match status so callers can drive the timer/screen.
function loadMatchData(data) {
  state.matchData = data;
  state.showingReport = false;
  state.showingChanges = false;
  if (!state.manualRotationMode) state.editMode = false;
  state.manualRotationMode = data.manual_mode || false;
  state.lockedSlots = new Set(data.locked_slots || []);
  state.removedPlayers = data.removed_players || {};
  // Restore stored goals (empty for a planned match). Without this a reopened
  // match shows no scorers and a later save would wipe the real tally.
  Object.keys(state.goalCounts).forEach(k => delete state.goalCounts[k]);
  Object.assign(state.goalCounts, data.goals || {});
  state.reportEditUnlocked = false;
  // FA sub-U12 scoreline masking — persisted per match, drives the Full Time card
  // + share image (see showFulltime / buildResultBlob).
  state.hideScore = !!(data.match?.hide_score);

  // Determine match state
  const status = data.match?.status || "planned";
  state.matchStarted = status !== "planned";
  // liveSlot = the period in play (persisted as current_slot); currentSlot is the
  // viewed slot, which starts on the live one but is then free to browse. A
  // completed match has no live period, so browsing starts from the first slot
  // (not wherever current_slot was frozen at End Match) so Prev/Next always walk
  // the whole match reliably.
  state.liveSlot = data.match?.current_slot || 0;
  state.currentSlot = (state.matchStarted && status !== "completed") ? state.liveSlot : 0;
  return status;
}

function enterPitchView(data) {
  const status = loadMatchData(data);

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

// ── "Review the plan" screen ──────────────────────────────────────────────────
// The landing after generating a plan (season + single tournament match): a
// per-player rotation grid, an under-slotted-player warning, and Tinker / Start /
// Back actions. Read-only — editing happens on the pitch ("Tinker") and persists
// via /adjust, then "◀ Plan" returns here with fresh counts.
function enterReviewView(data) {
  loadMatchData(data);
  stopTimerTicker();
  state.reviewMode = "single";
  showScreen("screen-review");
  renderReview();
}

// Landing for a reopened FINISHED match: the Full Time result card. loadMatchData
// restores the stored goals + hide_score flag; showFulltime renders the scoreline,
// scorers and share/export actions. "View on pitch" then browses the slots.
function enterFulltimeView(data) {
  loadMatchData(data);
  stopTimerTicker();
  showFulltime();
}

function renderReview() {
  const match = state.matchData.match;
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  document.getElementById("review-title").textContent = `${dateStr} · vs ${match.opponent || "Unknown"}`;
  document.getElementById("review-actions-single").hidden = false;

  const grid = document.getElementById("review-grid");
  grid.innerHTML = "";
  const under = underSlotted(state.matchData);
  const flagged = new Set(under.items.map(i => i.name));
  buildPositionGrid(grid, state.matchData, { markChanges: true, underSlotted: flagged });
  grid.appendChild(buildCountsStrip(state.matchData, flagged));

  const warn = document.getElementById("review-warning");
  if (under.items.length) {
    warn.innerHTML = `<span class="review-warning-head">⚠ Uneven playing time</span>` +
      under.items.map(i =>
        `<span class="review-warning-item">${i.name}: ${i.count} slot${i.count !== 1 ? "s" : ""} (below the ~${under.fairShare} fair share)</span>`
      ).join("");
    warn.hidden = false;
  } else {
    warn.hidden = true;
  }
}

// Builds one match's review card (header + optional warning + grid + Open button)
// for the combined tournament review page.
function buildReviewCard(md, { title, onOpen }) {
  const card = document.createElement("div");
  card.className = "review-card";
  const under = underSlotted(md);
  const warnHtml = under.items.length
    ? `<div class="review-warning review-warning-card"><span class="review-warning-head">⚠ Uneven time</span>` +
      under.items.map(i => `<span class="review-warning-item">${i.name}: ${i.count}</span>`).join("") + `</div>`
    : "";
  card.innerHTML = `
    <div class="review-card-head">
      <span class="review-card-title">${title}</span>
      <button class="btn btn-sm btn-secondary review-open-btn" type="button">Open ▶</button>
    </div>
    ${warnHtml}
    <div class="review-card-grid"></div>
  `;
  buildPositionGrid(card.querySelector(".review-card-grid"), md,
    { markChanges: true, underSlotted: new Set(under.items.map(i => i.name)) });
  card.querySelector(".review-open-btn").addEventListener("click", onOpen);
  return card;
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

  let data = await api.getMatch(matchId).catch(err => { alert(err.message); return null; });
  if (!data) return;

  if (!data.slots || data.slots.length === 0) {
    data = await api.generateRotation(matchId).catch(err => {
      alert("Could not generate rotation: " + err.message);
      return null;
    });
    if (!data) return;
  }

  // A not-yet-started plan lands on the review screen; an in-progress match goes
  // to the live pitch; a finished match lands on its Full Time result card (the
  // shareable summary — coaches reopen finished matches mainly to share the
  // result), with "View on pitch" to browse the slots.
  const status = data.match?.status || "planned";
  if (status === "planned") {
    enterReviewView(data);
  } else if (status === "completed") {
    enterFulltimeView(data);
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

// ── Review-screen controls ────────────────────────────────────────────────────
// View on pitch: open the pitch on the current (unstarted) plan in BROWSE mode
// (edit off) so Prev/Next flick through the slots. The pitch's own "Tinker"
// button toggles editing (persists via /adjust); "◀ Plan" returns here.
document.getElementById("btn-review-view").addEventListener("click", () => {
  enterPitchView(state.matchData);
});

document.getElementById("btn-review-start").addEventListener("click", () => {
  enterPitchView(state.matchData);
  doStartMatch();
});

document.getElementById("btn-review-back").addEventListener("click", () => {
  if (state.reviewMode === "tournament-all" ||
      (state.pitchBackContext === "tournament" && state.activeTournamentId)) {
    loadTournamentLobby(state.activeTournamentId);
  } else {
    loadHome();
  }
});

// "◀ Plan" pill on the pitch — jump back to the review grid (pre-start only).
document.getElementById("btn-review-plan").addEventListener("click", () => {
  enterReviewView(state.matchData);
});

// "◀ Full Time" pill on the pitch — back to the finished match's result card.
document.getElementById("btn-fulltime-pill").addEventListener("click", () => {
  showFulltime();
});

// ── Pitch controls ────────────────────────────────────────────────────────────
document.getElementById("btn-start-match-cta").addEventListener("click", () => doStartMatch());

document.getElementById("btn-next").addEventListener("click", async () => {
  if (state.showingReport) {
    if (state.matchStarted) doEndMatch();
    return;
  }
  if (state.currentSlot < state.matchData.slots.length - 1) {
    const prevSlotObj = state.matchData.slots[state.currentSlot];
    state.currentSlot++;
    // Next only MOVES THE VIEW in a live match — the match progresses via the
    // "Start period" prompt, so browsing ahead never commits or locks anything.
    // Let the prompt re-appear when landing on the next-period boundary again.
    state.newPeriodHintSlot = null;

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

    render();
  } else {
    // Last slot — show match report
    state.showingReport = true;
    renderReport();
  }
});

document.getElementById("btn-prev").addEventListener("click", () => {
  if (state.showingReport) { showMatch(); return; }
  if (state.currentSlot > 0) {
    state.currentSlot--;
    state.newPeriodHintSlot = null;
    render();
  }
});

// Jump the view straight back to the live slot after browsing away.
document.getElementById("btn-jump-live").addEventListener("click", () => {
  state.currentSlot = state.liveSlot;
  state.newPeriodHintSlot = null;
  state.showingReport = false;
  state.showingChanges = false;
  showMatch();
});

// ── End match ─────────────────────────────────────────────────────────────────
document.getElementById("btn-end-match").addEventListener("click", () => {
  const lastPeriod = periodOf(state.matchData.slots.length - 1);
  // No confirmation only when the match has genuinely reached its final period;
  // browsing to the report early (live period still behind) still needs confirming.
  if (livePeriod() >= lastPeriod) {
    doEndMatch();
  } else {
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
    await withSaveToast(() => api.saveGoals(state.matchData.match.id, state.goalCounts, oppGoals, state.hideScore));
    await withSaveToast(() => api.updateProgress(state.matchData.match.id, state.currentSlot, "completed"));
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

// The coach can hide the match clock per match via the create-match "show timer"
// toggle (show_timer === 0). Undefined/legacy plans default to shown.
function timerEnabled() {
  return state.matchData?.match?.show_timer !== 0;
}

// Called from Start Match — begins a fresh clock for this match
function beginMatchTimer() {
  if (!timerEnabled()) return;
  writeTimer({ startedAt: Date.now(), pausedAt: null, pausedAccumMs: 0 });
  startTimerTicker();
}

// Called on re-entering a live match — resume the existing clock (or start one
// if none is stored, e.g. it was cleared)
function resumeMatchTimer() {
  if (!timerEnabled()) return;
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
  if (!timerEnabled() || !state.matchStarted || state.showingReport || !timerState) {
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
  // Commit: the viewed period becomes the live one. Advance liveSlot, persist it
  // (this is the only progress write now), and reset the clock for the new period.
  state.liveSlot = state.currentSlot;
  state.matchData.match.current_slot = state.currentSlot;
  withSaveToast(() => api.updateProgress(state.matchData.match.id, state.currentSlot));
  resetMatchTimer();
  state.newPeriodHintSlot = state.currentSlot;
  document.getElementById("new-period-hint").hidden = true;
  render();
});

document.getElementById("btn-new-period-dismiss").addEventListener("click", () => {
  // Just browsing — leave the live period where it is, only suppress the prompt here.
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
    state.liveSlot = 0;             // first period is live
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
    state.liveSlot = 0;
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
    statusEl.textContent = "Regenerating plan…";
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
    statusEl.textContent = "Regenerating plan…";
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
  const finishing = state.editMode; // was tinkering; this click finishes
  state.editMode = !state.editMode;
  const btn = document.getElementById("btn-adjust");
  btn.textContent = state.editMode ? "Done" : "Tinker";
  render();
  if (finishing) showToast("Sorted. Plan updated.");
});

// Explicit, following-only recalculation. Local edits never touch other slots;
// this deliberately reflows every slot AFTER the one being viewed, keeping the
// current slot and everything before it exactly as the coach left them.
document.getElementById("btn-recalc-following").addEventListener("click", async () => {
  if (!state.matchData) return;
  const pivot = state.currentSlot;
  if (pivot >= state.matchData.slots.length - 1) {
    showToast("No later slots to recalculate.");
    return;
  }
  const label = (state.matchData.match.period_label || "Quarter").toLowerCase();
  if (!confirm(`Recalculate every slot after this one? The current ${label} and everything before it stay as they are.`)) return;

  // Lock the viewed slot + all earlier slots; leave later ones unlocked so the
  // engine regenerates ONLY the following slots.
  const locked = state.matchData.slots
    .map(s => s.slot_index)
    .filter(i => i <= pivot);

  const statusEl = document.getElementById("adjust-status");
  statusEl.textContent = "Regenerating following slots…";
  statusEl.hidden = false;
  try {
    const result = await api.adjustRotation(state.matchData.match.id, {}, locked);
    statusEl.hidden = true;
    // Slots after the pivot were regenerated, so any coach edits there are gone —
    // drop them from the edited set; edits at/before the pivot are preserved.
    state.lockedSlots = new Set([...state.lockedSlots].filter(i => i <= pivot));
    applyAdjustResult(result);
    warnIfUnderSlotted();
  } catch (err) {
    statusEl.hidden = true;
    alert("Could not recalculate: " + err.message);
  }
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
      li.innerHTML = `<span class="swap-name">${p.name}</span><span class="swap-pos">${displayPos(pos)} · ${count} slot${count !== 1 ? "s" : ""}</span>`;
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
  statusEl.textContent = "Saving edit…";
  statusEl.hidden = false;

  // A tinker edit is a purely LOCAL swap: lock every slot so the engine never
  // rewrites slots the coach didn't touch. To reflow later slots deliberately,
  // the coach uses the explicit "Recalculate rest of match" button.
  const slotsToLock = state.matchData.slots.map(s => s.slot_index);

  try {
    const result = await api.adjustRotation(
      state.matchData.match.id, edits, slotsToLock,
    );

    statusEl.hidden = true;
    state.lockedSlots.add(slotIndex);  // mark this slot as coach-edited (LOCKED badge)
    applyAdjustResult(result);
    warnIfUnderSlotted();
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

// Non-blocking: after a local tinker edit or a recalculate, flag any player now
// below fair share (bug #3 heuristic). The edit already applied — this only warns.
function warnIfUnderSlotted() {
  const under = underSlotted();
  if (under.items.length === 0) return;
  const names = under.items.map(i => i.name).join(", ");
  showToast(`⚠ Uneven playing time: ${names}`, { duration: 5000 });
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
  // NB: `state.lockedSlots` tracks *coach-edited* slots (drives the LOCKED badge),
  // NOT the transport lock set we send to the API. Since every tinker edit now
  // locks all slots on the wire, result.locked_slots is always "all" and must not
  // be copied here — callers maintain lockedSlots explicitly.
  render();
}

// Save goals when leaving pitch view via back button (no opponent goals known yet)
async function saveGoalsIfNeeded() {
  if (!state.matchData || !state.matchData.match.id) return;
  const hasGoals = Object.values(state.goalCounts).some(v => v > 0);
  if (hasGoals) {
    await withSaveToast(() => api.saveGoals(state.matchData.match.id, state.goalCounts, state.matchData.match.opponent_goals || 0));
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
// Paint the Full Time scoreline from the current goal tallies, honouring the
// FA "hide score" toggle: when on, both numbers show "X" (→ "X – X") and an
// explanatory caption appears; the scorer list is unaffected. Reads opponent
// goals live from the input so it stays in sync as the coach edits.
function renderFulltimeScoreline() {
  const ourGoals = Object.values(state.goalCounts).reduce((sum, n) => sum + n, 0);
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  const isHome = (state.matchData?.match.home_away || "home") === "home";
  const hidden = !!state.hideScore;
  document.getElementById("ft-our-score").textContent = hidden ? "X" : (isHome ? ourGoals : oppGoals);
  document.getElementById("ft-their-score").textContent = hidden ? "X" : (isHome ? oppGoals : ourGoals);
  document.getElementById("ft-hidden-note").hidden = !hidden;
}

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
  document.getElementById("ft-opp-input").value = oppGoals;
  document.getElementById("ft-hide-score").checked = !!state.hideScore;
  renderFulltimeScoreline();

  // Team logo — our badge sits next to our team's name, whichever side we're on
  // (home block when home, away block when away). The opponent side shows initials.
  const homeTeam = isHome ? ourName : oppName;
  const awayTeam = isHome ? oppName : ourName;
  const setLogo = (el, ourSide, teamName) => {
    if (ourSide && state.teamInfo.team_logo) {
      el.innerHTML = `<img src="${state.teamInfo.team_logo}" alt="${ourName}" class="ft-logo-img" />`;
    } else {
      el.innerHTML = "";
      el.textContent = teamName.slice(0, 2).toUpperCase();
    }
  };
  setLogo(document.getElementById("ft-home-logo"), isHome, homeTeam);
  setLogo(document.getElementById("ft-away-logo"), !isHome, awayTeam);

  // Date + venue
  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const venue = isHome ? "Home" : "Away";
  document.getElementById("ft-meta").textContent = `${dateStr}  ·  ${venue}`;

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
document.getElementById("ft-opp-input").addEventListener("input", () => {
  renderFulltimeScoreline();
});

// "Hide score" toggle — FA guidance disallows publishing scores for U11 and
// below. Masks the scoreline (scorers stay) and persists per match so reopening
// to share keeps it hidden.
document.getElementById("ft-hide-score").addEventListener("change", async e => {
  state.hideScore = e.target.checked;
  renderFulltimeScoreline();
  if (state.matchData?.match.id) {
    state.matchData.match.hide_score = state.hideScore ? 1 : 0;
    const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
    await withSaveToast(() => api.saveGoals(state.matchData.match.id, state.goalCounts, oppGoals, state.hideScore));
  }
});

document.getElementById("btn-ft-pitch").addEventListener("click", () => {
  // Browse the finished match's slots on the pitch; the "◀ Full Time" pill returns.
  enterPitchView(state.matchData);
});

document.getElementById("btn-ft-done").addEventListener("click", async () => {
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  if (state.matchData?.match.id) {
    await withSaveToast(() => api.saveGoals(state.matchData.match.id, state.goalCounts, oppGoals, state.hideScore));
  }
  if (state.pitchBackContext === "tournament" && state.activeTournamentId) {
    loadTournamentLobby(state.activeTournamentId);
  } else {
    loadHome();
  }
});

// ── Share result (canvas image) ───────────────────────────────────────────────
// Renders a shareable PNG that mirrors the on-screen Full Time card (same dark
// gradient, Signal-Lime "Full Time" badge + scorer pills, Space Mono scoreline,
// our badge on our side). Fonts are the page's already-loaded web fonts, so no
// network fetch happens at share time.
const _FONT_BODY = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
const _FONT_MONO = "'Space Mono', ui-monospace, SFMono-Regular, Menlo, monospace";

function _loadLogo(src) {
  if (!src) return Promise.resolve(null);
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

function _roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(x, y, w, h, rr); return; }
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

async function buildResultBlob() {
  // Ensure the web fonts (Space Mono / Inter) are ready so canvas text matches
  // the Full Time card rather than falling back to a system font.
  if (document.fonts?.ready) { try { await document.fonts.ready; } catch (_) { /* draw anyway */ } }

  const match = state.matchData.match;
  const ourGoals = Object.values(state.goalCounts).reduce((sum, n) => sum + n, 0);
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  const isHome = (match.home_away || "home") === "home";
  const ourName = state.teamInfo.team_name || "My Team";
  const oppName = match.opponent || "Opponent";
  const homeTeam = isHome ? ourName : oppName;
  const awayTeam = isHome ? oppName : ourName;
  const homeGoals = isHome ? ourGoals : oppGoals;
  const awayGoals = isHome ? oppGoals : ourGoals;

  const date = new Date(match.date + "T12:00:00");
  const dateStr = date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const venue = isHome ? "Home" : "Away";
  const scorers = Object.entries(state.goalCounts).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);

  const logoImg = await _loadLogo(state.teamInfo.team_logo);

  // Layout (logical px, 1:1 with the .ft-card CSS; canvas drawn at 2× for HiDPI).
  const SCALE = 2;
  const W = 540;
  const margin = 24;                 // backdrop around the card
  const padX = 22, padTop = 28, padBottom = 24;
  const cardX = margin, cardW = W - margin * 2;
  const contentX = cardX + padX, contentW = cardW - padX * 2;
  const centerX = W / 2;

  // Measure the scorer pills up front (needs a ctx) so we can size the canvas.
  const meas = document.createElement("canvas").getContext("2d");
  meas.font = "600 13px " + _FONT_BODY;
  const pillH = 26, pillGapX = 6, pillGapY = 8, pillPadX = 12;
  const pillItems = scorers.map(([name, n]) => {
    const label = n > 1 ? `${name} ×${n}` : name;
    return { label, w: Math.min(meas.measureText(label).width + pillPadX * 2, contentW) };
  });
  const pillRows = [];
  let row = [], rowW = 0;
  for (const it of pillItems) {
    const add = (row.length ? pillGapX : 0) + it.w;
    if (row.length && rowW + add > contentW) { pillRows.push({ items: row, w: rowW }); row = []; rowW = 0; }
    row.push(it); rowW += (row.length > 1 ? pillGapX : 0) + it.w;
  }
  if (row.length) pillRows.push({ items: row, w: rowW });
  const pillsH = pillRows.length ? pillRows.length * pillH + (pillRows.length - 1) * pillGapY : 0;

  // Section heights and total card height.
  const badgeH = 22, teamsH = 76, metaH = 18, titleH = 16;
  const scorersBlock = scorers.length ? 16 + titleH + 10 + pillsH : 0;
  const cardH = padTop + badgeH + 16 + teamsH + 14 + metaH + scorersBlock + padBottom;
  const H = cardH + margin * 2;

  const canvas = document.createElement("canvas");
  canvas.width = W * SCALE;
  canvas.height = H * SCALE;
  const ctx = canvas.getContext("2d");
  ctx.scale(SCALE, SCALE);

  // Backdrop (page bg) + card (gradient, rounded, soft shadow).
  ctx.fillStyle = BRAND.pitchDeep;
  ctx.fillRect(0, 0, W, H);
  const grad = ctx.createLinearGradient(cardX, margin, cardX + cardW, margin + cardH);
  grad.addColorStop(0, BRAND.pitchDeep);
  grad.addColorStop(1, BRAND.pitch);
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.4)";
  ctx.shadowBlur = 32;
  ctx.shadowOffsetY = 8;
  ctx.fillStyle = grad;
  _roundRect(ctx, cardX, margin, cardW, cardH, 18);
  ctx.fill();
  ctx.restore();

  const trunc = (text, font, maxW) => {
    ctx.font = font;
    if (ctx.measureText(text).width <= maxW) return text;
    while (text.length > 1 && ctx.measureText(text + "…").width > maxW) text = text.slice(0, -1);
    return text + "…";
  };

  let y = margin + padTop;

  // "FULL TIME" badge — Signal-Lime text on a translucent lime pill.
  ctx.font = "700 11px " + _FONT_BODY;
  if ("letterSpacing" in ctx) ctx.letterSpacing = "1.3px";
  const badgeLabel = "FULL TIME";
  const badgeTW = ctx.measureText(badgeLabel).width;
  const badgeW = badgeTW + 24, badgeYH = 22;
  ctx.fillStyle = matchdayAlpha(0.15);
  _roundRect(ctx, centerX - badgeW / 2, y, badgeW, badgeYH, 11);
  ctx.fill();
  ctx.fillStyle = BRAND.matchday;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(badgeLabel, centerX, y + badgeYH / 2 + 0.5);
  if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
  y += badgeH + 16;

  // Teams row: [logo+name] [score] [logo+name], vertically centred.
  const rowTop = y;
  const logoR = 24;
  const logoCY = rowTop + logoR;
  const nameCY = rowTop + logoR * 2 + 8 + 8;
  const scoreCY = rowTop + teamsH / 2 - 6;
  const sideW = contentW * 0.34;
  const leftCX = contentX + sideW / 2;
  const rightCX = contentX + contentW - sideW / 2;

  const drawTeam = (cx, ourSide, teamName) => {
    if (ourSide && logoImg) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, logoCY, logoR, 0, Math.PI * 2);
      ctx.clip();
      ctx.drawImage(logoImg, cx - logoR, logoCY - logoR, logoR * 2, logoR * 2);
      ctx.restore();
    } else {
      ctx.fillStyle = "rgba(255,255,255,0.1)";
      ctx.beginPath();
      ctx.arc(cx, logoCY, logoR, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = BRAND.chalk;
      ctx.font = "700 13px " + _FONT_BODY;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(teamName.slice(0, 2).toUpperCase(), cx, logoCY);
    }
    ctx.fillStyle = BRAND.chalk;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(trunc(teamName, "600 13px " + _FONT_BODY, sideW), cx, nameCY);
  };

  drawTeam(leftCX, isHome, homeTeam);
  drawTeam(rightCX, !isHome, awayTeam);

  // Scoreline — Space Mono, big numbers + a lighter separator. When the FA "hide
  // score" flag is set the numbers mask to "X" (→ "X – X"); scorers still print.
  const hideScore = !!state.hideScore;
  const homeStr = hideScore ? "X" : String(homeGoals);
  const awayStr = hideScore ? "X" : String(awayGoals);
  const numFont = "700 46px " + _FONT_MONO;
  const sepFont = "400 34px " + _FONT_MONO;
  ctx.font = numFont;
  const hw = ctx.measureText(homeStr).width;
  const aw = ctx.measureText(awayStr).width;
  ctx.font = sepFont;
  const sw = ctx.measureText("–").width;
  const g = 10;
  let sx = centerX - (hw + g + sw + g + aw) / 2;
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.font = numFont; ctx.fillStyle = BRAND.chalk; ctx.fillText(homeStr, sx, scoreCY); sx += hw + g;
  ctx.font = sepFont; ctx.fillStyle = chalkAlpha(0.4); ctx.fillText("–", sx, scoreCY); sx += sw + g;
  ctx.font = numFont; ctx.fillStyle = BRAND.chalk; ctx.fillText(awayStr, sx, scoreCY);

  y = rowTop + teamsH + 14;

  // Meta — date · venue (+ FA note when the score is masked).
  ctx.font = "400 12px " + _FONT_BODY;
  ctx.fillStyle = chalkAlpha(0.55);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const metaText = hideScore ? `${dateStr}  ·  ${venue}  ·  Score hidden (FA guidelines)` : `${dateStr}  ·  ${venue}`;
  ctx.fillText(metaText, centerX, y + metaH / 2);
  y += metaH;

  // Scorers — dim title + Signal-Lime pills, wrapped and centred.
  if (scorers.length) {
    y += 16;
    ctx.font = "600 12px " + _FONT_BODY;
    ctx.fillStyle = chalkAlpha(0.55);
    if ("letterSpacing" in ctx) ctx.letterSpacing = "0.6px";
    ctx.fillText("⚽ GOAL SCORERS", centerX, y + titleH / 2);
    if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
    y += titleH + 10;

    ctx.font = "600 13px " + _FONT_BODY;
    for (const r of pillRows) {
      let px = centerX - r.w / 2;
      for (const it of r.items) {
        ctx.fillStyle = matchdayAlpha(0.15);
        _roundRect(ctx, px, y, it.w, pillH, pillH / 2);
        ctx.fill();
        ctx.fillStyle = BRAND.matchday;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(it.label, px + it.w / 2, y + pillH / 2 + 0.5);
        px += it.w + pillGapX;
      }
      y += pillH + pillGapY;
    }
  }

  return new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
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
  if (!blob) { showToast("Couldn't build the result image."); return; }
  const match = state.matchData.match;
  const isHome = (match.home_away || "home") === "home";
  const home = isHome ? (state.teamInfo.team_name || "My Team") : (match.opponent || "Opponent");
  const away = isHome ? (match.opponent || "Opponent") : (state.teamInfo.team_name || "My Team");
  const ourGoals = Object.values(state.goalCounts).reduce((sum, n) => sum + n, 0);
  const oppGoals = parseInt(document.getElementById("ft-opp-input").value) || 0;
  const hg = isHome ? ourGoals : oppGoals;
  const ag = isHome ? oppGoals : ourGoals;
  const filename = `FT-${match.date}.png`;
  const file = new File([blob], filename, { type: "image/png" });
  const title = `FT: ${home} ${hg}–${ag} ${away}`;
  // Prefer the native share sheet WITH the image. If files can't be shared
  // (most desktop browsers), fall back to a download so the image is always
  // delivered — the old text-only share path silently dropped the picture.
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title });
    } catch (e) {
      if (e.name !== "AbortError") downloadBlob(blob, filename);
    }
  } else {
    downloadBlob(blob, filename);
  }
});

document.getElementById("btn-ft-save").addEventListener("click", async () => {
  const blob = await buildResultBlob();
  if (!blob) { showToast("Couldn't build the result image."); return; }
  downloadBlob(blob, `FT-${state.matchData.match.date}.png`);
});

export { enterPitchView, enterManualAssignMode, openMatch, showScreen, enterReviewView, buildReviewCard, underSlotted };

// ── Screen management (leaf helper, kept here to avoid a circular import
// between screens.js/season.js/tournament.js — every module needs it, and it
// has no dependency of its own) ────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => { s.hidden = true; });
  document.getElementById(id).hidden = false;
}
