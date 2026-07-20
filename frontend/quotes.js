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
  // — Positive legends —
  { text: "Hard work, humility and togetherness will take you further than talent alone.", who: "Eddie Howe" },
  { text: "Give players belief, and they'll give you everything back.", who: "Eddie Howe" },
  { text: "Enjoy the journey — the good days and the hard ones both make the team.", who: "Eddie Howe" },
  { text: "You can't play your best every week, but you can give your best every week.", who: "Kevin Keegan" },
  { text: "I know what's around the corner — I just don't always know where the corner is.", who: "Kevin Keegan" },
  { text: "Magic is sometimes very close to nothing at all — the tiniest details decide it.", who: "Zinedine Zidane" },
  { text: "Be proud of where you come from — it's what puts the fire in your football.", who: "Zinedine Zidane" },
  { text: "First, make sure they're enjoying it. Everything good in football follows from that.", who: "Gordon Strachan" },
  { text: "The best teams laugh together, work together, and lose together — then go again.", who: "Gordon Strachan" },
  { text: "The players play the game — my job is just to help them love it.", who: "Pep Guardiola" },
  { text: "If a player isn't enjoying his football, he's in the wrong game.", who: "Brian Clough" },
  { text: "The effort and the way you play matter far more than the result.", who: "Marcelo Bielsa" },
  { text: "The game is about glory — doing things in style, with a flourish.", who: "Danny Blanchflower" },
  { text: "Practice doesn't make perfect — it makes permanent. So enjoy the practice.", who: "Sir Bobby Robson" },
  { text: "The strength of the team is each player. The strength of each player is the team.", who: "Phil Jackson" },
  // — Funny, in the best possible taste —
  { text: "I couldn't be more chuffed if I were a badger at the start of mating season.", who: "Ian Holloway" },
  { text: "Every dog has its day — and today is 'woof' day. Today, I just want to bark.", who: "Ian Holloway" },
  { text: "You can't buy team spirit — and it's worth more than all the money in the world.", who: "Neil Warnock" },
  { text: "Football keeps you young — even while it's ageing you by the minute.", who: "Neil Warnock" },
  { text: "I wouldn't say I was the best manager in the business — but I was in the top one.", who: "Brian Clough" },
  { text: "‘Gordon, can we have a quick word?’ ‘Velocity.’", who: "Gordon Strachan" },
  { text: "Good times become good memories, but bad times make good lessons.", who: "Uncle Iroh, the Dragon of the West" },
];

// Easter egg: a rare comedy line that occasionally shows up instead of a real
// quote (~1 in 12). Fictional characters only, so it reads as a joke — never a
// real misattribution.
const EASTER_EGGS = [
  { text: "WHISTLE!!!!", who: "Roy Kent" },
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
