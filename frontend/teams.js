// Multi-team switcher (T1.1). One account can own several squads; the "active"
// team is just account.squad_id server-side, so switching = POST activate + a
// local cache reset (no reload). The header pill is the primary switcher (both
// home screens, parity); Settings hosts the same list as a "manage" path.
import { api } from "./api.js";
import { state, refreshTeams, setRole } from "./state.js";
import { showToast } from "./toast.js";
import { loadHome } from "./season.js";
import { loadTournamentHome } from "./tournament.js";
import { loadSquad } from "./screens.js";
import { showScreen } from "./pitch.js";

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
  const badge = active && active.role === "assistant"
    ? `<span class="role-badge">Assistant</span>` : "";
  el.innerHTML = `<button type="button" class="team-pill" title="Switch team">
    <span class="team-pill-name">${escapeHtml(name)}</span>${badge}
    <span class="team-pill-caret" aria-hidden="true">▾</span>
  </button>`;
  el.querySelector(".team-pill").addEventListener("click", openTeamSwitcher);
  if (containerId === "team-pill-landing") {
    // Landing gets the bigger standalone announcement banner instead of the
    // small pill popover — avoid showing both on the same screen.
    maybeShowLandingCallout();
  } else {
    maybeShowNewFeatureCallout(el);
  }
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

// ── Landing "multi-team is live" announcement banner ─────────────────────────
// A more prominent, one-time callout on the landing screen (separate key from the
// pill popover so a coach who dismissed the small hint still gets the big news).
const MULTITEAM_LANDING_KEY = "gaffer_multiteam_landing_seen";
function maybeShowLandingCallout() {
  const el = document.getElementById("multiteam-callout");
  if (!el) return;
  // Only when the switcher is actually usable (auth on + owned team) and not yet seen.
  el.hidden = !switcherEnabled() || !!localStorage.getItem(MULTITEAM_LANDING_KEY);
}

function dismissLandingCallout() {
  localStorage.setItem(MULTITEAM_LANDING_KEY, "1");
  const el = document.getElementById("multiteam-callout");
  if (el) el.hidden = true;
}

// Re-render every pill slot (whichever is on screen). Call after any team change.
export function renderTeamPills() {
  renderTeamPill("team-pill-home");
  renderTeamPill("team-pill-tournament");
  renderTeamPill("team-pill-landing");
  renderTeamPill("team-pill-squad");
}

// ── Switcher sheet ───────────────────────────────────────────────────────────
export async function openTeamSwitcher({ skipFetch = false } = {}) {
  dismissNewFeatureCallout();  // they found the switcher — retire the hint
  // Show the cached list instantly, then refresh it in place.
  renderTeamList("team-switcher-list", { allowRemove: true, onAfter: openTeamSwitcher });
  switcherOverlay().hidden = false;
  if (skipFetch) return;
  await refreshTeams();
  renderTeamList("team-switcher-list", { allowRemove: true, onAfter: openTeamSwitcher });
}

function closeSwitcher() { switcherOverlay().hidden = true; }

// Shared row renderer for the pill sheet AND the Settings list.
function renderTeamList(listId, { allowRemove, onAfter }) {
  const list = document.getElementById(listId);
  if (!list) return;
  list.innerHTML = "";
  // Only teams you head can be removed, and never your last one (assistants leave
  // a team from Settings instead).
  const headedCount = state.teams.filter(t => t.role !== "assistant").length;
  state.teams.forEach(t => {
    const name = (t.team_name || "").trim() || "Unnamed team";
    const isAsst = t.role === "assistant";
    const canRemove = allowRemove && !isAsst && headedCount > 1;
    const sub = isAsst
      ? `<span class="team-row-sub">Assistant coach${t.head_name ? ` · ${escapeHtml(t.head_name)}'s team` : ""}</span>` : "";
    const li = document.createElement("li");
    li.className = "team-row" + (t.is_active ? " team-row--active" : "");
    li.innerHTML = `
      <button type="button" class="team-row-main">
        <span class="team-row-check" aria-hidden="true">${t.is_active ? "✓" : ""}</span>
        <span class="team-row-name">${escapeHtml(name)}${sub}</span>
        <span class="team-row-count">${t.player_count} player${t.player_count === 1 ? "" : "s"}</span>
      </button>
      ${canRemove ? `<button type="button" class="btn-icon team-row-remove" title="Remove team">🗑</button>` : ""}
    `;
    li.querySelectorAll("button").forEach(b => { b.disabled = teamActionBusy; });
    li.querySelector(".team-row-main").addEventListener("click", () => {
      if (t.is_active) { closeSwitcher(); return; }
      switchTeam(t.id, name);
    });
    const rm = li.querySelector(".team-row-remove");
    if (rm) rm.addEventListener("click", (e) => { e.stopPropagation(); promptRemoveTeam(t.id, name, onAfter); });
    list.appendChild(li);
  });
}

// ── Busy lock ──────────────────────────────────────────────────────────────────
// While a team action is in flight every team control is inert, so a slow network
// can never turn a second tap into an action on a different (re-rendered) row.
let teamActionBusy = false;
function setTeamBusy(busy) {
  teamActionBusy = busy;
  document.querySelectorAll(
    ".team-row-main, .team-row-remove, #btn-team-add, #btn-settings-add-team, #btn-team-remove-confirm"
  ).forEach(el => { el.disabled = busy; });
}

