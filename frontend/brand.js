// Shared brand colours for <canvas> rendering.
//
// CSS custom properties (:root in style.css) can't be read from a canvas 2D
// context, so the share-card in pitch.js renders with these JS-side copies.
// Keep them in sync with the matching :root tokens in style.css — the share
// card is meant to mirror the on-screen Full Time card exactly.
export const BRAND = {
  pitchDeep: "#0B1210", // --pitch-deep : page bg + top of the card gradient
  pitch:     "#0A2619", // --pitch      : bottom of the card gradient
  matchday:  "#A4CC46", // --matchday   : Signal Lime — badge + scorer pills
  amber:     "#F5B544", // --amber
  slate:     "#1A1F1C", // --slate
  chalk:     "#F2F4EE", // --chalk      : primary text / scoreline
};

// Token colours at an arbitrary opacity — for canvas fills/tints.
export const chalkAlpha = (a) => `rgba(242, 244, 238, ${a})`;
export const matchdayAlpha = (a) => `rgba(164, 204, 70, ${a})`;

// Position band colours — mirrors the default (non-colourblind) --pos-* tokens
// in style.css so a shared plan image reads with the same colour language as the
// on-screen grid. `fg` is the text colour on that fill; MID's lime needs a dark
// foreground (same override as `.plan-cell.pos-mid` in style.css).
export const POS_COLORS = {
  GK:  { bg: "#3E8E97", fg: "#C4E6EA" },
  DEF: { bg: "#7E5FA8", fg: "#DED2EE" },
  MID: { bg: "#AEC93C", fg: "#223007" },
  FWD: { bg: "#C57A3E", fg: "#F4D6BB" },
};
