import { api } from "./api.js";
import { state, ensureGameConfigs, refreshShirtNumbers } from "./state.js";
import { showScreen, enterPitchView, openMatch } from "./pitch.js";
import { tournamentSelectSize, updateFairnessLabel, getRotationValue } from "./setup-form.js";
import { withSaveToast } from "./toast.js";

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
  await ensureGameConfigs();
  // Reset to creation mode
  state.editingTournamentId = null;
  document.getElementById("new-tournament-title").textContent = "New Tournament";
  document.getElementById("btn-new-tournament-back").textContent = "◀ Tournaments";
  document.getElementById("btn-create-tournament").textContent = "Next: Select Players →";
  document.getElementById("tournament-num-matches").closest("label").hidden = false;
  document.getElementById("tournament-name-input").value = "";
  document.getElementById("tournament-date").value = new Date().toISOString().split("T")[0];
  document.getElementById("tournament-duration").value = "10";
  document.getElementById("tournament-halftime").checked = false;
  document.getElementById("tournament-fairness-slider").value = 0;
  updateFairnessLabel(0, "tournament-fairness-value", "tournament-fairness-warning");
  const defaultRotRadio = document.querySelector('input[name="tournament-rotation"][value="100"]');
  if (defaultRotRadio) defaultRotRadio.checked = true;
  document.getElementById("tournament-num-matches").value = "4";
  tournamentSelectSize(5);
  showScreen("screen-new-tournament");
});

// ── New tournament form ────────────────────────────────────────────────────────
document.getElementById("btn-new-tournament-back").addEventListener("click", () => {
  if (state.editingTournamentId) {
    state.editingTournamentId = null;
    loadTournamentLobby(state.activeTournamentId);
  } else {
    loadTournamentHome();
  }
});

document.getElementById("new-tournament-form").addEventListener("submit", async e => {
  e.preventDefault();
  const name = document.getElementById("tournament-name-input").value.trim();
  const date = document.getElementById("tournament-date").value;
  const formation = document.getElementById("tournament-formation-select").value;
  const duration = parseInt(document.getElementById("tournament-duration").value) || 10;
  const hasHalftime = document.getElementById("tournament-halftime").checked;
  const fairnessValue = parseInt(document.getElementById("tournament-fairness-slider").value);
  const rotationIntensity = getRotationValue("tournament");
  state.pendingNumMatches = Math.max(1, parseInt(document.getElementById("tournament-num-matches").value) || 1);

  if (!name) {
    document.getElementById("tournament-name-input").focus();
    return;
  }

  const btn = document.getElementById("btn-create-tournament");
  btn.disabled = true;
  btn.textContent = state.editingTournamentId ? "Saving…" : "Creating…";

  const payload = {
    name,
    date: date || new Date().toISOString().split("T")[0],
    team_size: state.tournamentSelectedSize,
    formation,
    match_duration_mins: duration,
    has_halftime: hasHalftime,
    fairness_value: fairnessValue,
    rotation_intensity: rotationIntensity,
  };

  if (state.editingTournamentId) {
    const updated = await api.updateTournament(state.editingTournamentId, payload)
      .catch(err => { alert(err.message); return null; });
    btn.disabled = false;
    btn.textContent = "Next: Select Players →";
    if (!updated) return;
    // Go to squad screen so coach can confirm/change players too
    loadTournamentSquadScreen(state.editingTournamentId, state.pendingNumMatches);
  } else {
    const tournament = await api.createTournament(payload)
      .catch(err => { alert(err.message); return null; });
    btn.disabled = false;
    btn.textContent = "Next: Select Players →";
    if (!tournament) return;
    loadTournamentSquadScreen(tournament.id, state.pendingNumMatches);
  }
});

// ── Tournament Squad Selection ────────────────────────────────────────────────

function _effectivePositions(player, overrides) {
  // Derive the 4 toggleable positions for a player, respecting tournament overrides
  const pid = String(player.id);
  if (overrides && overrides[pid]) return overrides[pid];
  let prefs = [...(player.preferred_positions || [])];
  if (player.gk_status === "specialist") return ["GK"];
  if (!prefs.includes("GK") && ["preferred", "can_play"].includes(player.gk_status)) {
    prefs = ["GK", ...prefs];
  }
  if (prefs.length === 0) return ["DEF", "MID", "FWD"]; // can play any outfield
  return prefs;
}

