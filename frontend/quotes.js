// Generating-plan loading overlay (shown while the server builds a rotation —
// 5–8s on Railway, longer for a whole tournament). Displays "Generating game
// plan…" plus a random quote from a legendary manager, rotating every few
// seconds so a long wait still feels alive.
//
// NB: attributions are the widely-circulated popular ones — worth an eyeball if
// any matter to you; football quotes are notoriously paraphrased.

// Tone: effort, development, learning from mistakes, teamwork, enjoyment and
// grassroots community — never winning at all costs.
const QUOTES = [
  { text: "Football is not a matter of life and death. It's much more important than that.", who: "Bill Shankly" },
  { text: "Everybody working for the same goal, and everybody sharing in the rewards — that's the game I love.", who: "Bill Shankly" },
  { text: "Hard work will always overcome natural talent when natural talent doesn't work hard enough.", who: "Sir Alex Ferguson" },
  { text: "If they're good enough, they're old enough.", who: "Sir Matt Busby" },
  { text: "Football is nothing without the people who play it and watch it.", who: "Sir Matt Busby" },
  { text: "Playing football is very simple, but playing simple football is the hardest thing there is.", who: "Johan Cruyff" },
  { text: "Every disadvantage has its advantage.", who: "Johan Cruyff" },
  { text: "You'll learn more from a game you lost than from a game you won.", who: "Johan Cruyff" },
  { text: "The hardest and most important thing in football is to never stop wanting to improve.", who: "Arsène Wenger" },
  { text: "Failure teaches you more than success — it keeps you humble and hungry to get better.", who: "Arsène Wenger" },
  { text: "What is a club? It's the noise, the passion, the feeling of belonging.", who: "Sir Bobby Robson" },
  { text: "Football is the most important of the least important things in life.", who: "Arrigo Sacchi" },
  { text: "Football is a game you play with your brain.", who: "Rinus Michels" },
  { text: "Give young players a happy place to express themselves and they'll surprise you.", who: "Carlo Ancelotti" },
  { text: "We can achieve far more together than we ever could alone.", who: "Jürgen Klopp" },
  { text: "Confidence and enjoyment come first — the football follows.", who: "Jürgen Klopp" },
  { text: "The best teams are a family: they work, they make mistakes, and they grow together.", who: "Luis Enrique" },
  { text: "A club should give every child the chance to feel they belong.", who: "Jock Stein" },
  { text: "Good times become good memories, but bad times make good lessons.", who: "Uncle Iroh, the Dragon of the West" },
];

// Easter egg: a rare comedy "gaffer" who occasionally shows up instead of a real
// quote (~1 in 12). Kept obviously fictional so it reads as a joke, never a real
// misattribution. TODO(ali): swap in the Gaffer Oscar / Five Guys line you want.
const EASTER_EGGS = [
  { text: "Just get it in the mixer and let the big lad chase it — football's a simple game, lads.", who: "Gaffer Oscar (allegedly)" },
];
const EASTER_EGG_CHANCE = 1 / 12;

let quoteTimer = null;

function pickQuote() {
  const textEl = document.getElementById("generating-quote-text");
  const whoEl = document.getElementById("generating-quote-author");
  if (!textEl || !whoEl) return;
  const pool = (EASTER_EGGS.length && Math.random() < EASTER_EGG_CHANCE) ? EASTER_EGGS : QUOTES;
  const q = pool[Math.floor(Math.random() * pool.length)];
  textEl.textContent = "“" + q.text + "”";
  whoEl.textContent = "— " + q.who;
}

export function showGenerating(title = "Generating game plan…") {
  const overlay = document.getElementById("generating-overlay");
  if (!overlay) return;
  const titleEl = document.getElementById("generating-title");
  if (titleEl) titleEl.textContent = title;
  pickQuote();
  overlay.hidden = false;
  clearInterval(quoteTimer);
  quoteTimer = setInterval(pickQuote, 4000);  // rotate the quote on a long wait
}

export function hideGenerating() {
  const overlay = document.getElementById("generating-overlay");
  if (overlay) overlay.hidden = true;
  clearInterval(quoteTimer);
  quoteTimer = null;
}
