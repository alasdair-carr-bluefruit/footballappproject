import { state } from "./state.js";

// ── Fairness slider + rotation radios (shared by season new-match screen and
// tournament new/edit screen — NOT the pitch renderer, see pitch.js for the
// DEF_KEYS-family formation-layout helpers, which are a different concern) ──

// Light-hearted warnings for the competitive end of the slider — a fresh one
// each time the coach slides into the zone (think Ted Lasso, not Roy Kent)
const COMPETITIVE_QUIPS = [
  "Careful, Sir Alex! It's grassroots, not a cup final.",
  "Even Klopp rotates his squad! Give the bench a run.",
  "Parking the bus? Make sure everyone gets on it first.",
  "Save the tactical masterclass; let's ensure everyone gets a game.",
  "Great team, but remember: no Ballon d'Ors at this level.",
  "Three points are nice, but so is equal playing time.",
  "Steady on, Pep — this isn't the Champions League.",
  "Think more Ted Lasso, less Roy Kent.",
  "Relax — the scouts aren't watching. Everyone gets a run-out.",
  "The real trophy is the post-match snack bag.",
];

function pickCompetitiveQuip() {
  let i;
  do {
    i = Math.floor(Math.random() * COMPETITIVE_QUIPS.length);
  } while (i === state.lastQuipIndex);
  state.lastQuipIndex = i;
  return COMPETITIVE_QUIPS[i];
}

function updateFairnessLabel(value, elId = "fairness-value", warnId = "fairness-warning") {
  const el = document.getElementById(elId);
  const warn = document.getElementById(warnId);
  const v = parseInt(value);
  if (v <= 15) el.textContent = "Equal play — everyone gets the same time";
  else if (v <= 40) el.textContent = "Mostly fair — slight edge for stronger players";
  else if (v <= 60) el.textContent = "Balanced — skill matters but everyone plays";
  else if (v <= 85) el.textContent = "Competitive — best players get more time";
  else el.textContent = "Win mode — strongest lineup prioritised";
  if (warn) {
    const show = v > 60;
    if (show && warn.hidden) warn.textContent = pickCompetitiveQuip();
    warn.hidden = !show;
  }
}

document.getElementById("fairness-slider").addEventListener("input", e => {
  updateFairnessLabel(e.target.value);
});

function getRotationValue(formPrefix = "") {
  const name = formPrefix ? `${formPrefix}-rotation` : "rotation";
  const checked = document.querySelector(`input[name="${name}"]:checked`);
  return checked ? parseInt(checked.value) : 50;
}

// ── Team size & formation pickers (season + tournament) ─────────────────────
// Season and tournament run structurally identical size/formation pickers over
// different DOM ids and different state slots; these two helpers parametrise the
// shared body so the flows differ only in what they pass in.

// Highlight the active size button within a given picker container.
function highlightActiveSize(pickerId, size) {
  document.querySelectorAll(`${pickerId} .size-btn`).forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.size) === size);
  });
}

// Populate a formation <select> from the cached game-config for `size`, falling
// back to a hard-coded default per size when configs haven't loaded yet.
function buildFormationOptions(selectId, size) {
  const select = document.getElementById(selectId);
  select.innerHTML = "";
  if (state.gameConfigs && state.gameConfigs[String(size)]) {
    const cfg = state.gameConfigs[String(size)];
    cfg.formations.forEach(f => {
      const opt = document.createElement("option");
      opt.value = f.notation;
      opt.textContent = f.notation;
      if (f.notation === cfg.default_formation) opt.selected = true;
      select.appendChild(opt);
    });
  } else {
    const defaults = { 5: "1-2-1", 6: "1-3-1", 7: "2-3-1", 9: "3-3-2", 11: "4-4-2" };
    const opt = document.createElement("option");
    opt.value = defaults[size] || "1-2-1";
    opt.textContent = opt.value;
    select.appendChild(opt);
  }
}

