// Whose plan is it? — the "Plan by Sam" chip on the fixtures / tournaments lists, the
// head coach's hand-over picker behind it, and the "Reviewed ✓" mark.
//
// A plan's owner is whoever may edit and run it besides the head coach: the assistant
// who created it, or one the head coach handed it to. Season matches and tournaments
// share everything here (`kind` picks the endpoints) so the two flows can't drift.
import { api } from "./api.js";
import { state, can } from "./state.js";
import { showToast } from "./toast.js";

const ENDPOINTS = {
  match:      { setOwner: (id, acc) => api.setMatchOwner(id, acc),      review: (id, on) => api.reviewMatch(id, on) },
  tournament: { setOwner: (id, acc) => api.setTournamentOwner(id, acc), review: (id, on) => api.reviewTournament(id, on) },
};

// The head coach's assistants on the active team (cached; [] for everyone else, and
// when auth is off). Reset on team switch (teams.js resetTeamCaches).
export async function ensureAssistants() {
  if (!can("manage_team") || !state.account?.auth_enabled) return [];
  if (!state.assistants) state.assistants = await api.getAssistants().catch(() => null);
  return state.assistants || [];
}

function canHandOver(kind, item) {
  if (!can("manage_team") || !(state.assistants || []).length) return false;
  return kind === "tournament" || item.status === "planned";
}

// Chip HTML for a list row. Everyone sees "Plan by Sam (✓)" on an assistant's plan;
// the head coach's chip is a button that opens the picker, and their own planned
// fixtures get a quiet "Hand over" chip when the team has assistants.
export function planOwnerChip(kind, item) {
  const owned = !!item.created_by_name;
  const handOver = canHandOver(kind, item);
  if (!owned && !handOver) return "";
  const who = item.created_by_me ? "you" : item.created_by_name;
  const el = document.createElement(handOver ? "button" : "span");
  el.className = "match-badge match-badge-author";
  if (handOver) {
    el.type = "button";
    el.classList.add("plan-owner-btn");
    el.title = "Choose who does this plan";
  }
  if (!owned) el.classList.add("plan-owner-unassigned");
  el.textContent = owned ? `Plan by ${who}${item.reviewed ? " ✓" : ""}` : "Hand over";
  return el.outerHTML;
}

// Wire a rendered row's chip (no-op when it isn't a button).
export function bindPlanOwnerChip(row, kind, item, onChange) {
  row.querySelector(".plan-owner-btn")?.addEventListener("click", e => {
    e.stopPropagation();  // the row itself opens the match
    openOwnerPicker(kind, item, onChange);
  });
}

function openOwnerPicker(kind, item, onChange) {
  const overlay = document.getElementById("plan-owner-overlay");
  const options = document.getElementById("plan-owner-options");
  const label = kind === "tournament" ? (item.name || "this tournament") : `vs ${item.opponent || "Unknown opponent"}`;
  document.getElementById("plan-owner-info").textContent =
    `${label} — the coach you pick can set up the plan, tinker with it and run the match${kind === "tournament" ? "es" : ""}. You always can too.`;
  options.innerHTML = "";

  const choose = async (accountId) => {
    overlay.hidden = true;
    try {
      await ENDPOINTS[kind].setOwner(item.id, accountId);
      onChange();
    } catch (err) {
      showToast((err && err.message) || "Couldn't hand over the plan.");
    }
  };
  const add = (text, accountId, current) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `btn btn-full ${current ? "btn-primary" : "btn-secondary"}`;
    btn.textContent = current ? `${text} ✓` : text;
    btn.dataset.account = accountId == null ? "" : String(accountId);
    btn.addEventListener("click", () => (current ? (overlay.hidden = true) : choose(accountId)));
    options.appendChild(btn);
  };
  const ownerId = item.created_by_name ? item.created_by_account_id : null;
  add("Me (head coach)", null, ownerId == null);
  (state.assistants || []).forEach(a => add(a.display_name || a.email, a.account_id, ownerId === a.account_id));
  overlay.hidden = false;
}

document.getElementById("btn-plan-owner-cancel").addEventListener("click", () => {
  document.getElementById("plan-owner-overlay").hidden = true;
});

// The strip above a plan on the review screen: whose plan it is and whether the head
// coach has reviewed it. The head coach gets the button; it is a mark, not a gate.
// `item` = { id, created_by_name, created_by_me, reviewed } (a match or a tournament).
export function renderReviewMark(kind, item) {
  const row = document.getElementById("review-mark");
  if (!item || !item.created_by_name) { row.hidden = true; return; }
  row.hidden = false;
  const text = document.getElementById("review-mark-text");
  const btn = document.getElementById("btn-review-mark");
  const who = item.created_by_me ? "you" : item.created_by_name;
  text.textContent = item.reviewed
    ? `Plan by ${who} · Reviewed ✓ by the head coach`
    : `Plan by ${who}${can("manage_team") ? "" : " · not reviewed yet"}`;
  btn.hidden = !can("manage_team");
  btn.textContent = item.reviewed ? "Undo" : "Mark reviewed ✓";
  btn.onclick = async () => {
    btn.disabled = true;
    try {
      const res = await ENDPOINTS[kind].review(item.id, !item.reviewed);
      item.reviewed = res.reviewed;
      renderReviewMark(kind, item);
      if (res.reviewed) showToast("Marked as reviewed.");
    } catch (err) {
      showToast((err && err.message) || "Couldn't save that.");
    } finally {
      btn.disabled = false;
    }
  };
}
