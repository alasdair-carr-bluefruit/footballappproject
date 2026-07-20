// Multi-user auth gate (v1.1). Runs before the app boots: probes /api/auth/me,
// and if auth is enabled but the coach isn't signed in, routes to the login or
// invite-redeem screen (or verifies a magic-link token from the URL). When auth
// is OFF (single-user dev/default), /me returns 200 and we boot straight through,
// so nothing here changes today's behaviour.
import { api, setUnauthorizedHandler } from "./api.js";
import { state } from "./state.js";
import { showScreen } from "./pitch.js";
import { bootApp } from "./screens.js";

// Only bounce to the login screen for a 401 once the app has actually booted (an
// expired session mid-use). Before boot, the gate owns screen routing, so stray
// pre-auth 401s must not hijack the login/join screen it just showed.
let appBooted = false;

function clearAuthParams() {
  // Drop ?login=/?invite= from the URL so a refresh doesn't replay the token.
  history.replaceState({}, "", location.pathname);
}

function toggleSignout(me) {
  const on = !!(me && me.auth_enabled);
  const signout = document.getElementById("btn-signout");
  if (signout) signout.hidden = !on;
  const settings = document.getElementById("btn-settings");
  if (settings) settings.hidden = !on;  // Settings needs an account (auth on)
}

// Heuristic: are we inside an app's embedded webview (email/social) rather than a
// real browser? These have isolated cookie jars, so a session set here often
// won't carry to the browser the coach actually uses.
function isInAppBrowser() {
  const ua = navigator.userAgent || "";
  return /FBAN|FBAV|Instagram|Line|Twitter|WhatsApp|Snapchat|Pinterest|; wv\)|GSA\/|OutlookMobile|MicrosoftTeams/i.test(ua);
}

// Reveal the "open in your browser" nudge on the currently-shown auth screen when
// we look like an in-app webview. Copy buttons put the full URL on the clipboard
// (incl. any ?login=/?invite= token) so pasting into Safari/Chrome completes it.
function maybeShowInAppNudge() {
  if (isInAppBrowser()) {
    document.querySelectorAll(".auth-inapp").forEach((el) => { el.hidden = false; });
  }
}
document.querySelectorAll(".js-copy-link").forEach((btn) => {
  btn.addEventListener("click", () => {
    navigator.clipboard.writeText(location.href)
      .then(() => { btn.textContent = "Link copied ✓"; })
      .catch(() => { btn.textContent = "Copy failed — long-press the address bar"; });
  });
});

async function probeMe() {
  // Raw fetch (not api.me) so we can tell 401 (show login) from offline (be
  // permissive and boot — the app tolerates an unreachable server on its own).
  let res;
  try {
    res = await fetch("/api/auth/me", { credentials: "include" });
  } catch (_) {
    return { offline: true };
  }
  if (res.status === 401) return { unauth: true };
  if (!res.ok) return { offline: true };
  return { me: await res.json() };
}

function enterApp(me) {
  if (me) { state.account = me; toggleSignout(me); }
  appBooted = true;
  bootApp();
}

function showLogin(message) {
  showScreen("screen-login");
  const msg = document.getElementById("login-msg");
  const devlink = document.getElementById("login-devlink");
  if (devlink) devlink.hidden = true;
  if (msg) {
    msg.textContent = message || "";
    msg.hidden = !message;
  }
  maybeShowInAppNudge();
}

// Magic-link click-through. We show a Confirm screen and only POST /verify on an
// explicit tap — never on page load — so corporate mail scanners that pre-open the
// link can't burn the one-time token before the coach arrives.
function showVerify(token) {
  showScreen("screen-verify");
  maybeShowInAppNudge();
  const btn = document.getElementById("btn-verify-confirm");
  const msg = document.getElementById("verify-msg");
  if (msg) msg.hidden = true;
  btn.disabled = false;
  btn.onclick = async () => {
    btn.disabled = true;
    if (msg) { msg.hidden = false; msg.textContent = "Signing you in…"; }
    await handleVerify(token);
  };
}

