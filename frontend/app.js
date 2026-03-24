import { MATCH, SLOTS, PLAYERS } from "./data.js";

// ── State ────────────────────────────────────────────────────────────────────

let currentSlot = 0;
let showingReport = false;
const goalCounts = {}; // { playerName: count }

// ── Helpers ──────────────────────────────────────────────────────────────────

function quarterLabel(slotIndex) {
  const q = Math.floor(slotIndex / 2) + 1;
  const h = slotIndex % 2 === 0 ? "a" : "b";
  return { q, h, label: `Q${q}${h}` };
}

function slotPlayers(slot) {
  return new Set([slot.gk, slot.def, slot.mid1, slot.mid2, slot.fwd]);
}

// Players coming ON in nextSlot that were not in currentSlotData
function incomingSubs(currentSlotData, nextSlotData) {
  if (!nextSlotData) return new Set();
  const current = slotPlayers(currentSlotData);
  return new Set([
    nextSlotData.gk, nextSlotData.def, nextSlotData.mid1,
    nextSlotData.mid2, nextSlotData.fwd,
  ].filter(p => !current.has(p)));
}

// Players going OFF (in current, not in next)
function outgoingSubs(currentSlotData, nextSlotData) {
  if (!nextSlotData) return new Set();
  const next = slotPlayers(nextSlotData);
  return new Set([
    currentSlotData.gk, currentSlotData.def, currentSlotData.mid1,
    currentSlotData.mid2, currentSlotData.fwd,
  ].filter(p => !next.has(p)));
}

// ── Render ───────────────────────────────────────────────────────────────────

function playerCircle(name, role, isIncoming, isOutgoing, isGk = false) {
  const div = document.createElement("div");
  div.className = "player-circle tappable";
  if (isIncoming) div.classList.add("incoming");
  if (isOutgoing) div.classList.add("outgoing");
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
    // Tap the badge to undo a goal
    goalBadge.addEventListener("click", (e) => {
      e.stopPropagation();
      goalCounts[name] = Math.max(0, (goalCounts[name] || 0) - 1);
      render();
    });
    avatar.appendChild(goalBadge);
  }

  // Long press to record a goal
  let pressTimer = null;
  div.addEventListener("pointerdown", () => {
    pressTimer = setTimeout(() => {
      pressTimer = null;
      goalCounts[name] = (goalCounts[name] || 0) + 1;
      div.classList.add("goal-scored");
      setTimeout(() => div.classList.remove("goal-scored"), 600);
      // Vibrate if supported
      if (navigator.vibrate) navigator.vibrate(80);
      render();
    }, 600);
  });
  div.addEventListener("pointerup",    () => clearTimeout(pressTimer));
  div.addEventListener("pointerleave", () => clearTimeout(pressTimer));

  return div;
}

function render() {
  const slot = SLOTS[currentSlot];
  const nextSlot = SLOTS[currentSlot + 1] || null;
  const { q, h, label, half } = quarterLabel(currentSlot);

  const incoming = incomingSubs(slot, nextSlot);
  const outgoing = outgoingSubs(slot, nextSlot);

  // Header
  document.getElementById("match-title").textContent =
    `${MATCH.date}  ·  vs ${MATCH.opponent}`;
  document.getElementById("slot-label").textContent = label;
  document.getElementById("slot-counter").textContent =
    `Slot ${currentSlot + 1} of ${SLOTS.length}`;

  // Progress dots
  const dots = document.querySelectorAll(".progress-dot");
  dots.forEach((dot, i) => {
    dot.classList.toggle("active", i === currentSlot);
    dot.classList.toggle("done", i < currentSlot);
  });


  // Build map: incoming player → who they replace
  // Match by position order between current and next outfield
  const replacementMap = new Map(); // incoming name → outgoing name
  if (nextSlot) {
    const positions = ["def", "mid1", "mid2", "fwd"];
    positions.forEach(pos => {
      const cur = slot[pos];
      const nxt = nextSlot[pos];
      if (nxt !== cur && incoming.has(nxt)) {
        replacementMap.set(nxt, cur);
      }
    });
    // GK replacement
    if (nextSlot.gk !== slot.gk && incoming.has(nextSlot.gk)) {
      replacementMap.set(nextSlot.gk, slot.gk);
    }
  }

  // Pitch
  const pitch = document.getElementById("pitch");
  pitch.innerHTML = "";

  const rows = [
    { key: "fwd",  label: "FWD",  name: slot.fwd  },
    { key: "mid",  label: "MID",  mid1: slot.mid1, mid2: slot.mid2 },
    { key: "def",  label: "DEF",  name: slot.def  },
    { key: "gk",   label: "GK",   name: slot.gk   },
  ];

  rows.forEach(row => {
    const rowEl = document.createElement("div");
    rowEl.className = "pitch-row";

    if (row.key === "mid") {
      rowEl.classList.add("mid-row");
      rowEl.appendChild(playerCircle(row.mid1, "MID", incoming.has(row.mid1), false));
      rowEl.appendChild(playerCircle(row.mid2, "MID", incoming.has(row.mid2), false));
    } else {
      const isGk = row.key === "gk";
      rowEl.appendChild(playerCircle(row.name, row.label, incoming.has(row.name), false, isGk));
    }

    pitch.appendChild(rowEl);
  });

  // Bench
  const bench = document.getElementById("bench-list");
  bench.innerHTML = "";
  slot.bench.forEach(name => {
    const li = document.createElement("li");
    li.className = "bench-player";
    if (incoming.has(name)) li.classList.add("incoming");

    const initials = name.slice(0, 3).toUpperCase();
    const replacingName = replacementMap.get(name);
    const subLabel = replacingName
      ? `<span class="bench-arrow">↑ On for ${replacingName}</span>`
      : "";

    li.innerHTML = `
      <span class="bench-avatar">${initials}</span>
      <span class="bench-name">${name}</span>
      ${subLabel}
    `;
    bench.appendChild(li);
  });

  // Button states
  document.getElementById("btn-prev").disabled = currentSlot === 0;

  const btnNext = document.getElementById("btn-next");
  if (currentSlot === SLOTS.length - 1) {
    btnNext.textContent = "Full time ▶";
    btnNext.disabled = false;
  } else if (currentSlot % 2 === 0 && currentSlot < SLOTS.length - 1) {
    btnNext.textContent = "Next half ▶";
  } else {
    btnNext.textContent = "Next quarter ▶";
  }
}

