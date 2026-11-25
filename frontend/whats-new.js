// "What's new" — a skippable full-screen run through recent features, one slide
// each with a small looping animation and a plain-English "why". Shown once to
// every returning coach (head or assistant; head-only slides skipped) when
// WHATS_NEW_VERSION changes. Skipping it leaves a lit-up Settings button and a
// "What's new" entry in Settings until they've looked; finishing (or opening it
// from Settings) clears that. Seen-state is per device (gaffer_ localStorage).
//
// To announce a new batch: add slides at the top of SLIDES and bump the version.
import { state, isAssistant } from "./state.js";
import { showToast } from "./toast.js";

export const WHATS_NEW_VERSION = "2026-11";
const KEY = "gaffer_whats_new";

const coin = (label, cls = "") => `<span class="demo-coin ${cls}">${label}</span>`;
const chipRow = (band, cls, picks, delay) => `
  <div class="chip-demo-row" style="--demo-delay:${delay}s">
    <span class="demo-chip demo-band pos-${cls}">${band}</span>
    <span class="demo-split">${picks.map(p => `<span class="demo-chip pos-${cls}">${p}</span>`).join("")}</span>
  </div>`;

const SLIDES = [
  {
    title: "Assistant coaches",
    body: "Bring in a co-coach. They see your plans, and can plan and run matches of their own.",
    why: "Matchday is easier with two of you, and whoever is running the game can do it from their own phone.",
    where: "Settings → Assistant coaches",
    headOnly: true,
    demo: `<div class="wn-coaches">
      ${coin("You")}<span class="wn-plan">Plan</span>${coin("Co", "demo-coin-alt")}
    </div>`,
  },
  {
    title: "Rested or unavailable?",
    body: "Untick a player and say why. Rested players are owed time in later matches. Ill or away players aren't.",
    why: "Resting a player is your choice, so the app makes sure they catch up later. A child who's ill shouldn't count against anyone.",
    where: "New match → pick players",
    demo: `<div class="wn-rested">
      <div class="wn-row">
        <span class="wn-check"></span><span class="wn-name">Ava</span>
        <span class="wn-chips"><span class="wn-chip">Unavailable</span><span class="wn-chip wn-chip-rested">Rested</span></span>
      </div>
      <span class="wn-owed">10′ owed next match</span>
    </div>`,
  },
  {
    title: "Tap a player mid-match",
    body: "Record a goal, or an injury. For an injury you pick who comes on, and nobody else moves.",
    why: "Injuries happen mid-game. Re-planning the whole team would confuse the kids, so only the injured child changes.",
    where: "Live match → tap a player",
    demo: `<div class="wn-pitch">
      ${coin("Ben")}
      <span class="wn-swap">${coin("Cal", "wn-hurt")}${coin("Eve", "wn-on demo-coin-alt")}</span>
      ${coin("Dan")}
    </div>`,
  },
  {
    title: "Detailed positions",
    beta: true,
    body: "Pick LB, CB, LW… instead of DEF / MID / ATT. Made mainly for 9v9, where width matters more.",
    why: "On a bigger pitch, left and right are different jobs. Switch it off any time and nothing is lost.",
    where: "Squad → Detailed positions",
    headOnly: true,
    demo: `<div class="chip-demo">${chipRow("DEF", "def", ["LB", "CB", "RB"], 0)}${chipRow("ATT", "fwd", ["LW", "CF", "RW"], 0.25)}</div>`,
  },
  {
    title: "Remembers your settings",
    body: "A new match or tournament starts with the same format and options as your last one.",
    why: "Most teams play the same format every week. Fewer taps before kick-off.",
    where: "New match / New tournament",
    demo: `<div class="wn-cards">
      <div class="wn-card"><small>Last match</small><span class="wn-pill">7v7 · 4 × 12.5′</span></div>
      <span class="wn-arrow">→</span>
      <div class="wn-card"><small>New match</small><span class="wn-pill wn-pill-copy">7v7 · 4 × 12.5′</span></div>
    </div>`,
  },
];

function readStatus() {
  try {
    const s = JSON.parse(localStorage.getItem(KEY) || "null");
    return s && s.v === WHATS_NEW_VERSION ? s.status : null;
  } catch (_) { return null; }
}
function writeStatus(status) {
  try { localStorage.setItem(KEY, JSON.stringify({ v: WHATS_NEW_VERSION, status })); } catch (_) { /* storage blocked */ }
}

// Skipped but not yet looked at → light up the way back in.
export function syncWhatsNewGlow() {
  const pending = readStatus() === "dismissed";
  document.getElementById("btn-settings")?.classList.toggle("has-news", pending);
  document.getElementById("btn-settings-whats-new")?.classList.toggle("has-news", pending);
}

// A brand-new coach has nothing to compare against — don't greet them with "new".
export function markWhatsNewSeen() {
  writeStatus("done");
  syncWhatsNewGlow();
}

// Slides this coach can act on (assistants can't invite coaches or change the squad).
const slides = () => SLIDES.filter(s => !(s.headOnly && isAssistant()));

// Called on boot for a returning coach. Needs Settings (auth on) to come back to.
export function maybeShowWhatsNew() {
  if (!(state.account && state.account.auth_enabled)) return;
  if (readStatus() === null) openWhatsNew();
  else syncWhatsNewGlow();
}

let index = 0;
let openedFromSettings = false;
const el = id => document.getElementById(id);

export function openWhatsNew({ fromSettings = false } = {}) {
  openedFromSettings = fromSettings;
  index = 0;
  el("wn-dots").innerHTML = slides().map(() => "<span></span>").join("");
  render();
  el("whats-new").hidden = false;
  el("btn-wn-next").focus();
}

function render() {
  const all = slides();
  const s = all[index];
  el("wn-demo").innerHTML = s.demo;  // fresh nodes → the animation restarts per slide
  el("wn-title").innerHTML = s.title + (s.beta ? ' <span class="beta-tag">Beta</span>' : "");
  el("wn-body").textContent = s.body;
  el("wn-why").textContent = s.why;
  el("wn-where").textContent = s.where;
  el("wn-count").textContent = `${index + 1} of ${all.length}`;
  [...el("wn-dots").children].forEach((d, i) => d.classList.toggle("active", i === index));
  el("btn-wn-back").hidden = index === 0;
  const last = index === all.length - 1;
  el("btn-wn-next").textContent = last ? "Got it" : "Next";
  el("btn-wn-skip").hidden = last;
}

function close(finished) {
  el("whats-new").hidden = true;
  if (finished || openedFromSettings) {
    writeStatus("done");
  } else {
    writeStatus("dismissed");
    showToast("Check out what's new any time in ⚙ Settings.");
  }
  syncWhatsNewGlow();
}

el("btn-wn-next").addEventListener("click", () => {
  if (index === slides().length - 1) { close(true); return; }
  index += 1;
  render();
});
el("btn-wn-back").addEventListener("click", () => {
  if (index > 0) { index -= 1; render(); }
});
el("btn-wn-skip").addEventListener("click", () => close(false));
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && !el("whats-new").hidden) close(false);
});