async function loadTournamentSquadScreen(tournamentId, numMatches) {
  state.activeTournamentId = tournamentId;
  state.pendingPositionChanges = {};
  showScreen("screen-tournament-squad");

  const isEditing = state.editingTournamentId != null;

  const desc = document.getElementById("tournament-squad-desc");
  desc.textContent = isEditing
    ? "Update who's available. Changes will regenerate all planned matches."
    : `Select who's available today. ${numMatches} match${numMatches !== 1 ? "es" : ""} will be generated.`;

  const generateBtn = document.getElementById("btn-generate-all-matches");
  generateBtn.textContent = isEditing ? "Update Matches ▶" : "Generate Matches ▶";

  const ul = document.getElementById("tournament-squad-list");
  ul.innerHTML = "<li class='loading'>Loading players…</li>";

  // Fetch tournament data to get current available IDs and any existing overrides
  let currentAvailableIds = null;
  let existingOverrides = {};
  const tData = await api.getTournament(tournamentId).catch(() => null);
  if (tData) {
    state.activeTournamentData = tData;
    existingOverrides = tData.position_overrides || {};
    if (isEditing) {
      const firstPlanned = (tData.matches || []).find(m => m.status === "planned");
      if (firstPlanned?.available_player_ids) {
        currentAvailableIds = new Set(firstPlanned.available_player_ids);
      }
    }
  }

  const players = await api.getPlayers().catch(() => []);
  state.cachedSquadPlayers = players;
  ul.innerHTML = "";

  if (players.length === 0) {
    ul.innerHTML = "<li class='empty-state'>No players in squad — add some in Squad Management first</li>";
    return;
  }

  const ALL_POS = ["GK", "DEF", "MID", "FWD"];

  players.forEach(p => {
    const isChecked = !isEditing || currentAvailableIds == null || currentAvailableIds.has(p.id);
    const activePosSet = new Set(_effectivePositions(p, existingOverrides));

    const chipsHtml = ALL_POS.map(pos =>
      `<button type="button" class="pos-chip${activePosSet.has(pos) ? " active" : ""}" data-pos="${pos}">${pos}</button>`
    ).join("");

    const li = document.createElement("li");
    li.className = "avail-item";
    li.dataset.pid = p.id;
    li.innerHTML = `
      <label class="avail-label">
        <input type="checkbox" class="avail-check" data-pid="${p.id}" ${isChecked ? "checked" : ""} />
        <span class="avail-name">${p.name}</span>
        <span class="avail-skill">★${p.skill_rating}</span>
      </label>
      <div class="pos-chips">${chipsHtml}</div>
    `;
    ul.appendChild(li);
  });

  // Also show any guest players already added
  renderTournamentSquadGuests(tournamentId);
}

// Pos-chip toggle handler (event delegation on the list)
document.getElementById("tournament-squad-list").addEventListener("click", e => {
  const chip = e.target.closest(".pos-chip");
  if (!chip) return;
  const li = chip.closest("[data-pid]");
  if (!li) return;
  const pid = parseInt(li.dataset.pid);

  // Get current active positions for this player
  const allChips = [...li.querySelectorAll(".pos-chip")];
  const activeChips = allChips.filter(c => c.classList.contains("active"));

  // Don't allow deselecting the last active position
  if (chip.classList.contains("active") && activeChips.length === 1) return;

  chip.classList.toggle("active");

  const newPositions = allChips
    .filter(c => c.classList.contains("active"))
    .map(c => c.dataset.pos);

  state.pendingPositionChanges[pid] = newPositions;
});

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
      await withSaveToast(() => api.removeGuestPlayer(tournamentId, p.id));
      renderTournamentSquadGuests(tournamentId);
    });
    ul.appendChild(li);
  });
}

