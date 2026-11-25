// The new-coach walkthrough (docs/WALKTHROUGH_PLAN.md): a short welcome tour after
// "Create my team", an assistant welcome after joining a team, and a 1–3 card
// intro the first time a coach reaches each screen. Copy is the owner-edited
// review doc (link in the plan). Coach language only: "stint" = one half of a
// quarter on the pitch; never "slot", "algorithm", "violation" or "database".
//
// Seen-state lives on the account (GET /api/auth/me → intros_seen, POST/DELETE
// /api/auth/intros/{id}) so a tour seen on the laptop never repeats on the phone.
// localStorage mirrors it: the fallback when auth is off, and a cache so an intro
// can't show twice while its save is in flight. An intro is marked seen as it
// opens, so closing the tab mid-way never brings it back.
import { api } from "./api.js";
import { state, isAssistant } from "./state.js";
import { showIntro, introOpen, coin, chip, crossfade, DEMOS } from "./intro.js";

// Every intro id (the e2e conftest reads this line to pre-mark them all as seen).
export const INTRO_IDS = ["welcome", "assistant-welcome", "first-squad", "first-setup", "first-rested", "first-review", "first-tinker", "first-live", "first-tournament"];
const TIPS_OFF = "__tips_off";
const LS_KEY = "gaffer_intros";

// ── Cards ────────────────────────────────────────────────────────────────────────
const bars = heights => `<div class="in-bars">${heights.map(h => `<span style="--h:${h}%"></span>`).join("")}</div>`;

const WELCOME = [
  {
    title: "Fair time, done for you",
    body: "Level plans who plays when, so every child gets the same time on the pitch.",
    why: "Children who sit on the bench stop enjoying it, and many stop playing. The FA recommends equal playing time at grassroots.",
    demo: bars([30, 85, 50, 95, 40, 70, 20, 60]),
  },
  {
    title: "Everyone tries positions",
    body: "Children rotate through the positions you've said they're happy in.",
    why: "FA guidance is to rotate positions, not pick by size. The tallest at eight may be average at fourteen.",
    demo: `<div class="in-rotate">
      <div class="in-rot-cols">
        <span><small>Q1</small>${chip("DEF", "def")}</span>
        <span><small>Q2</small>${chip("MID")}</span>
        <span><small>Q3</small>${chip("ATT", "fwd")}</span>
      </div>
      ${coin("Ava", "in-rot-coin")}
    </div>`,
  },
  {
    title: "Even line-ups",
    body: "Your skill ratings keep each stint evenly matched. Only you see them.",
    why: "No group of children gets stuck in the \"weaker\" side, so every stint is a fair game.",
    demo: `<div class="in-scales">
      <div class="in-beam"><span class="in-pan">Stint 1</span><span class="in-pan">Stint 2</span></div>
      <span class="in-pivot"></span>
    </div>`,
  },
  {
    title: "You're still the coach",
    body: "Change anything with Tinker. Level re-balances the rest.",
    why: "The plan is a starting point, not a rule. You know your players.",
    demo: DEMOS.tinkerSwap(true),
  },
];

const assistantWelcome = team => [
  {
    title: "You can see everything",
    body: `The plans, match reports and season stats for ${team}.`,
    why: "You'll know the plan before you get to the pitch.",
    demo: DEMOS.handover("Head", "You"),
  },
  {
    title: "Plan and run your own",
    body: "Create matches and tournaments of your own. The head coach can also hand one to you.",
    why: "If you're running the game, you can do it from your own phone. The head coach's plans stay theirs to change.",
    demo: `<div class="in-plan-card"><span>Sat · vs Rovers</span><span class="in-yours in-late">Yours</span></div>`,
  },
  {
    title: "One phone runs the match",
    body: "Tap \"Take control\" if you're the one running it today.",
    why: "One score, one clock, no confusion on the touchline.",
    demo: DEMOS.phones(
      crossfade("<small>Running</small>", "<small>Watching</small>"),
      crossfade("<small>Watching</small>", "<small class=\"in-on\">Running</small>"),
    ),
  },
];

