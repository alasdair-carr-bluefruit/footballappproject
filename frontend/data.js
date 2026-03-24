// Hardcoded rotation plan — generated from the algorithm for the real squad.
// Replace with API call in v0.5.

export const MATCH = {
  date: "24 Mar 2026",
  opponent: "Rovers FC",
};

// slot_index 0–7: 0=Q1H1, 1=Q1H2, 2=Q2H1, 3=Q2H2, 4=Q3H1, 5=Q3H2, 6=Q4H1, 7=Q4H2
export const SLOTS = [
  // Q1 H1
  { gk: "Kai", def: "Oscar", mid1: "Eli", mid2: "Jackson", fwd: "Eden",
    bench: ["Rowan", "Jago", "Kobe", "Jude", "Wesley"] },
  // Q1 H2
  { gk: "Kai", def: "Jago", mid1: "Wesley", mid2: "Eli", fwd: "Oscar",
    bench: ["Rowan", "Kobe", "Eden", "Jude", "Jackson"] },
  // Q2 H1
  { gk: "Rowan", def: "Jago", mid1: "Jude", mid2: "Kobe", fwd: "Jackson",
    bench: ["Kai", "Eli", "Eden", "Oscar", "Wesley"] },
  // Q2 H2
  { gk: "Rowan", def: "Eden", mid1: "Kobe", mid2: "Jude", fwd: "Eli",
    bench: ["Kai", "Jago", "Jackson", "Oscar", "Wesley"] },
  // Q3 H1
  { gk: "Kai", def: "Oscar", mid1: "Kobe", mid2: "Wesley", fwd: "Eden",
    bench: ["Rowan", "Jago", "Eli", "Jude", "Jackson"] },
  // Q3 H2
  { gk: "Kai", def: "Jago", mid1: "Kobe", mid2: "Jude", fwd: "Eden",
    bench: ["Rowan", "Eli", "Oscar", "Wesley", "Jackson"] },
  // Q4 H1
  { gk: "Wesley", def: "Jago", mid1: "Jackson", mid2: "Jude", fwd: "Rowan",
    bench: ["Kai", "Eli", "Kobe", "Eden", "Oscar"] },
  // Q4 H2
  { gk: "Wesley", def: "Oscar", mid1: "Jackson", mid2: "Eli", fwd: "Rowan",
    bench: ["Kai", "Jago", "Kobe", "Eden", "Jude"] },
];

// Player metadata (used for display badges)
export const PLAYERS = {
  Kai:     { gkSpecialist: true },
  Rowan:   { gkPreferred: true },
  Kobe:    { defRestricted: true },
  Wesley:  { gkPreferred: true },
  Jago:    {},
  Eli:     {},
  Eden:    {},
  Jude:    {},
  Jackson: {},
  Oscar:   {},
};