document.getElementById("btn-tournament-squad-back").addEventListener("click", () => {
  if (state.editingTournamentId) {
    const tid = state.editingTournamentId;
    state.editingTournamentId = null;
    loadTournamentLobby(tid);
  } else {
    loadTournamentHome();
  }
});

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
  const teamSize = state.activeTournamentData?.tournament?.team_size || state.tournamentSelectedSize || 5;

  if (availablePlayerIds.length < teamSize) {
    alert(`Select at least ${teamSize} players.`);
    return;
  }

  const btn = document.getElementById("btn-generate-all-matches");
  btn.disabled = true;
  const isEditing = state.editingTournamentId != null;

  // Save any position overrides before generating
  if (Object.keys(state.pendingPositionChanges).length > 0) {
    // Merge with existing overrides from tournament data
    const existing = state.activeTournamentData?.position_overrides || {};
    const merged = { ...existing, ...state.pendingPositionChanges };
    // Build final overrides: include existing overrides for players not in this squad screen
    await withSaveToast(() => api.setPositionOverrides(state.activeTournamentId, merged));
    state.pendingPositionChanges = {};
  }

  if (isEditing) {
    // Update existing planned matches with new player list
    btn.textContent = "Updating players…";
    await api.setAvailablePlayers(state.activeTournamentId, availablePlayerIds)
      .catch(err => { alert("Could not update players: " + err.message); });

    // Reload to get current match counts
    const tData = await api.getTournament(state.activeTournamentId).catch(() => null);
    const plannedMatches = (tData?.matches || []).filter(m => m.stage === "group" && m.status === "planned");
    const currentCount = plannedMatches.length;

    if (state.pendingNumMatches > currentCount) {
      // Generate additional matches
      const existing = (tData?.matches || []).filter(m => m.stage === "group").length;
      for (let i = existing + 1; i <= existing + (state.pendingNumMatches - currentCount); i++) {
        btn.textContent = `Adding match ${i - existing} of ${state.pendingNumMatches - currentCount}…`;
        await api.addTournamentMatch(state.activeTournamentId, {
          opponent: `Match ${i}`,
          stage: "group",
          available_player_ids: availablePlayerIds,
        }).catch(() => {});
      }
    } else if (state.pendingNumMatches < currentCount) {
      // Delete excess planned matches from the end
      const toDelete = plannedMatches.slice(state.pendingNumMatches);
      for (const m of toDelete) {
        btn.textContent = "Removing match…";
        await api.deleteMatch(m.id).catch(() => {});
      }
    }

    state.editingTournamentId = null;
  } else {
    for (let i = 1; i <= state.pendingNumMatches; i++) {
      btn.textContent = `Generating ${i} of ${state.pendingNumMatches}…`;
      await api.addTournamentMatch(state.activeTournamentId, {
        opponent: `Match ${i}`,
        stage: "group",
        available_player_ids: availablePlayerIds,
      }).catch(() => {});
    }
  }

  btn.disabled = false;
  btn.textContent = "Generate Matches ▶";
  loadTournamentLobby(state.activeTournamentId);
});