async function handleVerify(token) {
  try {
    const me = await api.verifyLogin(token);
    clearAuthParams();
    enterApp(me);
  } catch (_) {
    clearAuthParams();
    showLogin("That sign-in link was invalid or has expired — enter your email for a fresh one.");
  }
}

// Email-change confirm click-through (link emailed to the NEW address). Same
// confirm-on-click discipline as sign-in so a mail scanner can't burn the token.
function showEmailChange(token) {
  showScreen("screen-email-change");
  maybeShowInAppNudge();
  const btn = document.getElementById("btn-email-change-confirm");
  const msg = document.getElementById("email-change-confirm-msg");
  if (msg) msg.hidden = true;
  btn.disabled = false;
  btn.onclick = async () => {
    btn.disabled = true;
    if (msg) { msg.hidden = false; msg.textContent = "Confirming…"; }
    try {
      const me = await api.confirmEmailChange(token);
      clearAuthParams();
      enterApp(me);
    } catch (_) {
      clearAuthParams();
      showLogin("That confirmation link was invalid or has expired — try changing your email again from Settings.");
    }
  };
}

async function runGate() {
  // An email-change confirm link is an explicit action that must run even when
  // already signed in (the link usually opens in the same logged-in browser).
  const emailChangeToken = new URLSearchParams(location.search).get("email_change");
  if (emailChangeToken) {
    showEmailChange(emailChangeToken);
    return;
  }
  const probe = await probeMe();
  if (probe.me || probe.offline) {
    // Authenticated, or auth disabled (me present), or server unreachable → boot.
    enterApp(probe.me || null);
    return;
  }
  // Not authenticated: check the URL for a magic-link / invite token.
  const params = new URLSearchParams(location.search);
  const loginToken = params.get("login");
  const inviteToken = params.get("invite");
  if (loginToken) {
    showVerify(loginToken);
  } else if (inviteToken) {
    showScreen("screen-join");
    maybeShowInAppNudge();
  } else {
    showLogin();
  }
}

// A mid-session 401 (expired/cleared cookie) drops back to the login screen —
// but only once booted, so the gate's own login/join routing isn't clobbered.
setUnauthorizedHandler(() => {
  if (appBooted) {
    showLogin("Your session has expired — enter your email for a fresh sign-in link.");
  }
});

// ── Login form: request a magic link ────────────────────────────────────────────
document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  if (!email) return;
  const btn = document.getElementById("btn-login-send");
  btn.disabled = true;
  const msg = document.getElementById("login-msg");
  const devlink = document.getElementById("login-devlink");
  try {
    const res = await api.requestLink(email);
    msg.textContent = "Check your email for a sign-in link. It expires shortly.";
    msg.hidden = false;
    // Dev convenience: no email provider configured → the API returns the link.
    if (res && res.dev_link) {
      devlink.textContent = "Dev link — open sign-in";
      devlink.href = res.dev_link;
      devlink.hidden = false;
    }
  } catch (_) {
    msg.textContent = "Something went wrong — please try again.";
    msg.hidden = false;
  } finally {
    btn.disabled = false;
  }
});

// ── Join form: redeem an invite ──────────────────────────────────────────────────
document.getElementById("join-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const token = new URLSearchParams(location.search).get("invite");
  const email = document.getElementById("join-email").value.trim();
  const displayName = document.getElementById("join-name").value.trim();
  const msg = document.getElementById("join-msg");
  if (!token) { showLogin(); return; }
  if (!email) return;
  const btn = document.getElementById("btn-join-create");
  btn.disabled = true;
  try {
    const me = await api.redeemInvite({ token, email, display_name: displayName });
    clearAuthParams();
    enterApp(me);
  } catch (err) {
    msg.textContent = (err && err.message) || "That invite link is invalid or expired.";
    msg.hidden = false;
    btn.disabled = false;
  }
});

// ── Sign out ─────────────────────────────────────────────────────────────────────
document.getElementById("btn-signout").addEventListener("click", async () => {
  try { await api.logout(); } catch (_) { /* clear locally regardless */ }
  location.reload();  // re-runs the gate → login screen
});

runGate();