// Apply a server response that carries the refreshed team list + team info
// (activate / delete return both, so no follow-up requests are needed).
function applyTeamsResponse(res) {
  state.teams = res.teams || state.teams;
  const active = state.teams.find(t => t.is_active);
  state.activeSquadId = res.active_squad_id ?? (active ? active.id : state.activeSquadId);
  if (active) setRole(active.role);
  if (res.team_info) state.teamInfo = res.team_info;
}

// ── Switch ───────────────────────────────────────────────────────────────────
// Optimistic: the sheet closes and the pill/role flip on tap; the server call
// follows, and we roll back if it fails.
async function switchTeam(id, name) {
  if (teamActionBusy) return;
  const target = state.teams.find(t => t.id === id);
  const previous = { teams: state.teams, teamInfo: state.teamInfo, role: state.role };
  setTeamBusy(true);
  state.teams = state.teams.map(t => ({ ...t, is_active: t.id === id }));
  if (target) {
    setRole(target.role);
    state.teamInfo = { team_name: target.team_name, team_logo: target.team_logo };
  }
  closeSwitcher();
  renderTeamPills();
  try {
    const res = await api.activateTeam(id);
    resetTeamCaches();
    applyTeamsResponse(res);
    refreshActiveViews();
    showToast(`Switched to ${name}`);
  } catch (err) {
    state.teams = previous.teams;
    state.teamInfo = previous.teamInfo;
    setRole(previous.role);
    renderTeamPills();
    showToast((err && err.message) || "Couldn't switch team — try again.");
  } finally {
    setTeamBusy(false);
  }
}

// ── Add ────────────────────────────────────────────────────────────────────────
export async function addTeam() {
  if (teamActionBusy) return;
  setTeamBusy(true);
  let created;
  try {
    created = await api.createTeam({});
  } catch (err) {
    showToast((err && err.message) || "Couldn't create the team — try again.");
    setTeamBusy(false);
    return;
  }
  resetTeamCaches();
  // The new team is blank and now active: no need to re-fetch its info.
  state.teamInfo = { team_name: created.team_name || "", team_logo: created.team_logo || "" };
  state.teams = [...state.teams.map(t => ({ ...t, is_active: false })), created];
  state.activeSquadId = created.id;
  setRole("head");
  setTeamBusy(false);
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
  if (teamActionBusy) return;
  pendingRemove = { id, name, onAfter };
  document.getElementById("team-remove-name").textContent = name;
  const msg = document.getElementById("team-remove-msg");
  if (msg) msg.hidden = true;
  removeOverlay().hidden = false;
}

async function confirmRemoveTeam() {
  if (!pendingRemove || teamActionBusy) return;
  const { id, name, onAfter } = pendingRemove;
  pendingRemove = null;  // a second tap can't re-fire this removal
  const wasActive = activeTeam()?.id === id;
  setTeamBusy(true);
  // Optimistic: close the dialog and drop the row now; the server does the rest.
  removeOverlay().hidden = true;
  const previousTeams = state.teams;
  state.teams = state.teams.filter(t => t.id !== id);
  if (typeof onAfter === "function") onAfter({ skipFetch: true });
  try {
    const res = await api.deleteTeam(id);
    if (wasActive) resetTeamCaches();  // server moved us to another team
    applyTeamsResponse(res);
    renderTeamPills();
    if (typeof onAfter === "function") onAfter({ skipFetch: true });
    if (wasActive) refreshActiveViews();
    showToast(`Removed ${name}`);
  } catch (err) {
    state.teams = previousTeams;
    if (typeof onAfter === "function") onAfter({ skipFetch: true });
    showToast(`Couldn't remove ${name}: ${(err && err.message) || "please try again"}`);
  } finally {
    setTeamBusy(false);
  }
}

// ── Settings "Teams" list (secondary path) ────────────────────────────────────
export async function renderSettingsTeams({ skipFetch = false } = {}) {
  if (!skipFetch) {
    renderTeamList("settings-team-list", { allowRemove: true, onAfter: renderSettingsTeams });  // cached, instant
    await refreshTeams();
  }
  renderTeamList("settings-team-list", { allowRemove: true, onAfter: renderSettingsTeams });
  const active = activeTeam();
  const nameEl = document.getElementById("settings-team-name");
  if (nameEl) nameEl.textContent = (active && (active.team_name || "").trim()) || "Your team";
}

// After the account gains or loses access to a team (joined, left, removed): the
// server may have moved the active team, so reset caches and re-derive the role.
export async function afterTeamAccessChange() {
  resetTeamCaches();
  await refreshTeams();
  await primeTeamInfo();
  renderTeamPills();
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
  else if (current === "screen-squad") {
    if (state.role === "assistant") showScreen("screen-landing");  // squad management is head-only
    else loadSquad();
  }
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
// Landing announcement: tapping the body opens the switcher (and retires the banner); ✕ just dismisses.
document.getElementById("btn-multiteam-callout")?.addEventListener("click", () => { dismissLandingCallout(); openTeamSwitcher(); });
document.getElementById("btn-multiteam-callout-dismiss")?.addEventListener("click", dismissLandingCallout);
document.getElementById("btn-team-remove-confirm")?.addEventListener("click", confirmRemoveTeam);
// Tap the backdrop to dismiss the switcher (matches other form-overlays' feel).
switcherOverlay()?.addEventListener("click", (e) => { if (e.target === switcherOverlay()) closeSwitcher(); });
