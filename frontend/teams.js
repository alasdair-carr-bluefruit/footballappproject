// Multi-team switcher (T1.1). One account can own several squads; the "active"
// team is just account.squad_id server-side, so switching = POST activate + a
// local cache reset (no reload). The header pill is the primary switcher (both
// home screens, parity); Settings hosts the same list as a "manage" path.
import { api } from "./api.js";
import { state, refreshTeams } from "./state.js";
import { showToast } from "./toast.js";
import { loadHome } from "./season.js";
import { loadTournamentHome } from "./tournament.js";
import { loadSquad } from "./screens.js";

const switcherOverlay = () => document.getElementById("team-switcher-overlay");
const removeOverlay = () => document.getElementById("team-remove-overlay");

function activeTeam() {
  return state.teams.find(t => t.is_active) || null;
}

function switcherEnabled() {
  // Only meaningful with auth on and at least one owned team (auth-off dev mode
  // has a single implicit squad — no owner, no pill).
  return !!(state.account && state.account.auth_enabled && state.teams.length >= 1);
}

// ── Header pill (shared render, both homes) ──────────────────────────────────
export function renderTeamPill(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return;
  if (!switcherEnabled()) { el.innerHTML = ""; return; }
  const active = activeTeam();
  // Prefer state.teamInfo for the active team — it's the live source of truth for
  // the current squad's name (the cached teams list can lag a rename/first setup).
  const name = (state.teamInfo && (state.teamInfo.team_name || "").trim())
    || (active && (active.team_name || "").trim())
    || "Your team";
  el.innerHTML = `<button type="button" class="team-pill" title="Switch team">
    <span class="team-pill-name">${escapeHtml(name)}</span>
    <span class="team-pill-caret" aria-hidden="true">▾</span>
  </button>`;
  el.querySelector(".team-pill").addEventListener("click", openTeamSwitcher);
  maybeShowNewFeatureCallout(el);
}

// One-time "what's new" callout pointing at the pill — highlights how to add /
// switch teams. Dismissed permanently once seen or once the pill is used.
const MULTITEAM_SEEN_KEY = "gaffer_multiteam_seen";
function maybeShowNewFeatureCallout(slotEl) {
  if (localStorage.getItem(MULTITEAM_SEEN_KEY)) return;
  if (slotEl.querySelector(".team-pill-callout")) return;  // already shown here
  const callout = document.createElement("div");
  callout.className = "team-pill-callout";
  callout.innerHTML = `
    <p class="team-pill-callout-title">✨ New — Multiple teams (Beta)</p>
    <p class="team-pill-callout-body">Tap your team name up here to switch teams — or add a new one with <strong>+ Add a team</strong>.</p>
    <button type="button" class="team-pill-callout-dismiss">Got it</button>
  `;
  callout.querySelector(".team-pill-callout-dismiss").addEventListener("click", dismissNewFeatureCallout);
  slotEl.appendChild(callout);
}

function dismissNewFeatureCallout() {
  localStorage.setItem(MULTITEAM_SEEN_KEY, "1");
  document.querySelectorAll(".team-pill-callout").forEach(el => el.remove());
}

// Re-render both pills (whichever is on screen). Call after any team change.
export function renderTeamPills() {
  renderTeamPill("team-pill-home");
  renderTeamPill("team-pill-tournament");
}

// ── Switcher sheet ───────────────────────────────────────────────────────────
export async function openTeamSwitcher() {
  dismissNewFeatureCallout();  // they found the switcher — retire the hint
  await refreshTeams();
  renderTeamList("team-switcher-list", { allowRemove: true, onAfter: openTeamSwitcher });
  switcherOverlay().hidden = false;
}

function closeSwitcher() { switcherOverlay().hidden = true; }

// Shared row renderer for the pill sheet AND the Settings list.
function renderTeamList(listId, { allowRemove, onAfter }) {
  const list = document.getElementById(listId);
  if (!list) return;
  list.innerHTML = "";
  const canRemove = allowRemove && state.teams.length > 1;
  state.teams.forEach(t => {
    const name = (t.team_name || "").trim() || "Unnamed team";
    const li = document.createElement("li");
    li.className = "team-row" + (t.is_active ? " team-row--active" : "");
    li.innerHTML = `
      <button type="button" class="team-row-main">
        <span class="team-row-check" aria-hidden="true">${t.is_active ? "✓" : ""}</span>
        <span class="team-row-name">${escapeHtml(name)}</span>
        <span class="team-row-count">${t.player_count} player${t.player_count === 1 ? "" : "s"}</span>
      </button>
      ${canRemove ? `<button type="button" class="btn-icon team-row-remove" title="Remove team">🗑</button>` : ""}
    `;
    li.querySelector(".team-row-main").addEventListener("click", () => {
      if (t.is_active) { closeSwitcher(); return; }
      switchTeam(t.id, name);
    });
    const rm = li.querySelector(".team-row-remove");
    if (rm) rm.addEventListener("click", (e) => { e.stopPropagation(); promptRemoveTeam(t.id, name, onAfter); });
    list.appendChild(li);
  });
}

