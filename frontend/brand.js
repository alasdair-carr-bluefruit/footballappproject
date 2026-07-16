// Shared brand colours for <canvas> rendering.
//
// CSS custom properties (:root in style.css) can't be read from a canvas 2D
// context, so the share-card in pitch.js used to hardcode ~9 brand hexes,
// duplicating the CSS token values. This module is the single JS-side source
// of those values — keep it in sync with the matching :root tokens in
// style.css. Phase 3 will have both sides read from tokens.json.
export const BRAND = {
  pitchDeep: "#0E3A29", // --pitch-deep : share-card background
  pitch:     "#1A5C42", // --pitch      : top accent bar
  amber:     "#F5B544", // --amber      : "FULL TIME" pill
  slate:     "#1A1F1C", // --slate      : text on the amber pill
  chalk:     "#F2F4EE", // --chalk      : scoreline
};

// Chalk (off-white) at an arbitrary opacity — for canvas text tints.
export const chalkAlpha = (a) => `rgba(242, 244, 238, ${a})`;
