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
import { showIntro, DEMOS } from "./intro.js";

export const WHATS_NEW_VERSION = "2026-11";
const KEY = "gaffer_whats_new";

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
    demo: DEMOS.handover(),
  },
  {
    title: "Add your other teams",
    body: "Coach more than one side? Add each team and switch between them from the team name at the top.",
    why: "Lots of coaches run two teams, or help with a brother's or sister's. One sign-in, and each team's players and matches stay separate.",
    where: "Tap your team name → Add a team",
    demo: `<div class="wn-teams">
      <span class="wn-team-pill"><span class="wn-team wn-team-a">Owls</span><span class="wn-team wn-team-b">Hawks</span> ▾</span>
      <span class="wn-team-list"><span>Owls</span><span>Hawks</span><span class="wn-team-add">+ Add a team</span></span>
    </div>`,
  },
  {
    title: "Rested or unavailable?",
    body: "Untick a player and say why. Rested players are owed time in later matches. Ill or away players aren't.",
    why: "Resting a player is your choice, so the app makes sure they catch up later. A child who's ill shouldn't count against anyone.",
    where: "New match → pick players",
    demo: DEMOS.rested,
  },
  {
    title: "Tap a player mid-match",
    body: "Record a goal, or an injury. For an injury you pick who comes on, and nobody else moves.",
    why: "Injuries happen mid-game. Re-planning the whole team would confuse the kids, so only the injured child changes.",
    where: "Live match → tap a player",
    demo: DEMOS.injury,
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
    demo: DEMOS.remembers(),
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

// ?whatsnew=reset — forget this device's seen-state (for testing the first-visit
// and skip paths again). Harmless anywhere: it only brings the carousel back.
try {
  const params = new URLSearchParams(location.search);
  if (params.get("whatsnew") === "reset") {
    localStorage.removeItem(KEY);
    params.delete("whatsnew");
    const qs = params.toString();
    history.replaceState({}, "", location.pathname + (qs ? `?${qs}` : "") + location.hash);
  }
} catch (_) { /* storage blocked */ }

export function openWhatsNew({ fromSettings = false } = {}) {
  showIntro(slides(), { kicker: "What's new" }).then(result => {
    if (result === "busy") return;
    if (result === "done" || fromSettings) {
      writeStatus("done");
    } else {
      writeStatus("dismissed");
      showToast("Check out what's new any time in ⚙ Settings.");
    }
    syncWhatsNewGlow();
  });
}
