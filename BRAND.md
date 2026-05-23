# Gaffr — Brand Guidelines

> Fair play, made simple. The manager's app for grassroots football.

This is the canonical brand reference for the Gaffr app. Update this file when the brand changes — it's the source of truth that the design system (`tokens.json`) and the polished PDF are both derived from.

- **Logo & icon assets:** [`assets/brand/`](./assets/brand/)
- **Design tokens (JSON):** [`assets/brand/tokens.json`](./assets/brand/tokens.json)
- **PDF version (for sharing):** `docs/gaffr-brand-guidelines.pdf` *(optional — regenerate with the build script when this file changes)*

---

## 1. Essence

A "gaffer" is the manager. The trusted voice on the touchline. The one who makes sure every kid gets a fair go. Our brand should feel like that person — knowledgeable, warm, never pompous.

### Three words we lead with

| Word | Meaning |
|------|---------|
| **Fair** | Every player gets minutes. The product enforces it; the brand promises it. |
| **Fast** | Match plans in seconds, not Sunday-night spreadsheets. Built for the touchline. |
| **Grounded** | Grassroots, not Premier League. Muddy boots, volunteer coaches, real Saturdays. |

### Who we're for

Volunteer coaches at under-7 to under-16 level. Parents who said yes to running the team and now need a way to keep it fair when there are 13 kids and only 7 shirts. We're not building for academies or pro clubs — though they're welcome too.

### Who we are not

Not a tactics app. Not stats-heavy. Not a social network. Not "FIFA for dads." If a feature doesn't help a Sunday-morning coach make a fairer decision, it doesn't belong.

---

## 2. Name & wordmark

**The wordmark is `Gaffr`.** The dropped "e" gives a punchier app-icon presence, a more modern tech feel, and a distinctive visual identity. It works harder at small sizes than the full word would.

**In spoken and long-form written copy, "Gaffer" is fine and natural** — that's what people will say aloud, and it's the right word to use in App Store descriptions, marketing prose, and anywhere the full British football vocabulary helps. The asymmetry is deliberate: the wordmark is the brand, the spoken name is the meaning.

### Logo variants

| File | When to use |
|------|-------------|
| [`logo-gaffr-primary.svg`](./assets/brand/logo-gaffr-primary.svg) | Default. Pitch green on light backgrounds. |
| [`logo-gaffr-reversed.svg`](./assets/brand/logo-gaffr-reversed.svg) | Chalk wordmark with green dot, for dark backgrounds. |
| [`logo-gaffr-mono-light.svg`](./assets/brand/logo-gaffr-mono-light.svg) | Single-colour chalk version where green can't reproduce. |
| [`icon-app.svg`](./assets/brand/icon-app.svg) | App icon. Standalone "G" with centre-spot dot. |

### The dot

The green dot after the wordmark is the **centre spot of a football pitch**. It is the brand's signature device and doubles as the wordmark's full stop. It also stands alone as the icon glyph at small sizes.

### Do

- Capital G, lowercase rest: `Gaffr` (never `gaffr`, never `GAFFR`)
- Keep the dot in `#2EBE6B` (Match-day green) on all colour applications
- Spell "Gaffer" in full in body copy, voice-overs, and ad scripts where it reads naturally
- Maintain clear space equal to the cap-height of the "G" on all sides
- Minimum legible size: **60 px wide on screen, 18 mm wide in print**. Below this, use the icon glyph alone.

### Don't

- All-caps `GAFFR` — feels shouty and premiership
- Recolour the dot, drop it, or replace it with a period
- Italicise, outline, add gradients, or apply effects
- Place on busy photography without an overlay or solid panel
- Mix "Gaffr" and "Gaffer" within a single UI screen — pick one per context

---

## 3. Colour

| Token | Hex | Role |
|-------|-----|------|
| **Pitch** | `#1A5C42` | Primary brand colour. Backgrounds, large surfaces. |
| **Match-day** | `#2EBE6B` | Action, affirmation, CTAs, the centre-spot dot. |
| **Chalk** | `#F2F4EE` | Light surface, primary text on dark. |
| Pitch Deep | `#0E3A29` | Dark mode backgrounds, app icon background. |
| Trophy Amber | `#F5B544` | Accent only. Highlights, rewards, "coming soon" states. |
| Slate | `#1A1F1C` | Body text on light backgrounds. |

