// Settings screen (T1.3/T1.4) — account self-service: change email address
// (with a re-verify link to the new address), a multi-team teaser, and the
// destructive "Clear squad & data" action gated behind a type-to-confirm modal.
import { api } from "./api.js";
import { state } from "./state.js";
import { showScreen } from "./pitch.js";
import { showToast } from "./toast.js";
import { renderSettingsTeams } from "./teams.js";

// ── Open / populate ─────────────────────────────────────────────────────────────
async function openSettings() {
  showScreen("screen-settings");
  // Reset transient UI
  document.getElementById("settings-new-email").value = "";
  hide("email-change-msg");
  hide("email-change-devlink");

  document.getElementById("settings-email").textContent =
    (state.account && state.account.email) || "—";

  // Reset the invite-a-friend block (don't surface a link minted in a prior visit).
  document.getElementById("invite-result").hidden = true;
  document.getElementById("invite-link").value = "";
  hide("invite-msg");
  hide("invite-expiry-hint");
  document.getElementById("btn-invite-create").textContent = "Create invite link";

  // Multi-team list (also sets the "Current team" name from the active row).
  renderSettingsTeams();
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

// ── Invite a friend (growth loop) ─────────────────────────────────────────────────
const INVITE_SHARE_TEXT =
  "I'm using Level to sort fair player rotation for our grassroots team — here's a one-time invite to try it:";

document.getElementById("btn-invite-create").addEventListener("click", async () => {
  const btn = document.getElementById("btn-invite-create");
  btn.disabled = true;
  hide("invite-msg");
  try {
    const res = await api.inviteAFriend();
    document.getElementById("invite-link").value = res.link;
    document.getElementById("invite-result").hidden = false;
    // Native share sheet only exists on supported (mostly mobile) browsers.
    document.getElementById("btn-invite-share").hidden = typeof navigator.share !== "function";
    const days = res.expires_in_days;
    showMsg("invite-expiry-hint",
      `This link works once, for one coach${days ? `, and expires in ${days} days` : ""}. Create another any time.`);
    btn.textContent = "Create another link";
  } catch (err) {
    showMsg("invite-msg", (err && err.message) || "Couldn't create an invite link — please try again.");
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("btn-invite-copy").addEventListener("click", async () => {
  const link = document.getElementById("invite-link").value;
  if (!link) return;
  try {
    await navigator.clipboard.writeText(link);
    showToast("Invite link copied.");
  } catch (_) {
    // Clipboard API blocked (insecure context / permissions) — select for manual copy.
    const input = document.getElementById("invite-link");
    input.focus();
    input.select();
    showToast("Press ⌘/Ctrl+C to copy the link.");
  }
});

document.getElementById("btn-invite-share").addEventListener("click", async () => {
  const link = document.getElementById("invite-link").value;
  if (!link || typeof navigator.share !== "function") return;
  try {
    await navigator.share({ title: "Try Level", text: INVITE_SHARE_TEXT, url: link });
  } catch (_) { /* user dismissed the share sheet — no-op */ }
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

// ── Check for updates (hard refresh past the service-worker cache) ─────────────────
// Installed PWAs (esp. Android) have no easy "reload" — this clears the caches and
// pulls the latest assets. The SW is network-first, so the reload re-caches fresh.
document.getElementById("btn-check-updates").addEventListener("click", async () => {
  const btn = document.getElementById("btn-check-updates");
  btn.disabled = true;
  showMsg("check-updates-msg", "Checking for updates…");
  try {
    if ("serviceWorker" in navigator) {
      const reg = await navigator.serviceWorker.getRegistration();
      if (reg) await reg.update();
    }
    if (window.caches) {
      const keys = await caches.keys();
      await Promise.all(keys.map(k => caches.delete(k)));
    }
  } catch (_) { /* best effort — reload anyway */ }
  location.reload();
});

// ── Sign out (mirrors the landing sign-out) ────────────────────────────────────────
document.getElementById("btn-settings-signout").addEventListener("click", async () => {
  try { await api.logout(); } catch (_) { /* clear locally regardless */ }
  location.reload();
});
