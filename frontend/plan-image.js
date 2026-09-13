// ── Share the plan (canvas image) ────────────────────────────────────────────
// Coaches already do this by hand: they screenshot the "Review the plan" table
// and paste it into the co-coaches' WhatsApp group before the match. This turns
// that into a button — the same grid (positions down, periods across), rendered
// as a PNG that's legible off-phone, with full player names instead of the
// cramped mobile tokens, plus the slots-per-player totals underneath.
//
// One entry point (#btn-review-share) covers both flows: a season match, a
// single tournament match, and the tournament "Review all plans" page, which
// shares every match's grid stacked in one image. The plans to draw come from
// `state.reviewPlans`, which pitch.js/tournament.js set when they render the
// screen — so this module never has to know which flow it's in.
import { state, displayPos } from "./state.js";
import { planGridData, positionRows } from "./pitch.js";
import { BRAND, chalkAlpha, matchdayAlpha, POS_COLORS } from "./brand.js";
import { showToast } from "./toast.js";

const FONT_BODY = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
const FONT_MONO = "'Space Mono', ui-monospace, SFMono-Regular, Menlo, monospace";

// Layout constants (logical px; the canvas is drawn at 2× for HiDPI).
const SCALE = 2;
const MARGIN = 18;        // backdrop around the card
const PAD = 20;           // card padding
const LABEL_W = 58;       // position-label column
const COL_MIN = 74;       // per-slot column
const COL_MAX = 104;
const MIN_CONTENT_W = 460; // a 2-slot tournament grid mustn't squeeze the header
const ROW_H = 30;
const BENCH_LINE_H = 13;  // one benched name per line inside a bench cell
const CELL_GAP = 4;
const HEAD_H = 22;

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(x, y, w, h, rr); return; }
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function loadLogo(src) {
  if (!src) return Promise.resolve(null);
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = src;
  });
}

function truncate(ctx, text, maxW) {
  if (ctx.measureText(text).width <= maxW) return text;
  let t = text;
  while (t.length > 1 && ctx.measureText(t + "…").width > maxW) t = t.slice(0, -1);
  return t + "…";
}

// The label drawn in a cell: the player's name, prefixed with their shirt number
// when they have one (the co-coach reading this on a phone recognises both).
function cellLabel(name) {
  const num = state.shirtNumbers[name];
  return num != null ? `${num} ${name}` : name;
}

// Per-block geometry: rows are the formation's positions (+GK), columns its
// slots. Each block is one match, so a tournament stacks several.
function blockRows(md) {
  return positionRows(md.match.formation || "1-2-1");
}

// Names on the bench for slot `i`. Falls back to deriving them from the squad
// when a slot carries no bench list (older stored plans).
function benchNames(md, i) {
  const slot = md.slots[i];
  if (!slot) return [];
  if (slot.bench?.length) return slot.bench.map(p => cellLabel(p.name));
  const onPitch = new Set(Object.values(slot.lineup).map(p => p.name));
  return planGridData(md).players
    .filter(p => !onPitch.has(p.name))
    .map(p => cellLabel(p.name));
}

// Tall enough for the fullest bench in the match (never shorter than a position
// row), so every column lines up.
function benchRowHeight(md) {
  const most = Math.max(0, ...md.slots.map((_, i) => benchNames(md, i).length));
  if (!most) return 0;
  return Math.max(ROW_H, most * BENCH_LINE_H + 10);
}

// ── Drawing ──────────────────────────────────────────────────────────────────