// ── Switch ───────────────────────────────────────────────────────────────────
async function switchTeam(id, name) {
  try {
    await api.activateTeam(id);
  } catch (err) {
    showToast((err && err.message) || "Couldn't switch team — try again.");
    return;
  }
  resetTeamCaches();
  await refreshTeams();
  await primeTeamInfo();
  closeSwitcher();
  refreshActiveViews();
  showToast(`Switched to ${name}`);
}

// ── Add ────────────────────────────────────────────────────────────────────────
export async function addTeam() {
  let created;
  try {
    created = await api.createTeam({});
  } catch (err) {
    showToast((err && err.message) || "Couldn't create the team — try again.");
    return;
  }
  resetTeamCaches();
  await refreshTeams();
  await primeTeamInfo();
  closeSwitcher();
  renderTeamPills();
  // Drop straight into squad management to name it + add players.
  state.squadBackContext = "landing";
  loadSquad();
  showToast("New team created — give it a name.");
  return created;
}

// ── Remove ───────────────────────────────────────────────────────────────────
let pendingRemove = null; // { id, name, onAfter }
function promptRemoveTeam(id, name, onAfter) {
  pendingRemove = { id, name, onAfter };
  document.getElementById("team-remove-name").textContent = name;
  const msg = document.getElementById("team-remove-msg");
  if (msg) msg.hidden = true;
  removeOverlay().hidden = false;
}

async function confirmRemoveTeam() {
  if (!pendingRemove) return;
  const { id, name, onAfter } = pendingRemove;
  const btn = document.getElementById("btn-team-remove-confirm");
  btn.disabled = true;
  const wasActive = activeTeam()?.id === id;
  try {
    await api.deleteTeam(id);
  } catch (err) {
    const msg = document.getElementById("team-remove-msg");
    if (msg) { msg.textContent = (err && err.message) || "Couldn't remove the team."; msg.hidden = false; }
    btn.disabled = false;
    return;
  }
  removeOverlay().hidden = true;
  btn.disabled = false;
  if (wasActive) resetTeamCaches();  // server moved us to another team
  await refreshTeams();
  if (wasActive) await primeTeamInfo();
  renderTeamPills();
  if (typeof onAfter === "function") onAfter();
  if (wasActive) refreshActiveViews();
  showToast(`Removed ${name}`);
}

// ── Settings "Teams" list (secondary path) ────────────────────────────────────
export async function renderSettingsTeams() {
  await refreshTeams();
  renderTeamList("settings-team-list", { allowRemove: true, onAfter: renderSettingsTeams });
  const active = activeTeam();
  const nameEl = document.getElementById("settings-team-name");
  if (nameEl) nameEl.textContent = (active && (active.team_name || "").trim()) || "Your team";
}

// ── Helpers ────────────────────────────────────────────────────────────────────
// Wipe in-memory caches so a switched/created team doesn't show stale data
// (mirrors settings.js clear-data handler + the plan's reset set).
function resetTeamCaches() {
  state.teamInfo = null;
  state.shirtNumbers = {};
  state.matchData = null;
  state.activeTournamentId = null;
  state.activeTournamentData = null;
  state.cachedSquadPlayers = [];
  state.goalCounts = {};
  state.removedPlayers = {};
}

async function primeTeamInfo() {
  const info = await api.getTeamInfo().catch(() => null);
  if (info) state.teamInfo = info;
}

// Re-render whichever list screen is currently visible after a team change.
function refreshActiveViews() {
  const current = document.querySelector(".screen:not([hidden])")?.id;
  if (current === "screen-tournament-home") loadTournamentHome();
  else if (current === "screen-home") loadHome();
  else if (current === "screen-settings") renderSettingsTeams();
  renderTeamPills();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

// ── Wire static controls ───────────────────────────────────────────────────────
document.getElementById("btn-team-switcher-close")?.addEventListener("click", closeSwitcher);
document.getElementById("btn-team-add")?.addEventListener("click", addTeam);
document.getElementById("btn-settings-add-team")?.addEventListener("click", addTeam);
document.getElementById("btn-team-remove-cancel")?.addEventListener("click", () => { removeOverlay().hidden = true; });
document.getElementById("btn-team-remove-confirm")?.addEventListener("click", confirmRemoveTeam);
// Tap the backdrop to dismiss the switcher (matches other form-overlays' feel).
switcherOverlay()?.addEventListener("click", (e) => { if (e.target === switcherOverlay()) closeSwitcher(); });
