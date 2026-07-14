import { api } from "./api.js";
import { state, refreshShirtNumbers } from "./state.js";
import { showScreen } from "./pitch.js";
import { loadHome } from "./season.js";
import { loadTournamentHome } from "./tournament.js";
import { withSaveToast } from "./toast.js";

// ── First-launch tutorial ─────────────────────────────────────────────────────
// Check server first — if a team name exists the DB already has data (e.g. a
// returning user on a new device) so skip the tutorial entirely.
(async function initScreen() {
  try {
    const info = await api.getTeamInfo();
    if (info) state.teamInfo = info;
    if (info && info.team_name) {
      // Team already configured on server — skip tutorial regardless of localStorage
      localStorage.setItem("gaffer_onboarded", "1");
      showScreen("screen-landing");
      return;
    }
  } catch (_) { /* offline or first boot — fall through */ }

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
  await withSaveToast(() => api.updateTeamInfo({ team_name: name, team_logo: logo }));
  state.teamInfo = { team_name: name, team_logo: logo };
  localStorage.setItem("gaffer_onboarded", "1");
  showScreen("screen-landing");
  showSquadTip();
});

function showSquadTip() {
  if (localStorage.getItem("gaffer_squad_tip_dismissed")) return;
  document.getElementById("squad-onboarding").style.display = "flex";
  document.querySelector(".landing").classList.add("landing--onboarding");
}

function dismissSquadTip() {
  document.getElementById("squad-onboarding").style.display = "none";
  document.querySelector(".landing").classList.remove("landing--onboarding");
  localStorage.setItem("gaffer_squad_tip_dismissed", "1");
}

// ── Landing screen ────────────────────────────────────────────────────────────

// Auto-dismiss squad tip if players already exist (guards against cached JS etc.)
api.getPlayers().then(players => {
  if (players.length > 0) dismissSquadTip();
}).catch(() => {});

document.getElementById("btn-season-mode").addEventListener("click", () => loadHome());
document.getElementById("btn-tournament-mode").addEventListener("click", () => loadTournamentHome());
document.getElementById("btn-squad-management").addEventListener("click", () => {
  dismissSquadTip();
  state.squadBackContext = "landing";
  loadSquad();
});

// ── Bug reporting ─────────────────────────────────────────────────────────────

document.getElementById("btn-bug-report").addEventListener("click", () => {
  document.getElementById("bug-report-description").value = "";
  document.getElementById("bug-report-overlay").hidden = false;
});

document.getElementById("btn-bug-report-cancel").addEventListener("click", () => {
  document.getElementById("bug-report-overlay").hidden = true;
});

document.getElementById("bug-report-form").addEventListener("submit", async e => {
  e.preventDefault();
  const description = document.getElementById("bug-report-description").value.trim();
  if (description.length < 3) return;

  const context = {
    screen: document.querySelector(".screen:not([hidden])")?.id || "unknown",
    match_id: state.matchData?.match?.id ?? null,
    tournament_id: state.activeTournamentId,
    user_agent: navigator.userAgent,
  };

  const btn = document.getElementById("btn-bug-report-send");
  btn.disabled = true;
  btn.textContent = "Sending…";
  const result = await api.submitFeedback(description, context).catch(err => {
    alert(`Could not send the report: ${err.message}`);
    return null;
  });
  btn.disabled = false;
  btn.textContent = "Send report";

  if (!result) return;
  document.getElementById("bug-report-overlay").hidden = true;
  alert("Thanks — your report has been sent.");
});

// ── Squad screen ──────────────────────────────────────────────────────────────
async function loadSquad() {
  showScreen("screen-squad");
  closePlayerForm();

  // Populate team info fields
  const info = await api.getTeamInfo().catch(() => null);
  if (info) {
    state.teamInfo = info;
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

  // Rebuild shirt number map and detect conflicts
  const players = await refreshShirtNumbers();
  const numberCount = {};
  players.forEach(p => {
    if (p.shirt_number != null) {
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
      state.pendingDeletePlayerId = p.id;
      document.getElementById("delete-player-info").textContent =
        `Are you sure you want to remove ${p.name} from your squad? All previous match data including goals scored will be lost.`;
      document.getElementById("delete-player-overlay").hidden = false;
    });
    list.appendChild(li);
  });
}

function openPlayerForm(player = null) {
  state.editingPlayerId = player?.id ?? null;
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
  state.editingPlayerId = null;
}

document.getElementById("btn-squad-back").addEventListener("click", () => {
  if (state.squadBackContext === "landing") {
    dismissSquadTip(); // visited squad management = tip no longer needed
    showScreen("screen-landing");
  } else {
    loadHome();
  }
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
    state.teamInfo = await api.updateTeamInfo({ team_name: name, team_logo: logo });
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

  const id = state.editingPlayerId;
  closePlayerForm();

  if (id !== null) {
    await api.updatePlayer(id, data).catch(err => alert(err.message));
  } else {
    await api.addPlayer(data).catch(err => alert(err.message));
    dismissSquadTip(); // first player added — tip no longer needed
  }
  loadSquad();
});

// ── Delete player modal ────────────────────────────────────────────────────────
document.getElementById("btn-delete-player-cancel").addEventListener("click", () => {
  document.getElementById("delete-player-overlay").hidden = true;
  state.pendingDeletePlayerId = null;
});

document.getElementById("btn-delete-player-confirm").addEventListener("click", async () => {
  document.getElementById("delete-player-overlay").hidden = true;
  if (!state.pendingDeletePlayerId) return;
  const id = state.pendingDeletePlayerId;
  state.pendingDeletePlayerId = null;
  await api.deletePlayer(id).catch(err => alert(err.message));
  loadSquad();
});
