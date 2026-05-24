# Gaffer — Brand Guidelines

> Fair play, made simple. The manager's app for grassroots football.

This is the canonical brand reference for the Gaffer app. Update this file when the brand changes — it's the source of truth that the design system (`tokens.json`) and the polished PDF are both derived from.

- **Logo & icon assets:** [`assets/brand/`](./assets/brand/)
- **Design tokens (JSON):** [`assets/brand/tokens.json`](./assets/brand/tokens.json)
- **PDF version (for sharing):** `docs/gaffer-brand-guidelines.pdf` *(optional — regenerate with the build script when this file changes)*

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

**The wordmark is `Gaffer`** — written in full, capital G, lowercase rest. The full word carries the British grassroots tone the brand is built on; it's a piece of football vocabulary that does heavy lifting for free and reads naturally aloud.

### Logo variants

| File | When to use |
|------|-------------|
| [`logo-gaffer-primary.svg`](./assets/brand/logo-gaffer-primary.svg) | Default. Pitch green on light backgrounds. |
| [`logo-gaffer-reversed.svg`](./assets/brand/logo-gaffer-reversed.svg) | Chalk wordmark with green dot, for dark backgrounds. |
| [`logo-gaffer-mono-light.svg`](./assets/brand/logo-gaffer-mono-light.svg) | Single-colour chalk version where green can't reproduce. |
| [`icon-app.svg`](./assets/brand/icon-app.svg) | App icon. Standalone "G" with centre-spot dot. |

### The dot

The green dot after the wordmark is the **centre spot of a football pitch**. It is the brand's signature device and doubles as the wordmark's full stop. It also stands alone as the icon glyph at small sizes.

### Do

- Capital G, lowercase rest: `Gaffer` (never `gaffer`, never `GAFFER` as a logo treatment)
- Keep the dot in `#2EBE6B` (Match-day green) on all colour applications
- Maintain clear space equal to the cap-height of the "G" on all sides
- Minimum legible size: **60 px wide on screen, 18 mm wide in print**. Below this, use the icon glyph alone.

### Don't

- All-caps `GAFFER` as a logo — feels shouty and premiership
- Recolour the dot, drop it, or replace it with a period
- Italicise, outline, add gradients, or apply effects
- Place on busy photography without an overlay or solid panel
- Abbreviate to "Gaffr" in product UI — the full word is the brand

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

## 7. Modes & states

The product has two primary modes for the match plan: **Locked** (the default, the committed plan) and **Tinkering** (an explicit edit state). The mode distinction is brand-critical — coaches need to feel safe experimenting without worrying they've broken the auto-generated rotation.

### Naming