// Default minutes per period by team size (editable on the form).
// 5v5/6v6 = 10-min quarters, 7v7 = 12.5-min quarters, 9v9 = 30-min halves.
const PERIOD_MINUTES = { 5: 10, 6: 10, 7: 12.5, 9: 30 };

// Label + max reflect the period type: quarters cap at 22.5 min, halves at 45.
function updateLengthConstraints() {
  const halves = state.selectedPeriods === 2;
  const label = document.getElementById("match-length-label");
  if (label) label.textContent = halves ? "Minutes per half" : "Minutes per quarter";
  const input = document.getElementById("match-length");
  if (input) input.max = halves ? "45" : "22.5";
}

// ── Season: size drives formation options + period count ──
function selectSize(size) {
  state.selectedSize = size;
  highlightActiveSize("#size-picker", size);
  selectPeriods(size >= 9 ? 2 : 4);
  buildFormationOptions("formation-select", size);
  const lengthInput = document.getElementById("match-length");
  if (lengthInput) lengthInput.value = String(PERIOD_MINUTES[size] ?? 10);
  updateLengthConstraints();
}

function selectPeriods(periods) {
  state.selectedPeriods = periods;
  document.querySelectorAll("#period-picker .size-btn").forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.periods) === periods);
  });
  updateLengthConstraints();
}

document.getElementById("period-picker").addEventListener("click", e => {
  const btn = e.target.closest(".size-btn");
  if (btn) selectPeriods(parseInt(btn.dataset.periods));
});

document.getElementById("size-picker").addEventListener("click", e => {
  const btn = e.target.closest(".size-btn");
  if (btn) selectSize(parseInt(btn.dataset.size));
});

// Per-size preset mid-period sub cap (fallback if game-configs aren't cached yet).
const PRESET_MAX_SUBS = { 5: 2, 6: 2, 7: 3, 9: 4 };

// Populate the tournament max-subs picker. Bounds scale with team size (1 up to
// the outfield count = size − 1); the default is the size's preset mid_period_subs.
// A caller-supplied `selected` (or the current value, on a size change) is kept if
// it still fits the new size's range.
function buildMaxSubsOptions(size, selected) {
  const select = document.getElementById("tournament-max-subs");
  if (!select) return;
  const outfieldMax = Math.max(1, size - 1);
  const cfg = state.gameConfigs && state.gameConfigs[String(size)];
  const preset = cfg?.mid_period_subs ?? PRESET_MAX_SUBS[size] ?? Math.min(2, outfieldMax);
  const prev = selected != null ? Number(selected) : Number(select.value);
  const keep = Number.isFinite(prev) && prev >= 1 && prev <= outfieldMax ? prev : null;
  const chosen = keep ?? Math.min(preset, outfieldMax);
  select.innerHTML = "";
  for (let n = 1; n <= outfieldMax; n++) {
    const opt = document.createElement("option");
    opt.value = String(n);
    opt.textContent = n === preset ? `${n} (default)` : String(n);
    if (n === chosen) opt.selected = true;
    select.appendChild(opt);
  }
}

// ── Tournament: size drives formation + max-subs options (no period picker) ──
function tournamentSelectSize(size, maxSubs) {
  state.tournamentSelectedSize = size;
  highlightActiveSize("#tournament-size-picker", size);
  buildFormationOptions("tournament-formation-select", size);
  buildMaxSubsOptions(size, maxSubs);
}

document.getElementById("tournament-size-picker").addEventListener("click", e => {
  const btn = e.target.closest(".size-btn");
  if (btn) tournamentSelectSize(parseInt(btn.dataset.size));
});

document.getElementById("tournament-fairness-slider").addEventListener("input", e => {
  updateFairnessLabel(e.target.value, "tournament-fairness-value", "tournament-fairness-warning");
});

export { updateFairnessLabel, getRotationValue, selectSize, selectPeriods, tournamentSelectSize, buildMaxSubsOptions };
