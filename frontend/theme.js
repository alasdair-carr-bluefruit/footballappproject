// Colour theme (T2.3). A `data-theme` attribute on <html> swaps in an alternate
// set of CSS custom properties defined in style.css (`:root[data-theme="…"]`).
// The default (Level) palette needs no attribute. Currently one alternate:
// "colourblind" — an Okabe–Ito-based, colourblind-safe palette. The choice is
// persisted per-device under the gaffer_ localStorage prefix (see CLAUDE.md).
//
// A tiny inline snippet in index.html's <head> applies the saved theme before
// first paint (no flash); this module is the runtime source of truth and wires
// the Settings control.

const THEME_KEY = "gaffer_theme";
export const THEMES = ["default", "colourblind"];

export function getTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  return THEMES.includes(stored) ? stored : "default";
}

export function applyTheme(theme) {
  const t = THEMES.includes(theme) ? theme : "default";
  if (t === "default") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", t);
  }
  try { localStorage.setItem(THEME_KEY, t); } catch { /* private mode — theme just won't persist */ }
}

// Reflect the persisted choice onto the Settings radio group and keep it in sync.
export function syncThemeControl() {
  const radios = document.querySelectorAll('input[name="theme-choice"]');
  const current = getTheme();
  radios.forEach(r => { r.checked = r.value === current; });
}

function wire() {
  const radios = document.querySelectorAll('input[name="theme-choice"]');
  radios.forEach(r => {
    r.addEventListener("change", () => {
      if (r.checked) applyTheme(r.value);
    });
  });
  syncThemeControl();
}

// Re-assert on load (the head snippet already set it pre-paint) and wire the control.
applyTheme(getTheme());

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", wire);
} else {
  wire();
}