// ── Tournament Lobby ──────────────────────────────────────────────────────────
async function loadTournamentLobby(id) {
  state.activeTournamentId = id;
  showScreen("screen-tournament-lobby");

  document.getElementById("lobby-match-list").innerHTML = "<li class='loading'>Loading…</li>";
  document.getElementById("add-match-panel").hidden = true;

  const data = await api.getTournament(id).catch(err => {
    alert(err.message);
    loadTournamentHome();
    return null;
  });
  if (!data) return;

  state.activeTournamentData = data;
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

document.getElementById("btn-edit-tournament").addEventListener("click", async () => {
  const t = state.activeTournamentData?.tournament;
  if (!t) return;

  await ensureGameConfigs();

  // Pre-fill form with current tournament values
  state.editingTournamentId = t.id;
  document.getElementById("new-tournament-title").textContent = "Edit Tournament";
  document.getElementById("tournament-name-input").value = t.name || "";
  document.getElementById("tournament-date").value = t.date || "";
  document.getElementById("tournament-duration").value = t.match_duration_mins || 10;
  document.getElementById("tournament-halftime").checked = t.has_halftime || false;
  const tFairness = t.fairness_value ?? 0;
  document.getElementById("tournament-fairness-slider").value = tFairness;
  updateFairnessLabel(tFairness, "tournament-fairness-value", "tournament-fairness-warning");
  const tRotation = t.rotation_intensity ?? 50;
  const tRotRadio = document.querySelector(`input[name="tournament-rotation"][value="${tRotation}"]`)
    || document.querySelector('input[name="tournament-rotation"][value="50"]');
  if (tRotRadio) tRotRadio.checked = true;
  // Show num-matches in edit mode so coach can add/remove group matches
  const currentGroupCount = (state.activeTournamentData?.matches || []).filter(m => m.stage === "group").length;
  document.getElementById("tournament-num-matches").value = currentGroupCount || 1;
  document.getElementById("tournament-num-matches").closest("label").hidden = false;
  document.getElementById("btn-new-tournament-back").textContent = "◀ Back";
  document.getElementById("btn-create-tournament").textContent = "Next: Select Players →";
  tournamentSelectSize(t.team_size || 5);
  // Select the saved formation once options are populated
  const formationSelect = document.getElementById("tournament-formation-select");
  if (t.formation) formationSelect.value = t.formation;

  showScreen("screen-new-tournament");
});

document.getElementById("btn-tournament-stats").addEventListener("click", async () => {
  const stats = await api.getTournamentStats(state.activeTournamentId).catch(err => {
    alert("Could not load stats: " + err.message);
    return null;
  });
  if (!stats) return;

  const list = document.getElementById("tournament-stats-list");
  list.innerHTML = "";

  if (!stats.players || stats.players.length === 0) {
    list.innerHTML = "<li class='empty-state'>No match data yet</li>";
  } else {
    stats.players.forEach(p => {
      const li = document.createElement("li");
      li.className = "stats-row";
      const goalsHtml = p.goals > 0 ? `<span class="stats-goals">⚽ ${p.goals}</span>` : "";
      li.innerHTML = `
        <span class="stats-name">${p.name}</span>
        ${goalsHtml}
        <span class="stats-slots">${p.slots_played} slot${p.slots_played !== 1 ? "s" : ""}</span>
      `;
      list.appendChild(li);
    });
  }

  document.getElementById("tournament-stats-overlay").hidden = false;
});

document.getElementById("btn-tournament-stats-close").addEventListener("click", () => {
  document.getElementById("tournament-stats-overlay").hidden = true;
});

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
    const canDelete = m.status === "planned";
    const li = document.createElement("li");
    li.className = "match-item";
    if (m.status === "completed") li.classList.add("match-item-done");
    li.innerHTML = `
      <div class="match-item-main">
        <span class="match-badge">${stageLabel}</span>
        <span class="match-item-opponent">vs ${m.opponent || "TBD"}<button class="btn-icon match-rename" data-id="${m.id}" title="Edit opponent name">✎</button></span>
        ${statusBadge}
      </div>
      ${canDelete ? `<button class="btn-icon match-delete" data-id="${m.id}" title="Remove match">✕</button>` : ""}
    `;
    li.querySelector(".match-item-main").addEventListener("click", e => {
      if (e.target.closest(".match-rename")) return;
      openMatch(m.id, "tournament");
    });
    li.querySelector(".match-rename").addEventListener("click", e => {
      e.stopPropagation();
      const current = m.opponent || "";
      const newName = prompt("Opponent name:", current);
      if (newName === null) return; // cancelled
      const trimmed = newName.trim();
      api.updateMatchOpponent(state.activeTournamentId, m.id, trimmed).then(() => {
        loadTournamentLobby(state.activeTournamentId);
      }).catch(err => alert("Could not update: " + err.message));
    });
    if (canDelete) {
      li.querySelector(".match-delete").addEventListener("click", async e => {
        e.stopPropagation();
        if (confirm(`Remove match vs ${m.opponent || "TBD"}?`)) {
          try {
            await api.deleteMatch(m.id);
            loadTournamentLobby(state.activeTournamentId);
          } catch (err) {
            alert("Could not remove match: " + err.message);
          }
        }
      });
    }
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
  state.activeTournamentStage = stage;
  document.getElementById("add-match-title").textContent =
    stage === "knockout" ? "Add Knockout Match" : "Add Group Match";
  document.getElementById("add-match-opponent").value = "";
  document.getElementById("knockout-options").hidden = stage !== "knockout";
  document.getElementById("knockout-fairness-slider").value = 50;
  updateFairnessLabel(50, "knockout-fairness-label", "knockout-fairness-warning");
  document.getElementById("add-match-panel").hidden = false;
}