// ── Report ───────────────────────────────────────────────────────────────────

function computeReport() {
  // perSlot[name] = array of 8 entries: position string or null (bench)
  const perSlot = {};
  Object.keys(PLAYERS).forEach(name => { perSlot[name] = Array(8).fill(null); });

  SLOTS.forEach((slot, i) => {
    [
      { name: slot.gk,   pos: "GK"  },
      { name: slot.def,  pos: "DEF" },
      { name: slot.mid1, pos: "MID" },
      { name: slot.mid2, pos: "MID" },
      { name: slot.fwd,  pos: "FWD" },
    ].forEach(({ name, pos }) => {
      perSlot[name][i] = pos;
    });
  });

  const slotCounts = {};
  Object.keys(PLAYERS).forEach(name => {
    slotCounts[name] = perSlot[name].filter(p => p !== null).length;
  });

  return { slotCounts, perSlot };
}

function renderReport() {
  const { slotCounts, perSlot } = computeReport();

  document.getElementById("slot-label").textContent = "Full Time";
  document.getElementById("slot-counter").textContent = "Match report";
  document.getElementById("match-title").textContent =
    `${MATCH.date}  ·  vs ${MATCH.opponent}`;

  document.querySelector(".pitch-wrapper").style.display = "none";
  document.querySelector(".bench-section").style.display = "none";
  document.getElementById("report-section").style.display = "block";
  document.querySelector(".progress-dots").style.display = "none";

  const slotLabels = ["Q1a","Q1b","Q2a","Q2b","Q3a","Q3b","Q4a","Q4b"];

  const list = document.getElementById("report-list");
  list.innerHTML = "";

  Object.keys(PLAYERS).forEach(name => {
    const count = slotCounts[name] || 0;
    const slots = perSlot[name];

    const chipsHtml = slots.map((pos, i) => {
      if (!pos) return `<span class="slot-chip bench" title="${slotLabels[i]}">–</span>`;
      return `<span class="slot-chip pos-${pos.toLowerCase()}" title="${slotLabels[i]}: ${pos}">
        <span class="chip-quarter">${slotLabels[i]}</span>
        <span class="chip-pos">${pos}</span>
      </span>`;
    }).join("");

    const goals = goalCounts[name] || 0;
    const goalHtml = goals > 0
      ? `<span class="report-goals">⚽ ${goals}</span>`
      : "";

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

// ── Event listeners ──────────────────────────────────────────────────────────

document.getElementById("btn-next").addEventListener("click", () => {
  if (showingReport) return;
  if (currentSlot < SLOTS.length - 1) {
    currentSlot++;
    render();
  } else {
    showingReport = true;
    renderReport();
  }
});

document.getElementById("btn-prev").addEventListener("click", () => {
  if (showingReport) {
    showMatch();
    return;
  }
  if (currentSlot > 0) {
    currentSlot--;
    render();
  }
});

// ── Init ─────────────────────────────────────────────────────────────────────

render();
