# Level — Brand Guidelines

> Keep things level. The rotation app for grassroots football.

Canonical brand reference for the **Level** app. This is the design source of
truth; the values here are **as-built** and mirror `frontend/style.css` `:root`
and `assets/brand/tokens.json`. When the brand changes, update all three
together.

---

## 1. Essence

**"Level" is what the product does and what it promises.** Every kid gets level
minutes. The maths is level. The plan is level. The coach doesn't have to keep
it level in their head — the app does.

A spirit level is the most instantly readable instrument ever made: one glance
and you know if things are balanced. That's the brand — a clear read at a glance.

### Three words we lead with

| Word | Meaning |
|---|---|
| **Balanced** | Every player gets their fair minutes. The maths is perfect, so the coach doesn't have to think about it. |
| **Reliable** | Built for the touchline. High contrast for glaring sun, chunky hit areas for cold hands, zero fragile UI. |
| **Direct** | No tech jargon, no corporate fluff. It does exactly what it says on the tin. |

### Who we're for
Volunteer coaches at U7–U16 — parents who stepped up to run the team and just
want the admin sorted in thirty seconds so they can watch the football.

### Who we are not
Not a tactics app. Not stats-heavy. Not a social network. If a feature doesn't
help a Sunday-morning coach make a fairer decision, it doesn't belong.

### Taglines
- **Primary:** *Keep things level.*
- **Marketing / App Store subtitle:** *Level with me.*

---

## 2. Name, wordmark & mark

The wordmark is **Level** in **Space Mono 700**, sentence case ("Level"). Never
all-caps — "LEVEL" reads as shouting, which is exactly what the product isn't.
In-app the wordmark is rendered as **live Space Mono text** (transparent,
recolours to context) rather than an image.

The **identity mark** is a **bubble centred between two horizontal lines** — a
spirit-level vial read three ways at once: a level with the bubble dead-centre,
the centre circle + touchlines of a pitch from above, and a dot resting on a
horizon. On the pitch mark the bubble's lower half is Signal Lime.

**Do not:** add football imagery (boots, whistles, full pitches); add tradesman
imagery (ruler ticks, measurement scales); or tilt the lines — they are always
horizontal.

Assets live in `assets/brand/` (`icon-app.svg` app icon, `LevelLinesTransparent.png`
wide lockup) and `frontend/` (`icon-app-192/512.png` PWA icons, `apple-touch-icon.png`).

---

## 3. Colour (as-built)

A softened broadcast aesthetic. Deep green surfaces reference the pitch; nothing
sits at full saturation. The nostalgia lives in the **typography**, not the colour.

| Token | Hex | Role |
|---|---|---|
| Studio Green | `#0A2619` | Primary background — pitch field + page base. |
| Deep Ink | `#0B1210` | Deep surface — header, bench, cards, toasts. |
| Signal Lime | `#A4CC46` | Primary action colour (CTAs, live, sub-in). Muted back from the original `#B8E62E` — it read too neon. Aim for **one** lime element per screen. |
| On-Accent | `#0A2619` | Text/icons **on** Signal Lime (lime is light — never white on it). |
| Chalk | `#F2F4EE` | Primary text / off-white; player-token fill. |
| Amber Phosphor | `#F5B544` | **Warnings only** (under-slotted players). Never a general accent. |
| Ghost Green | `#4E7E4A` | Lighter, lime-leaning pitch tint while Tinkering. |
| Provisional Chalk | `#E8D97A` | Dashed outline on movable tokens while Tinkering. |
| Danger | `#e74c3c` | Destructive / removal. Outside the core palette but functionally required. |
| Coach Blue | `#3E6DA8` | In-match advisory prompts. |

### Position palette (functional coding — not brand colour)
DEF/MID/FWD/GK on the pitch and plan grid. Deliberately clear of Signal Lime
(CTA) and Amber Phosphor (warning):

| Position | Fill | Foreground |
|---|---|---|
| GK | teal `#2FBFA8` | `#B6F0E6` |
| DEF | azure `#4F9BF0` | `#C4DEFB` |
| MID | violet `#A98CF0` | `#E0D6FB` |
| FWD | coral `#DB7B54` | `#F6C7B2` |

*Developer note: all colour values are defined once in `frontend/style.css`
`:root`; tints derive via `color-mix`. Do not hardcode hexes elsewhere. Canvas
(`<canvas>`) values live in `frontend/brand.js`.*

---

## 4. Typography — three fonts

Retro monospace for display/data, clean sans for helper text. This carries the
broadcast reference — not the colour.

1. **Space Mono** (`--font-display`) — headers, player initials, scores, data
   points. Tabular by design, so minutes/counters align without a workaround.
2. **VT323** (`--font-timer`) — the **live match timer only**. Ceefax /
   vidiprinter nostalgia at the moment it matters. Minimum 24px; below that it
   falls back to Space Mono.
3. **Inter** (`--font-body`) — button labels, settings, helper text.

---

## 5. Voice

Direct, warm, efficient. British grassroots vocabulary used naturally. We speak
like a calm assistant manager, not a mate down the pub.

**Sounds like us:** "Sorted. Plan updated." · "Still to level up: Sam, Alex." ·
"Tap a player to swap them out." · "Couldn't reach the server — check your
connection."

**Doesn't sound like us:** "Unlock your team's tactical synergy." · "Oops! An
error occurred." · "Let's get this party started!"

**Wordplay we own** (use sparingly): *Level with me* (onboarding), *Keep things
level* (the nudge when equal minutes are about to break), *Level up* (a player
earning back minutes).

---

## 6. Modes & states — the Tinker pivot

Two match-plan modes: **Locked** (default, the algorithm's plan) and
**Tinkering** (explicit edit). The button to enter is **Tinker**; to commit,
**Done** (Signal Lime). Tinkering is casual — no confirmation modals.

**The visual metaphor is modulation, not replacement.** Tinkering does not swap
the pitch for a notebook or whiteboard — it modulates it:

1. **Surface** — the pitch tints one step lighter, from Studio Green up to the
   lime-leaning **Ghost Green** `#4E7E4A`.
2. **Tokens** — movable player coins **invert** to a dark fill (`#0B1210`) with
   chalk text and a chunky **dashed Provisional-Chalk outline** (`#E8D97A`). A
   strong, unmistakable "edit mode" shift against the lightened pitch. GK /
   incoming coins keep their identity colour but still gain the dashed outline.
3. **The pill** — top-right, Signal-Lime fill with Studio-Green text:
   **TINKERING**, with a blinking terminal-block cursor (`_`) in Space Mono —
   the one small broadcast-nostalgia nod.

**Rejected** (do not reintroduce): a crumpled-paper / notebook texture,
`mix-blend-mode` overlays, SVG pen-wobble filters, or a decorative "hand-drawn"
font. These shipped in an earlier draft and were removed — the identity carries
through type and the pill, not surface trickery.

Tinker copy: exiting → **"Sorted. Plan updated."**