document.getElementById("btn-add-group-match").addEventListener("click", () => openAddMatchPanel("group"));
document.getElementById("btn-add-knockout-match").addEventListener("click", () => openAddMatchPanel("knockout"));
document.getElementById("btn-add-match-cancel").addEventListener("click", () => {
  document.getElementById("add-match-panel").hidden = true;
});

document.getElementById("knockout-fairness-slider").addEventListener("input", e => {
  updateFairnessLabel(e.target.value, "knockout-fairness-label", "knockout-fairness-warning");
});

// Guest player form (overlay)
function updateGuestBestPositionOptions(selectedPositions, currentBest = "") {
  const sel = document.getElementById("guest-best-position");
  sel.innerHTML = '<option value="">Not set</option>';
  selectedPositions.forEach(pos => {
    const opt = document.createElement("option");
    opt.value = pos;
    opt.textContent = pos;
    if (pos === currentBest) opt.selected = true;
    sel.appendChild(opt);
  });
}

document.getElementById("guest-position-checkboxes").addEventListener("change", () => {
  const checked = [...document.querySelectorAll("#guest-position-checkboxes input:checked")].map(cb => cb.value);
  const currentBest = document.getElementById("guest-best-position").value;
  updateGuestBestPositionOptions(checked, checked.includes(currentBest) ? currentBest : "");
});

document.getElementById("btn-show-add-guest").addEventListener("click", () => {
  document.getElementById("guest-name").value = "";
  document.getElementById("guest-skill").value = "3";
  document.getElementById("guest-shirt-number").value = "";
  document.querySelectorAll("#guest-position-checkboxes input").forEach(cb => cb.checked = false);
  updateGuestBestPositionOptions([]);
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

  const preferred = [...document.querySelectorAll("#guest-position-checkboxes input:checked")].map(cb => cb.value);
  const bestPos = document.getElementById("guest-best-position").value;
  const skill = parseInt(document.getElementById("guest-skill").value) || 3;
  const shirtRaw = document.getElementById("guest-shirt-number").value.trim();

  // Derive gk_status the same way as the normal player form
  let gkStatus;
  if (preferred.includes("GK") && preferred.length === 1) {
    gkStatus = "specialist";
  } else if (bestPos === "GK") {
    gkStatus = "preferred";
  } else if (preferred.includes("GK")) {
    gkStatus = "can_play";
  } else {
    gkStatus = "emergency_only";
  }
  const defRestricted = preferred.length > 0 && !preferred.includes("DEF");

  const btn = document.getElementById("btn-add-guest-confirm");
  btn.disabled = true;
  btn.textContent = "Adding…";

  const guest = await api.addGuestPlayer(state.activeTournamentId, {
    name,
    gk_status: gkStatus,
    def_restricted: defRestricted,
    skill_rating: skill,
    preferred_positions: preferred,
    best_position: bestPos,
    shirt_number: shirtRaw !== "" ? parseInt(shirtRaw, 10) : null,
  }).catch(err => { alert(err.message); return null; });

  btn.disabled = false;
  btn.textContent = "Add Player";
  if (!guest) return;

  document.getElementById("guest-form-overlay").hidden = true;
  loadTournamentLobby(state.activeTournamentId);
});

// Generate tournament match
document.getElementById("btn-generate-tournament-match").addEventListener("click", async () => {
  // Opponent name is optional — auto-name like batch generation does; the
  // coach can rename later from the lobby (✎)
  const opponent = document.getElementById("add-match-opponent").value.trim()
    || `Match ${(state.activeTournamentData?.matches?.length || 0) + 1}`;

  // Use all players currently in the tournament (squad + any guests)
  const t = state.activeTournamentData;
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
    stage: state.activeTournamentStage,
    available_player_ids: availablePlayerIds,
  };

  if (state.activeTournamentStage === "knockout") {
    body.knockout_fairness_value = parseInt(document.getElementById("knockout-fairness-slider").value);
  }

  const result = await api.addTournamentMatch(state.activeTournamentId, body).catch(err => {
    alert(err.message);
    return null;
  });

  btn.disabled = false;
  btn.textContent = "Generate ▶";

  if (!result) return;

  document.getElementById("add-match-panel").hidden = true;
  state.pitchBackContext = "tournament";

  // Update shirt numbers cache
  refreshShirtNumbers();

  enterPitchView(result);
});

export { loadTournamentHome, loadTournamentLobby };
