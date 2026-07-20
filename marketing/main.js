// Level marketing site — early-access form + explainer video swap.

// The app (same project, app.keepthingslevel.com) hosts the endpoint that emails
// the founder. Override here if the app domain ever changes.
const API_BASE = "https://app.keepthingslevel.com";

// ── Early-access form ───────────────────────────────────────────────
const form = document.getElementById("ea-form");
if (form) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("ea-submit");
    const msg = document.getElementById("ea-msg");
    msg.className = "form-msg";
    msg.textContent = "";

    const payload = {
      email: document.getElementById("ea-email").value.trim(),
      name: document.getElementById("ea-name").value.trim(),
      message: document.getElementById("ea-message").value.trim(),
      website: document.getElementById("ea-website").value.trim(), // honeypot
    };
    if (!payload.email) return;

    btn.disabled = true;
    btn.textContent = "Sending…";
    try {
      const res = await fetch(API_BASE + "/api/early-access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("bad status " + res.status);
      msg.className = "form-msg ok";
      msg.textContent = "Thanks! You're on the list — I'll be in touch with an invite.";
      form.reset();
    } catch (_) {
      msg.className = "form-msg err";
      msg.innerHTML = 'Something went wrong sending that — please try again, or email <a href="mailto:hello@keepthingslevel.com">hello@keepthingslevel.com</a>.';
    } finally {
      btn.disabled = false;
      btn.textContent = "Request early access";
    }
  });
}