const FIRST_USE = {
  "first-squad": {
    kicker: "Adding players",
    headOnly: true,
    slides: () => [
      {
        title: "Positions they're happy in",
        body: "Tick every position this player enjoys.",
        why: "The plan moves children around within those, so they learn the game without being put somewhere they hate.",
        demo: `<div class="in-picks">${chip("DEF", "def", "in-pick-on")}${chip("MID", "mid", "in-pick-on in-pick-2")}${chip("ATT", "fwd", "in-pick-dim")}</div>`,
      },
      {
        title: "Skill, 1 to 5",
        body: "A rough rating helps keep line-ups even.",
        why: "It's only used to balance stints, and only you can see it. Assistants never do.",
        demo: `<div class="in-stars"><span>★</span><span>★</span><span>★</span><span class="in-star-4">★</span><span class="in-star-off">★</span></div>`,
      },
      {
        title: "Keeper only?",
        body: "Only say yes if they never play outfield.",
        why: "A keeper-only child shares goal time so they play the same as everyone else.",
        demo: `<div class="wn-pitch in-goal">${crossfade(coin("Gus", "in-gk"), coin("Ava", "demo-coin-alt"))}</div>`,
      },
    ],
  },
  "first-setup": {
    kicker: "Your first plan",
    slides: () => [
      {
        title: "Pick your format",
        body: "5v5, 7v7 or 9v9, with the age groups shown.",
        why: "Matches the FA's formats, so the plan fits the league you play in.",
        demo: `<div class="in-sizes">
          <span>5v5<small>U8–U9</small></span><span class="in-size-on">7v7<small>U10–U11</small></span><span>9v9<small>U12–U13</small></span>
        </div>`,
      },
      {
        title: "Equal or start strong",
        body: "The slider sets how even playing time is.",
        why: "Equal is right most weeks. Slide it for a cup game if you want your strongest side on for longer.",
        demo: `<div class="in-slider"><span class="in-track"><span class="in-thumb"></span></span>
          <span class="in-slider-labels"><small>Equal</small><small>Start strong</small></span></div>`,
      },
      {
        title: "Next match remembers",
        body: "Your next match starts with these settings.",
        why: "Most teams play the same format every week, so it's fewer taps before kick-off.",
        demo: DEMOS.remembers("This match", "Next match"),
      },
    ],
  },
  "first-rested": {
    kicker: "Who's coming?",
    slides: () => [
      {
        title: "Rested or unavailable?",
        body: "Untick a player and say why.",
        why: "Resting is your choice, so they're owed time later. A child who's ill shouldn't count against anyone.",
        demo: DEMOS.rested,
      },
    ],
  },
  "first-review": {
    kicker: "Your first plan",
    slides: () => [
      {
        title: "Reading the plan",
        body: "Quarters run across, positions run down. Each quarter has a start and a halfway change.",
        why: "One glance shows who plays where, all match.",
        demo: `<div class="in-grid">
          <small></small><small>Q1</small><small>Q2</small><small>Q3</small><small>Q4</small>
          <small>GK</small><span>Gus</span><span>Gus</span><span>Ava</span><span>Ava</span>
          <small>DEF</small><span class="in-sweep">Ben</span><span class="in-sweep">Cal</span><span class="in-sweep">Ben</span><span class="in-sweep">Eve</span>
          <small>ATT</small><span>Dan</span><span>Eve</span><span>Cal</span><span>Dan</span>
        </div>`,
      },
      {
        title: "Notes, not errors",
        body: "Notes like \"out of position\" or \"long stint on the bench\" are suggestions.",
        why: "Sometimes a squad just can't be perfect. You decide if it matters today.",
        demo: `<div class="in-note"><span class="in-note-text">Ben · out of position in Q3</span><span class="in-tick in-late">✓</span></div>`,
      },
      {
        title: "Happy with it?",
        body: "View on pitch to see it as the kids will, or adjust it there.",
        why: "Seeing it on a pitch is how most coaches check a plan.",
        demo: crossfade(
          `<span class="in-mini-grid">${"<i></i>".repeat(12)}</span>`,
          `<span class="wn-pitch in-mini-pitch">${coin("Ben")}${coin("Cal")}${coin("Eve")}</span>`,
          "in-fold",
        ),
      },
    ],
  },
  "first-tinker": {
    kicker: "Tinker",
    slides: () => [
      {
        title: "Swap anyone",
        body: "Drag one player onto another, or tap a player to pick who goes there.",
        why: "You know who needs to be on together or kept apart.",
        demo: DEMOS.tinkerSwap(false),
      },
      {
        title: "The rest re-balances",
        body: "Stints you change are locked; Level re-plans the others to keep time fair.",
        why: "Your changes stick, and nobody loses out because of them.",
        demo: `<div class="in-stints">
          <span class="in-stint">1<b class="in-lock in-late">🔒</b></span>
          <span class="in-stint in-shuffle">2</span><span class="in-stint in-shuffle">3</span><span class="in-stint in-shuffle">4</span>
        </div>`,
      },
    ],
  },
  "first-live": {
    kicker: "Match day",
    slides: () => [
      {
        title: "Next only looks ahead",
        body: "Flick forward to see what's coming. \"Start period\" moves the game on.",
        why: "You can check the next change without losing your place.",
        demo: `<div class="in-col">
          <span class="in-live-row"><span class="in-live-tag">● Live · Q1</span><span class="in-next">Next ▶</span></span>
          <span class="in-preview in-late">Preview: Q1 halfway · <b>Back to live</b></span>
        </div>`,
      },
      {
        title: "Tap a player",
        body: "For a goal, or an injury. For an injury you pick who comes on.",
        why: "Recording as you go builds the match report, and an injury only changes that one child.",
        demo: `<div class="in-col">${coin("Ben", "in-tap")}
          <span class="in-menu in-late"><span>⚽ Goal</span><span>Injured</span></span></div>`,
      },
      {
        title: "One phone runs it",
        body: "Other coaches can watch live, and take over if needed.",
        why: "No arguments about whose phone has the right score.",
        demo: DEMOS.phones("<small class=\"in-on\">Running</small>", "<small>Watching</small>"),
      },
    ],
  },
  "first-tournament": {
    kicker: "Tournament day",
    slides: () => [
      {
        title: "Built for tournament days",
        body: "Several short matches, one squad, one plan for the whole day.",
        why: "Tournament days are hard to juggle: back-to-back games, not always a full squad, sometimes a borrowed player. Level keeps it fair across the lot.",
        demo: `<div class="in-games">${[1, 2, 3, 4].map(n => `<span class="in-game" style="--d:${(n - 1) * 0.25}s">Game ${n}</span>`).join("")}</div>`,
      },
      {
        title: "Fair across the day",
        body: "Time evens out across every match, not just one.",
        why: "A child who sat more in game one plays more in game two.",
        demo: `<div class="in-stacks">${[[10, 30, 20], [30, 10, 20], [20, 20, 20], [25, 15, 20]].map(col =>
          `<span>${col.map((h, i) => `<i style="--h:${h}px;--d:${i * 0.6}s"></i>`).join("")}</span>`).join("")}</div>`,
      },
      {
        title: "Guests for the day",
        body: "Add a player just for this tournament.",
        why: "Borrowed players are common on tournament days, and they don't clutter your squad.",
        demo: `<div class="wn-pitch">${coin("Ben")}${coin("Cal")}<span class="in-guest in-late">${coin("Zac", "demo-coin-alt")}<small>Guest</small></span></div>`,
      },
    ],
  },
};