**Proportions:** roughly `60 / 25 / 10 / 5` — Pitch dominates, Chalk balances, Match-day signals action, Amber sparkles occasionally.

Programmatic values live in [`tokens.json`](./assets/brand/tokens.json) — that file is the source of truth for Tailwind config, theme files, etc. Don't hardcode hex values in component code; import from tokens.

### Accessibility

WCAG contrast ratios for the most common combinations:

| Foreground | Background | Ratio | Status |
|------------|------------|-------|--------|
| Chalk `#F2F4EE` | Pitch `#1A5C42` | 7.14 | AA normal, AAA large |
| Pitch `#1A5C42` | Chalk `#F2F4EE` | 7.14 | AA normal, AAA large |
| Slate `#1A1F1C` | Chalk `#F2F4EE` | 15.08 | AAA all sizes |
| Match-day `#2EBE6B` | Pitch `#1A5C42` | 3.28 | AA large only |
| Match-day `#2EBE6B` | Chalk `#F2F4EE` | 2.18 | **Fails AA — do not use for text** |
| Trophy Amber `#F5B544` | Pitch `#1A5C42` | 4.36 | AA normal, AAA large |

**Match-day green is a UI accent, not a text colour on light backgrounds.** For green text on Chalk, use Pitch. For green CTAs on Chalk, use Match-day as the *fill* with Pitch-Deep or Chalk as the *label* — the button label needs its own contrast against the green, not against the surrounding Chalk.

---

## 4. Typography

**One family: [Inter](https://rsms.me/inter/).** Open-source (SIL Open Font License), drawn for screens, and the weight range covers headlines and body copy without a second typeface. Inter's tabular figures are essential for the minutes-played displays — enable `font-variant-numeric: tabular-nums` on any element showing minutes, scores, or counts.

### Fallback stack

```css
font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
```

### Mobile UI scale

| Role | Size / line-height | Weight |
|------|---------------------|--------|
| Display | 32 / 36 | 800 |
| H1 — Screen titles | 24 / 28 | 700 |
| H2 — Section headers | 18 / 22 | 700 |
| Body — Default reading | 15 / 22 | 400 |
| Caption — Metadata, helper | 12 / 16 | 500 |

### Display & headline treatment

- Letter-spacing `-2.5%` on 800-weight display sizes
- Letter-spacing `-1.5%` on 700-weight headings
- Body and below: default tracking

---

## 5. Voice

Direct, warm, occasionally funny — never lecturing. We use British football vocabulary naturally (gaffer, sub, the lads / the team, minutes, full-time) but never force it. We don't shout. We don't say "leverage."

### Sounds like us

- "Right, who's on first?"
- "Everyone gets a fair go."
- "Sub Sam at the 20."
- "Saved you a Sunday-night spreadsheet."

### Doesn't sound like us

- "Unlock your team's potential."
- "AI-powered rotation optimisation."
- "Elevate your coaching journey."
- Anything with "synergy."

### Microcopy principles

1. **Short over clever.** "Add player" beats "Get your squad ready." A button is a button.
2. **Acknowledge effort.** When a coach saves a plan, say "Sorted." Not "Match plan saved successfully."
3. **Empty states have a voice.** "No subs yet — add your first when you're ready." Beats a blank screen.
4. **Errors are honest.** "Couldn't save — try again?" with a retry button. Not "Oops! Something went wrong."

### Taglines

- **Fair play, made simple.** *(recommended)*
- Every kid gets a game.
- The manager's app.
- Sunday morning, sorted.

---

## 6. In use

### App icon

The app icon uses the standalone `G` with the centre-spot dot. It works at every iOS / Android icon size from 1024 px down to the 48 px notification badge. See [`icon-app.svg`](./assets/brand/icon-app.svg).

### In the product

The brand lives in the moments coaches see most: pre-match, mid-match, post-match.

- **Pitch green** sets the stage — primary backgrounds, card surfaces
- **Match-day green** is for what's happening *now* and what to tap *next* — primary CTAs, active states, the substitution alert
- **Trophy amber** flags imbalance — "these two have played less, give them a run"
- **The centre-spot dot** from the logo recurs throughout the app as a marker for *current moment*, *current player*, *now*

---

## Changelog

| Version | Date | Notes |
|---------|------|-------|
| 1.0.0 | 2026-05-23 | Initial guidelines. Wordmark, palette, typography, voice. |