- The button that enters edit mode is labelled **`Tinker`** (verb, imperative).
- The mode itself is **`Tinkering`** (gerund, shown as the live state).
- The button that exits and commits is **`Done`** (not "Save", not "Apply" — coaches aren't filing a tax return).
- The button that exits and discards is **`Discard changes`** (only shown if changes were actually made).

"Tinker" is doing real work here. It communicates *low-stakes, no-harm experimentation* — which is exactly the emotional frame coaches need when they're about to override an auto-balanced rotation. Do not replace it with "Edit", "Adjust", "Modify", or any other generic term. The word is the brand.

### The metaphor

Tinkering mode should feel like **the gaffer pulling out a tactics notebook on the touchline and sketching changes in pen**. Not Excalidraw, not Figma. A real coach's notebook: paper texture over the pitch, hand-drawn pen strokes around movable elements, ink-style annotations.

This metaphor is doing two jobs at once:
1. **Communicating "draft / uncommitted"** — paper and pen are inherently provisional
2. **Reinforcing the grassroots brand** — this is what a real volunteer coach does on a Saturday morning

### The visual rule

> *Tinkering mode keeps the pitch underneath. We overlay paper texture and switch all movable elements from solid UI strokes to hand-drawn pen strokes. Typography stays in Inter — only shapes become sketchy.*

### Implementation recipe

Apply these changes when Tinkering mode is active. **All other UI** (typography, layout, copy, button positions, position labels like "CF" / "LM") **stays identical to Locked mode.** The button that says `Tinker` in Locked mode simply becomes `Done` in the same physical slot — don't move it.

#### 1. The paper texture (the surface)

The pitch background gets a **real crumpled-paper photograph** layered over it with a multiply blend. The white paper multiplies down to the pitch green, so creases and highlights remain visible but tinted to "green paper". This is not a procedural effect — procedural noise looks like noise, not paper. Use the asset.

**Asset:** [`assets/brand/texture-paper.jpg`](./assets/brand/texture-paper.jpg) (1920×1080, ~68 KB)

**CSS recipe:**

```css
.tinkering-pitch {
  background-color: #1A5C42;            /* Pitch green base */
  background-image: url('/assets/brand/texture-paper.jpg');
  background-size: cover;               /* one sheet, do not tile */
  background-position: center;
  background-blend-mode: multiply;      /* this is what makes white paper become green paper */
}
```

**Critical:** use `background-blend-mode`, **not** `mix-blend-mode` on a separate overlay div. The blend has to happen between the background-image and background-color on the same element so the green tints through the white paper.

**Why `background-size: cover` not `repeat`:** The pitch on a phone is small enough that a single 1920×1080 sheet covers it without needing to tile. Tiling produces visible seams which break the "one piece of paper" illusion.

#### 2. Hand-drawn pen strokes on movable elements (the marks)

Player tokens, position slots, and **anything draggable on the pitch** swap their solid stroke for a hand-drawn ink stroke in Trophy Amber.

**Bench chips do NOT wobble.** Bench items in Tinkering mode keep their crisp Locked-mode style — the amber outline on incoming subs is already enough signal that something is changing. Wobbling the bench would over-apply the metaphor and read as noisy.

The "hand-drawn" feel comes from a solid amber stroke + an SVG displacement filter:

| Property | Value | Why |
|----------|-------|-----|
| `stroke` | `#F5B544` (Trophy Amber) | Reads as pen ink against paper |
| `stroke-width` | `2.5` px | A touch heavier than UI default — pen, not pencil |
| `stroke-linecap` | `round` | Pen tips are round, not square |
| `stroke-linejoin` | `round` | Matches pen behaviour at corners |
| `stroke-dasharray` | `0` (solid, **not dashed**) | Real pen strokes are continuous — dashed reads as "border", solid reads as "drawn" |
| SVG filter | `url(#pen-wobble)` | Adds visible hand-drawn jitter |

**The wobble filter (paste into the page once, reuse via `url(#pen-wobble)`):**

```html
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <defs>
    <filter id="pen-wobble">
      <feTurbulence type="fractalNoise" baseFrequency="0.025" numOctaves="2" seed="5" result="noise"/>
      <feDisplacementMap in="SourceGraphic" in2="noise" scale="3.2"/>
    </filter>
  </defs>
</svg>
```

**`scale="3.2"` is the locked value** for player-token-sized elements (~50–70 px diameter). At this scale the wobble is clearly visible — circles aren't mathematically perfect, they look drawn. Lower than 2 is too subtle to read against paper; higher than 4 starts looking shaky/broken.

**Important:** the pen stroke *replaces* the existing token outline — it doesn't get added on top. A double ring (solid grey + amber wobble) reads as a UI bug.

#### 3. The "Tinkering" pill (the mode indicator)

Top-right of the header, persistent throughout the mode. Match-day green fill (`#2EBE6B`), Pitch-Deep label (`#0E3A29`), Inter 800 with all-caps "TINKERING" text. The pill outline gets the `pen-wobble` filter — the label text stays crisp Inter.

The pill is **status only**. It is not a button. It does not contain a Done action.

#### 4. The Done button (below the subs)

The button that reads `Tinker` in Locked mode reads `Done` in Tinkering mode. **Same slot, below the bench, full-width.** Match-day green fill, Pitch-Deep label, Inter 800.

Tapping `Done` exits Tinkering and commits. To discard, use a secondary affordance (back arrow / cancel link) — don't add a competing button next to Done.

#### 5. Entry & exit transitions

- **Entering Tinkering** (`Tinker` tapped): paper texture fades in over 200 ms; movable element strokes morph from solid white/grey to amber pen over 250 ms; button label crossfades `Tinker` → `Done`. No flash, no bounce.
- **Exiting via `Done`**: reverse, 200 ms. Add a brief Match-day green ripple from the button to confirm commit.
- **Exiting via discard**: same fade, but the player positions visibly snap back to their pre-Tinkering arrangement first (300 ms), so the user *sees* their changes being undone.

### What "sketchy" does **not** mean here

- ❌ Procedural / SVG-filter paper. We tried it. It looks like noise, not paper. Use the JPG asset.
- ❌ Wobbly Inter or a handwritten font. Inter stays. Only **shapes** are hand-drawn.
- ❌ Dashed strokes. Dashed reads as "border style", not "pen". Use solid + wobble filter.
- ❌ Wobbling the bench. Bench stays crisp — only on-pitch elements get pen strokes.
- ❌ Floating action buttons on the pitch. The Done button lives below the bench, in the existing Tinker slot.
- ❌ A Done button inside the Tinkering pill. The pill is a status indicator, not an action.
- ❌ Crayon, marker, or watercolour effects. We're a pen on paper, not an art class.
- ❌ Full background swap to chalk/cream. The pitch metaphor stays. Paper is on top of the pitch, not instead of it.
- ❌ Sketchy treatment outside Tinkering mode. Locked mode is crisp. The contrast is the whole point.

### Tone of voice in Tinkering mode

The voice stays the same — direct, warm, never panicky. Helper text should reinforce the low-stakes framing:

- Empty Tinkering hint: **"Drag a player to swap them in. Nothing's saved until you tap Done."**
- After exiting Tinkering: **"Sorted. Plan updated."**
- If discarding: **"No worries — back to the original plan."**

Avoid alarm language like "Unsaved changes!" or "You'll lose your work." Tinkering is *meant* to be casual.

### Worked example — a movable player token

```jsx
// Once per page, somewhere in the root:
<svg width="0" height="0" style={{ position: 'absolute' }} aria-hidden="true">
  <defs>
    <filter id="pen-wobble">
      <feTurbulence type="fractalNoise" baseFrequency="0.025" numOctaves="2" seed="5" result="noise"/>
      <feDisplacementMap in="SourceGraphic" in2="noise" scale="3.2"/>
    </filter>
  </defs>
</svg>

// Then for each player token, when isTinkering is true:
<svg width="68" height="68" viewBox="0 0 68 68">
  {/* white fill stays the same as Locked mode */}
  <circle cx="34" cy="34" r="28" fill="#FFFFFF" />
  {/* hand-drawn amber ring REPLACES the normal token outline */}
  <circle
    cx="34" cy="34" r="28"
    fill="none"
    stroke="#F5B544"
    strokeWidth="2.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    filter="url(#pen-wobble)"
  />
  {/* initials stay crisp Inter — NO filter on the text */}
  <text
    x="34" y="40"
    textAnchor="middle"
    fontFamily="Inter"
    fontWeight="800"
    fontSize="15"
    fill="#0E3A29"
  >JAC</text>
</svg>
```

The pitch container itself:

```jsx
<div
  className="tinkering-pitch"
  style={{
    backgroundColor: '#1A5C42',
    backgroundImage: "url('/assets/brand/texture-paper.jpg')",
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    backgroundBlendMode: 'multiply',
  }}
>
  {/* pitch lines, player tokens, etc. */}
</div>
```

Position slots, the Tinkering pill, and any other on-pitch movable element follow the same recipe: keep the fill and the typography from Locked mode, replace the outline with an amber stroke + wobble filter. The bench, header, and footer button strip stay crisp — exactly as they look in Locked mode.

---

## Changelog

| Version | Date | Notes |
|---------|------|-------|
| 1.4.0 | 2026-05-23 | Locked Tinkering visual spec after iteration. Paper texture is now a real JPG asset (`texture-paper.jpg`) applied via `background-blend-mode: multiply`, not procedural. Wobble scale bumped to 3.2. Bench stays crisp — no wobble off-pitch. Done button stays in its existing slot below the bench (not floating, not in the pill). Tinkering pill is status-only, not a button. |
| 1.3.0 | 2026-05-23 | Rewrote §7 Tinkering. Switched from "tinted pitch + dashed amber outlines" to "paper texture overlay + hand-drawn pen strokes" (wobble filter, solid amber). Added implementation recipe with SVG filters and a worked React example. |
| 1.2.0 | 2026-05-23 | Added §7 Modes & states. Defines `Tinker` / `Tinkering` naming, visual rule (tinted pitch + dashed amber strokes), and rejected alternatives. |
| 1.1.0 | 2026-05-23 | Reverted name to `Gaffer` (from `Gaffr`). All wordmark SVGs and copy updated. |
| 1.0.0 | 2026-05-23 | Initial guidelines. Wordmark, palette, typography, voice. |