// One match block: title, the position × slot grid, then a slots-per-player
// strip. Returns the y position after the block.
function drawBlock(ctx, md, { title, x, y, colW, cols, contentW }) {
  const rows = blockRows(md);
  const { slotLabels, players, perSlot } = planGridData(md);

  // Block title (e.g. "Match 2 · vs Rovers"). Omitted for a single-match share,
  // where the card header already says which match this is.
  if (title) {
    ctx.font = "700 14px " + FONT_BODY;
    ctx.fillStyle = BRAND.chalk;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(title, x, y + 9);
    y += 26;
  }

  // Header row — period labels (Q1a, Q1b, …).
  ctx.font = "700 11px " + FONT_MONO;
  ctx.fillStyle = chalkAlpha(0.55);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  slotLabels.forEach((label, i) => {
    ctx.fillText(label, x + LABEL_W + i * colW + (colW - CELL_GAP) / 2, y + HEAD_H / 2);
  });
  y += HEAD_H;

  // One row per position: a dim row label, then the player filling that position
  // in each slot, tinted by position band.
  rows.forEach(({ key, band }) => {
    const colors = POS_COLORS[band] || POS_COLORS.DEF;
    ctx.font = "700 11px " + FONT_BODY;
    ctx.fillStyle = colors.bg;
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(displayPos(key), x, y + ROW_H / 2);

    for (let i = 0; i < cols; i++) {
      const cx = x + LABEL_W + i * colW;
      const cw = colW - CELL_GAP;
      const p = md.slots[i]?.lineup[key];
      if (!p) {
        ctx.fillStyle = chalkAlpha(0.05);
        roundRect(ctx, cx, y + 2, cw, ROW_H - 4, 6);
        ctx.fill();
        continue;
      }
      ctx.fillStyle = colors.bg;
      roundRect(ctx, cx, y + 2, cw, ROW_H - 4, 6);
      ctx.fill();
      ctx.fillStyle = colors.fg;
      ctx.font = "600 12px " + FONT_BODY;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(truncate(ctx, cellLabel(p.name), cw - 8), cx + cw / 2, y + ROW_H / 2 + 0.5);
    }
    y += ROW_H;
  });

  // Bench row — who's off in each period. The on-screen grid leaves this to the
  // pitch view, but a team sheet in a group chat has to answer "when am I on?"
  // without anyone opening the app.
  const benchH = benchRowHeight(md);
  if (benchH) {
    ctx.font = "700 11px " + FONT_BODY;
    ctx.fillStyle = chalkAlpha(0.45);
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText("BENCH", x, y + benchH / 2);
    for (let i = 0; i < cols; i++) {
      const cx = x + LABEL_W + i * colW;
      const cw = colW - CELL_GAP;
      ctx.fillStyle = chalkAlpha(0.05);
      roundRect(ctx, cx, y + 2, cw, benchH - 4, 6);
      ctx.fill();
      const names = benchNames(md, i);
      ctx.font = "500 11px " + FONT_BODY;
      ctx.fillStyle = chalkAlpha(0.65);
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      let ty = y + benchH / 2 - ((names.length - 1) * BENCH_LINE_H) / 2;
      names.forEach(n => {
        ctx.fillText(truncate(ctx, n, cw - 8), cx + cw / 2, ty);
        ty += BENCH_LINE_H;
      });
    }
    y += benchH;
  }

  // Slots-per-player strip — the fairness read-out, same numbers as on screen.
  y += 12;
  ctx.font = "700 10px " + FONT_BODY;
  ctx.fillStyle = chalkAlpha(0.45);
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  if ("letterSpacing" in ctx) ctx.letterSpacing = "0.6px";
  ctx.fillText("SLOTS PER PLAYER", x, y + 6);
  if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";
  y += 18;

  const counts = players
    .map(p => ({ name: p.name, count: perSlot[p.name].filter(Boolean).length }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  const chipH = 22, chipGap = 6, chipPad = 10;
  ctx.font = "600 12px " + FONT_BODY;
  let cx = x;
  counts.forEach(c => {
    const label = `${c.name} ${c.count}`;
    const w = ctx.measureText(label).width + chipPad * 2;
    if (cx > x && cx + w > x + contentW) { cx = x; y += chipH + chipGap; }
    ctx.fillStyle = chalkAlpha(0.07);
    roundRect(ctx, cx, y, w, chipH, chipH / 2);
    ctx.fill();
    ctx.fillStyle = chalkAlpha(0.8);
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, cx + w / 2, y + chipH / 2 + 0.5);
    cx += w + chipGap;
  });
  return y + chipH;
}

// Height of one block, measured without drawing (so the canvas can be sized up
// front). Mirrors drawBlock — keep the two in step.
function measureBlock(meas, md, { title, cols, contentW }) {
  let h = title ? 26 : 0;
  h += HEAD_H + blockRows(md).length * ROW_H + benchRowHeight(md);
  h += 12 + 18; // strip title

  const { players, perSlot } = planGridData(md);
  meas.font = "600 12px " + FONT_BODY;
  const chipH = 22, chipGap = 6, chipPad = 10;
  let lineW = 0, lines = 1;
  players.forEach(p => {
    const w = meas.measureText(`${p.name} ${perSlot[p.name].filter(Boolean).length}`).width + chipPad * 2;
    const add = lineW ? chipGap + w : w;
    if (lineW && lineW + add > contentW) { lines += 1; lineW = w; } else { lineW += add; }
  });
  return h + lines * chipH + (lines - 1) * chipGap;
}

// Builds the shareable PNG for `blocks` ([{ md, title }]). `heading` is the team
// name row; `subheading` the match/tournament line under it.
async function buildPlanBlob(blocks, { heading, subheading }) {
  if (document.fonts?.ready) { try { await document.fonts.ready; } catch (_) { /* draw anyway */ } }

  // Column width is driven by the widest match in the set so stacked grids line
  // up, and clamped so a 2-slot tournament match doesn't stretch to a billboard.
  const cols = Math.max(...blocks.map(b => b.md.slots.length));
  const colW = Math.max(COL_MIN, Math.min(COL_MAX, Math.round(760 / cols)));
  const gridW = LABEL_W + cols * colW - CELL_GAP;
  const contentW = Math.max(gridW, MIN_CONTENT_W);
  const cardW = contentW + PAD * 2;
  const W = cardW + MARGIN * 2;

  const meas = document.createElement("canvas").getContext("2d");
  const headerH = 54;
  const footerH = 26;
  const blockGap = 24;
  const blockHs = blocks.map(b => measureBlock(meas, b.md, { title: b.title, cols, contentW }));
  const cardH = PAD + headerH + blockHs.reduce((a, h) => a + h, 0)
    + blockGap * (blocks.length - 1) + 18 + footerH + PAD;
  const H = cardH + MARGIN * 2;

  const canvas = document.createElement("canvas");
  canvas.width = W * SCALE;
  canvas.height = H * SCALE;
  const ctx = canvas.getContext("2d");
  ctx.scale(SCALE, SCALE);

  // Backdrop + card (same dark gradient as the Full Time share card).
  ctx.fillStyle = BRAND.pitchDeep;
  ctx.fillRect(0, 0, W, H);
  const grad = ctx.createLinearGradient(MARGIN, MARGIN, MARGIN + cardW, MARGIN + cardH);
  grad.addColorStop(0, BRAND.pitchDeep);
  grad.addColorStop(1, BRAND.pitch);
  ctx.save();
  ctx.shadowColor = "rgba(0,0,0,0.4)";
  ctx.shadowBlur = 32;
  ctx.shadowOffsetY = 8;
  ctx.fillStyle = grad;
  roundRect(ctx, MARGIN, MARGIN, cardW, cardH, 18);
  ctx.fill();
  ctx.restore();

  const x = MARGIN + PAD;
  let y = MARGIN + PAD;

  // Header: badge (crest or team initials), team name, match line, and a
  // Signal-Lime "TEAM SHEET" pill on the right.
  const logoImg = await loadLogo(state.teamInfo.team_logo);
  const logoR = 18;
  if (logoImg) {
    ctx.save();
    ctx.beginPath();
    ctx.arc(x + logoR, y + logoR, logoR, 0, Math.PI * 2);
    ctx.clip();
    ctx.drawImage(logoImg, x, y, logoR * 2, logoR * 2);
    ctx.restore();
  } else {
    ctx.fillStyle = chalkAlpha(0.1);
    ctx.beginPath();
    ctx.arc(x + logoR, y + logoR, logoR, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = BRAND.chalk;
    ctx.font = "700 13px " + FONT_BODY;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText((heading || "Team").slice(0, 2).toUpperCase(), x + logoR, y + logoR);
  }

  const badgeLabel = blocks.length > 1 ? "TEAM SHEETS" : "TEAM SHEET";
  ctx.font = "700 10px " + FONT_BODY;
  if ("letterSpacing" in ctx) ctx.letterSpacing = "1.2px";
  const badgeW = ctx.measureText(badgeLabel).width + 22;
  const badgeX = x + contentW - badgeW;
  ctx.fillStyle = matchdayAlpha(0.15);
  roundRect(ctx, badgeX, y + 4, badgeW, 20, 10);
  ctx.fill();
  ctx.fillStyle = BRAND.matchday;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(badgeLabel, badgeX + badgeW / 2, y + 14.5);
  if ("letterSpacing" in ctx) ctx.letterSpacing = "0px";

  const textX = x + logoR * 2 + 12;
  const textW = badgeX - textX - 12;
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.font = "700 16px " + FONT_MONO;
  ctx.fillStyle = BRAND.chalk;
  ctx.fillText(truncate(ctx, heading || "My Team", textW), textX, y + 11);
  ctx.font = "400 12px " + FONT_BODY;
  ctx.fillStyle = chalkAlpha(0.6);
  ctx.fillText(truncate(ctx, subheading || "", textW), textX, y + 29);
  y += headerH;

  blocks.forEach((b, i) => {
    y = drawBlock(ctx, b.md, { title: b.title, x, y, colW, cols, contentW });
    if (i < blocks.length - 1) y += blockGap;
  });

  // Footer — quiet attribution, doubles as the "where do I get this?" prompt for
  // whichever co-coach in the group hasn't seen the app.
  y += 18;
  ctx.font = "400 11px " + FONT_BODY;
  ctx.fillStyle = chalkAlpha(0.35);
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText("Made with Level — keepthingslevel.com", x, y + footerH / 2);

  return new Promise(resolve => canvas.toBlob(resolve, "image/png"));
}

function downloadBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// ── Share button ─────────────────────────────────────────────────────────────
document.getElementById("btn-review-share").addEventListener("click", async () => {
  const share = state.reviewShare;
  const blocks = (share?.blocks || []).filter(b => b.md?.slots?.length);
  if (!blocks.length) { showToast("Nothing to share yet — generate a plan first."); return; }

  const btn = document.getElementById("btn-review-share");
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Building…";
  let blob;
  try {
    blob = await buildPlanBlob(blocks, share);
  } catch {
    blob = null;
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
  if (!blob) { showToast("Couldn't build the plan image."); return; }

  const filename = share.filename || "team-sheet.png";
  const file = new File([blob], filename, { type: "image/png" });
  const title = share.shareTitle || "Team sheet";
  // Native share sheet WITH the image (that's the WhatsApp path on a phone);
  // desktop browsers that can't share files fall back to a download so the
  // coach always ends up with the picture.
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title, text: title });
      return;
    } catch (err) {
      if (err && err.name === "AbortError") return;
    }
  }
  downloadBlob(blob, filename);
  showToast("Team sheet saved — ready to share.");
});

export { buildPlanBlob };