// ── Seen-state ───────────────────────────────────────────────────────────────────
const accountOn = () => !!(state.account && state.account.auth_enabled);

function localSeen() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "{}") || {}; } catch (_) { return {}; }
}
function writeLocal(seen) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(seen)); } catch (_) { /* storage blocked */ }
}

export function introSeen(id) {
  return !!(state.account?.intros_seen?.[id] || localSeen()[id]);
}

export function markIntroSeen(id) {
  const at = new Date().toISOString();
  writeLocal({ ...localSeen(), [id]: at });
  if (state.account) state.account.intros_seen = { ...(state.account.intros_seen || {}), [id]: at };
  if (accountOn()) api.markIntro(id).catch(() => { /* cached locally; retried next time it's marked */ });
}

// "Show tips for new screens" (Settings). The account is the truth when signed in.
export function tipsOn() {
  if (accountOn()) return !state.account.intros_seen?.[TIPS_OFF];
  return !localSeen()[TIPS_OFF];
}
export async function setTipsOn(on) {
  if (!on) { markIntroSeen(TIPS_OFF); return; }
  const local = localSeen();
  delete local[TIPS_OFF];
  writeLocal(local);
  if (state.account?.intros_seen) {
    const { [TIPS_OFF]: _off, ...rest } = state.account.intros_seen;
    state.account.intros_seen = rest;
  }
  if (accountOn()) await api.unmarkIntro(TIPS_OFF);
}

// ── Showing them ─────────────────────────────────────────────────────────────────
// First-use intro for a screen: once, only if tips are on and nothing else is open.
// Resolves true when it was shown (after it closes).
export async function maybeIntro(id) {
  const intro = FIRST_USE[id];
  if (!intro || introSeen(id) || !tipsOn() || introOpen()) return false;
  if (intro.headOnly && isAssistant()) return false;
  markIntroSeen(id);
  const result = await showIntro(intro.slides(), { kicker: intro.kicker });
  return result !== "busy";
}

// The welcome tour for a brand-new head coach, shown over the team-name screen.
export async function maybeWelcomeTour() {
  if (introSeen("welcome") || introOpen()) return false;
  markIntroSeen("welcome");
  await showIntro(WELCOME, { kicker: "Welcome to Level", finalLabel: "Set up my team →" });
  return true;
}

export async function maybeAssistantWelcome() {
  if (introSeen("assistant-welcome") || introOpen()) return false;
  markIntroSeen("assistant-welcome");
  // Fetched here: on boot state.teamInfo still holds its placeholder name.
  const team = await api.getTeamInfo().then(i => i?.team_name).catch(() => "") || "your team";
  await showIntro(assistantWelcome(team), { kicker: `Welcome to ${team}`, finalLabel: "Let's go" });
  return true;
}

// Settings → "Replay the welcome tour" (the assistant welcome for an assistant).
export function replayWelcome() {
  if (isAssistant()) {
    const team = state.teamInfo?.team_name || "your team";
    return showIntro(assistantWelcome(team), { kicker: `Welcome to ${team}`, finalLabel: "Let's go" });
  }
  return showIntro(WELCOME, { kicker: "Welcome to Level" });
}

// For tests: every card has the parts the layout needs.
export const ALL_SLIDES = () => [
  ...WELCOME, ...assistantWelcome("Owls"),
  ...Object.values(FIRST_USE).flatMap(i => i.slides()),
];
