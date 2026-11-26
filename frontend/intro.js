// The full-screen intro carousel shared by What's new, the welcome tour and the
// first-use intros: one card per idea (title · what · Why · small looping
// animation), Skip top-right, Back / Next, "2 of 4". One overlay (#whats-new in
// index.html), so it all feels like one system.
//
//   showIntro(slides, { kicker, finalLabel }) → Promise<"done" | "skipped" | "busy">
//
// A slide is { title, body, why, where?, demo, beta? }. "busy" means another intro
// was already open, so nothing was shown (the caller can try again later).
// Demos are aria-hidden; under reduced motion each one shows its end state.

const el = id => document.getElementById(id);
let run = null;  // { slides, index, finalLabel, resolve, returnFocus }

export const introOpen = () => run !== null;

export function showIntro(slides, { kicker = "What's new", finalLabel = "Got it" } = {}) {
  if (run || !slides.length) return Promise.resolve("busy");
  return new Promise(resolve => {
    run = { slides, index: 0, finalLabel, resolve, returnFocus: document.activeElement };
    el("wn-kicker").textContent = kicker;
    el("wn-dots").innerHTML = slides.map(() => "<span></span>").join("");
    const many = slides.length > 1;
    el("wn-dots").hidden = !many;
    el("wn-count").hidden = !many;
    render();
    el("whats-new").hidden = false;
    el("btn-wn-next").focus();
  });
}

function render() {
  const { slides, index, finalLabel } = run;
  const s = slides[index];
  el("wn-demo").innerHTML = s.demo || "";  // fresh nodes → the animation restarts per card
  el("wn-title").innerHTML = s.title + (s.beta ? ' <span class="beta-tag">Beta</span>' : "");
  el("wn-body").textContent = s.body;
  el("wn-why").textContent = s.why;
  el("wn-where").textContent = s.where || "";
  el("wn-where").hidden = !s.where;
  el("wn-count").textContent = `${index + 1} of ${slides.length}`;
  [...el("wn-dots").children].forEach((d, i) => d.classList.toggle("active", i === index));
  el("btn-wn-back").hidden = index === 0;
  const last = index === slides.length - 1;
  el("btn-wn-next").textContent = last ? finalLabel : "Next";
  el("btn-wn-skip").hidden = last;  // the last card's own button is the way out
}

function close(result) {
  el("whats-new").hidden = true;
  const { resolve, returnFocus } = run;
  run = null;
  try { returnFocus?.focus?.(); } catch (_) { /* element gone */ }
  resolve(result);
}

el("btn-wn-next").addEventListener("click", () => {
  if (!run) return;
  if (run.index === run.slides.length - 1) { close("done"); return; }
  run.index += 1;
  render();
});
el("btn-wn-back").addEventListener("click", () => {
  if (run && run.index > 0) { run.index -= 1; render(); }
});
el("btn-wn-skip").addEventListener("click", () => { if (run) close("skipped"); });
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && run) close("skipped");
});

// ── Demo building blocks ────────────────────────────────────────────────────────
// Small helpers so a new card's animation is a line or two. Styles: style.css
// "Intro demos" (`.in-*`) plus the What's new ones (`.wn-*`, `.demo-*`).
export const coin = (label, cls = "") => `<span class="demo-coin ${cls}">${label}</span>`;
export const chip = (label, pos = "mid", cls = "") => `<span class="demo-chip pos-${pos} ${cls}">${label}</span>`;
// Two things in one place: the first fades out as the second fades in (end state = b).
export const crossfade = (a, b, cls = "") => `<span class="in-stack ${cls}"><span class="in-xa">${a}</span><span class="in-xb">${b}</span></span>`;

// A mini pitch with a formation on it: "the plan" without a word on it.
const FORMATION_ICON = `<svg class="wn-formation" viewBox="0 0 36 48" aria-hidden="true">
  <rect x="1" y="1" width="34" height="46" rx="3" class="wn-f-pitch"/>
  <line x1="1" y1="24" x2="35" y2="24" class="wn-f-line"/>
  <circle cx="18" cy="24" r="5" class="wn-f-line" fill="none"/>
  <circle cx="18" cy="42" r="2.6" class="wn-f-gk"/>
  <circle cx="11" cy="35" r="2.6"/><circle cx="25" cy="35" r="2.6"/>
  <circle cx="8" cy="23" r="2.6"/><circle cx="18" cy="21" r="2.6"/><circle cx="28" cy="23" r="2.6"/>
  <circle cx="18" cy="9" r="2.6"/>
</svg>`;

export const DEMOS = {
  rested: `<div class="wn-rested">
      <div class="wn-row">
        <span class="wn-check"></span><span class="wn-name">Ava</span>
        <span class="wn-chips"><span class="wn-chip">Unavailable</span><span class="wn-chip wn-chip-rested">Rested</span></span>
      </div>
      <span class="wn-owed">10′ owed next match</span>
    </div>`,
  remembers: (from = "Last match", to = "New match") => `<div class="wn-cards">
      <div class="wn-card"><small>${from}</small><span class="wn-pill">7v7 · 4 × 12.5′</span></div>
      <span class="wn-arrow">→</span>
      <div class="wn-card"><small>${to}</small><span class="wn-pill wn-pill-copy">7v7 · 4 × 12.5′</span></div>
    </div>`,
  // Coach and Assistant chips; a little team sheet (a 7v7 2-3-1) passes between them.
  handover: (from = "Coach", to = "Assistant") => `<div class="wn-coaches">
      <span class="wn-role">${from}</span>
      <span class="wn-track">${FORMATION_ICON}</span>
      <span class="wn-role wn-role-alt">${to}</span>
    </div>`,
  injury: `<div class="wn-pitch">
      ${coin("Ben")}
      <span class="wn-swap">${coin("Cal", "wn-hurt")}${coin("Eve", "wn-on demo-coin-alt")}</span>
      ${coin("Dan")}
    </div>`,
  // Two dashed (Tinker) coins swap places; optional "Sorted." toast after.
  tinkerSwap: (toast = false) => `<div class="in-col">
      <div class="wn-pitch in-tinker">${coin("Ben", "in-dashed in-swap-a")}${coin("Cal", "in-dashed in-swap-b")}</div>
      ${toast ? '<span class="in-toast in-late">Sorted. Plan updated.</span>' : ""}
    </div>`,
  phones: (a, b) => `<div class="in-phones">
      <div class="in-phone"><b>2–1</b>${a}</div>
      <div class="in-phone"><b>2–1</b>${b}</div>
    </div>`,
};
