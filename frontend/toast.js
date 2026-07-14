// Toast notifications (C.7).
//
// `showToast` renders a single transient message at the bottom of the screen,
// optionally with an action button (e.g. Retry). `withSaveToast` wraps a write
// call so a failed save surfaces a retryable toast instead of vanishing
// silently (the old `.catch(() => {})` pattern lost the change with no signal).

let _current = null;

function dismiss(toast) {
  toast.remove();
  if (_current === toast) _current = null;
}

export function showToast(message, { actionLabel, action, duration } = {}) {
  // Only one toast at a time — a new one replaces the old.
  if (_current) dismiss(_current);

  const toast = document.createElement("div");
  toast.className = "toast";

  const text = document.createElement("span");
  text.className = "toast-text";
  text.textContent = message;
  toast.appendChild(text);

  if (action) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toast-action";
    btn.textContent = actionLabel || "Retry";
    btn.addEventListener("click", () => {
      dismiss(toast);
      action();
    });
    toast.appendChild(btn);
  }

  document.body.appendChild(toast);
  _current = toast;
  // Retryable toasts linger longer so the coach can act on them.
  setTimeout(() => dismiss(toast), duration ?? (action ? 8000 : 4000));
  return toast;
}

export async function withSaveToast(fn, message = "Couldn't save — check your connection.") {
  try {
    return await fn();
  } catch {
    showToast(message, { actionLabel: "Retry", action: () => withSaveToast(fn, message) });
    return null;
  }
}
