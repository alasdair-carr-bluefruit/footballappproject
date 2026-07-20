// Settings screen (T1.3/T1.4) — account self-service: change email address
// (with a re-verify link to the new address), a multi-team teaser, and the
// destructive "Clear squad & data" action gated behind a type-to-confirm modal.
import { api } from "./api.js";
import { state } from "./state.js";
import { showScreen } from "./pitch.js";
import { showToast } from "./toast.js";

// ── Open / populate ─────────────────────────────────────────────────────────────
async function openSettings() {
  showScreen("screen-settings");
  // Reset transient UI
  document.getElementById("settings-new-email").value = "";
  hide("email-change-msg");
  hide("email-change-devlink");

  document.getElementById("settings-email").textContent =
    (state.account && state.account.email) || "—";

  // Team name: prefer cached, else fetch.
  let teamName = state.teamInfo && state.teamInfo.team_name;
  if (!teamName) {
    const info = await api.getTeamInfo().catch(() => null);
    if (info) { state.teamInfo = info; teamName = info.team_name; }
  }
  document.getElementById("settings-team-name").textContent = teamName || "Your team";
}

function hide(id) { const el = document.getElementById(id); if (el) el.hidden = true; }
function showMsg(id, text) {
  const el = document.getElementById(id);
  if (el) { el.textContent = text; el.hidden = false; }
}

// Only wire the landing entry points when auth is on (single-user has no account).
const btnSettings = document.getElementById("btn-settings");
if (btnSettings) btnSettings.addEventListener("click", openSettings);

document.getElementById("btn-settings-back").addEventListener("click", () => {
  showScreen("screen-landing");
});

// ── Change email ─────────────────────────────────────────────────────────────────
document.getElementById("email-change-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const newEmail = document.getElementById("settings-new-email").value.trim();
  if (!newEmail) return;
  const btn = document.getElementById("btn-email-change-send");
  btn.disabled = true;
  hide("email-change-devlink");
  try {
    const res = await api.requestEmailChange(newEmail);
    showMsg("email-change-msg", `Check ${newEmail} for a confirmation link. Your current email keeps working until you tap it.`);
    if (res && res.dev_link) {
      const dl = document.getElementById("email-change-devlink");
      dl.textContent = "Dev link — confirm email change";
      dl.href = res.dev_link;
      dl.hidden = false;
    }
  } catch (err) {
    showMsg("email-change-msg", (err && err.message) || "Something went wrong — please try again.");
  } finally {
    btn.disabled = false;
  }
});

// ── Clear squad & data (type-to-confirm) ──────────────────────────────────────────
const clearOverlay = document.getElementById("clear-data-overlay");
const clearInput = document.getElementById("clear-data-confirm");
const clearConfirmBtn = document.getElementById("btn-clear-data-confirm");

document.getElementById("btn-clear-data").addEventListener("click", () => {
  clearInput.value = "";
  clearConfirmBtn.disabled = true;
  hide("clear-data-msg");
  clearOverlay.hidden = false;
  clearInput.focus();
});

document.getElementById("btn-clear-data-cancel").addEventListener("click", () => {
  clearOverlay.hidden = true;
});

clearInput.addEventListener("input", () => {
  clearConfirmBtn.disabled = clearInput.value.trim().toUpperCase() !== "DELETE";
});

clearConfirmBtn.addEventListener("click", async () => {
  clearConfirmBtn.disabled = true;
  showMsg("clear-data-msg", "Clearing…");
  try {
    await api.clearAccountData();
    clearOverlay.hidden = true;
    // Wipe local caches so the app doesn't show stale data.
    state.teamInfo = null;
    state.matchData = null;
    state.activeTournamentId = null;
    showToast("Squad & data cleared.");
    showScreen("screen-landing");
  } catch (err) {
    showMsg("clear-data-msg", (err && err.message) || "Could not clear your data — please try again.");
    clearConfirmBtn.disabled = false;
  }
});

// ── Sign out (mirrors the landing sign-out) ────────────────────────────────────────
document.getElementById("btn-settings-signout").addEventListener("click", async () => {
  try { await api.logout(); } catch (_) { /* clear locally regardless */ }
  location.reload();
});
