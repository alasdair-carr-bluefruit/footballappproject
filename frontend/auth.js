// Multi-user auth gate (v1.1). Runs before the app boots: probes /api/auth/me,
// and if auth is enabled but the coach isn't signed in, routes to the login or
// invite-redeem screen (or verifies a magic-link token from the URL). When auth
// is OFF (single-user dev/default), /me returns 200 and we boot straight through,
// so nothing here changes today's behaviour.
import { api, setUnauthorizedHandler } from "./api.js";
import { state, setRole } from "./state.js";
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
  if (me) { state.account = me; toggleSignout(me); setRole(me.role); }
  appBooted = true;
  bootApp();
}

// ── Assistant-coach invites (T3.2) ─────────────────────────────────────────────
// A `?assist=` link adds whoever opens it as an assistant on the inviting team.
// Signed in → confirm screen → POST /teams/join. New person → the join form, which
// redeems the token as a new account. Existing account but signed out → we park the
// token here, they sign in by magic link, then land on the confirm screen.
const PENDING_ASSIST_KEY = "gaffer_pending_assist";

function pendingAssist() {
  try { return localStorage.getItem(PENDING_ASSIST_KEY); } catch (_) { return null; }
}
function setPendingAssist(token) {
  try {
    if (token) localStorage.setItem(PENDING_ASSIST_KEY, token);
    else localStorage.removeItem(PENDING_ASSIST_KEY);
  } catch (_) { /* storage blocked — the link still works if reopened */ }
}

function assistCopy(preview) {
  const team = (preview && preview.team_name) || "a team";
  const head = preview && preview.head_name;
  return {
    title: `Join ${team}`,
    sub: head
      ? `${head} has invited you to be an assistant coach for ${team} on Level.`
      : `You've been invited to be an assistant coach for ${team} on Level.`,
  };
}

// Signed-in accept. Always an explicit tap (never on load).
async function showAssistJoin(token, me) {
  showScreen("screen-assist-join");
  const msg = document.getElementById("assist-join-msg");
  const btn = document.getElementById("btn-assist-join-confirm");
  msg.hidden = true;
  btn.disabled = false;
  let preview = null;
  try { preview = await api.previewAssistInvite(token); } catch (_) {
    setPendingAssist(null);
    clearAuthParams();
    msg.textContent = "That invite link is invalid or has expired — ask the head coach for a new one.";
    msg.hidden = false;
    btn.disabled = true;
  }
  const copy = assistCopy(preview);
  document.getElementById("assist-join-title").textContent = copy.title;
  document.getElementById("assist-join-sub").textContent = copy.sub;

  btn.onclick = async () => {
    btn.disabled = true;
    try {
      await api.joinAsAssistant(token);
      setPendingAssist(null);
      clearAuthParams();
      enterApp(await api.me());
    } catch (err) {
      msg.textContent = (err && err.message) || "Couldn't join the team — try again.";
      msg.hidden = false;
      btn.disabled = false;
    }
  };
  document.getElementById("btn-assist-join-skip").onclick = () => {
    setPendingAssist(null);
    clearAuthParams();
    enterApp(me);
  };
}

// Signed out: re-word the join form for an assistant invite.
async function showAssistSignup(token) {
  showScreen("screen-join");
  maybeShowInAppNudge();
  let preview = null;
  try { preview = await api.previewAssistInvite(token); } catch (_) { /* form shows the error on submit */ }
  const copy = assistCopy(preview);
  document.getElementById("join-title").textContent = copy.title;
  document.getElementById("join-sub").textContent = copy.sub + " Enter your details to get started.";
  document.getElementById("btn-join-create").textContent = "Join as assistant coach";
  const haveAccount = document.getElementById("btn-join-have-account");
  haveAccount.hidden = false;
  haveAccount.onclick = () => parkAssistAndSignIn(token, document.getElementById("join-email").value.trim());
}

// Existing coach, signed out: sign in first; the confirm screen follows the magic link.
function parkAssistAndSignIn(token, email) {
  setPendingAssist(token);
  clearAuthParams();
  showLogin("Sign in with your Level email. Open the sign-in link on this device and you'll be asked to join the team.");
  if (email) document.getElementById("login-email").value = email;
}

// After a successful sign-in, finish a parked assistant invite if there is one.
function enterAppOrAssist(me) {
  const token = pendingAssist();
  if (token && me && me.auth_enabled) showAssistJoin(token, me);
  else enterApp(me);
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
    enterAppOrAssist(me);
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

// Reclaim confirm click-through (link emailed to the OLD address after an email
// change). Reverts the email + signs out all devices, then routes to login.
function showReclaim(token) {
  showScreen("screen-reclaim");
  maybeShowInAppNudge();
  const btn = document.getElementById("btn-reclaim-confirm");
  const msg = document.getElementById("reclaim-msg");
  if (msg) msg.hidden = true;
  btn.disabled = false;
  btn.onclick = async () => {
    btn.disabled = true;
    if (msg) { msg.hidden = false; msg.textContent = "Reclaiming…"; }
    try {
      const res = await api.reclaimSquad(token);
      clearAuthParams();
      showLogin(`Your squad is restored and all devices were signed out. Sign in with ${res.email} to continue.`);
    } catch (_) {
      clearAuthParams();
      showLogin("That reclaim link was invalid or has expired.");
    }
  };
}

async function runGate() {
  // A reclaim / email-change link is an explicit action that must run even when
  // already signed in (the link usually opens in the same logged-in browser).
  const params0 = new URLSearchParams(location.search);
  const reclaimToken = params0.get("reclaim");
  if (reclaimToken) {
    showReclaim(reclaimToken);
    return;
  }
  const emailChangeToken = params0.get("email_change");
  if (emailChangeToken) {
    showEmailChange(emailChangeToken);
    return;
  }
  const assistToken = params0.get("assist");
  const probe = await probeMe();
  if (probe.me && probe.me.auth_enabled && (assistToken || pendingAssist())) {
    showAssistJoin(assistToken || pendingAssist(), probe.me);
    return;
  }
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
  } else if (assistToken) {
    showAssistSignup(assistToken);
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
  const params = new URLSearchParams(location.search);
  const assistToken = params.get("assist");
  const token = assistToken || params.get("invite");
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
    if (assistToken && err && err.status === 409) {
      // They already have a Level account: sign in first, then accept the invite.
      parkAssistAndSignIn(assistToken, email);
      document.getElementById("login-msg").textContent = "You already have a Level account — "
        + "enter your email for a sign-in link. Open it on this device and you'll be asked to join the team.";
      return;
    }
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
