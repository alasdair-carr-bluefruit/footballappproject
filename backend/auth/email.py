"""Magic-link email delivery, behind a tiny sender interface.

In dev / tests (no RESEND_API_KEY) the link is logged instead of sent, so the
whole auth flow is exercisable with no external dependency. In production the
same call posts to the Resend API via httpx. Swapping providers later is a change
to this one module.

The HTML template carries Level branding (Studio Green / Signal Lime, per
BRAND.md) plus a short "how to use / how to report issues" block, so the sign-in
email doubles as a light onboarding nudge.
"""
from __future__ import annotations

import logging

from backend.settings import app_base_url, early_access_to, email_from, resend_api_key

logger = logging.getLogger("level.auth.email")

# Brand palette (BRAND.md / assets/brand/tokens.json). Inlined because email
# clients strip <style>/external CSS — every colour must live on the element.
_STUDIO_GREEN = "#0A2619"
_DEEP_INK = "#0B1210"
_SIGNAL_LIME = "#A4CC46"
_ON_ACCENT = "#0A2619"
_CHALK = "#F2F4EE"
_MUTED = "#9DB3A6"
_HAIRLINE = "#1C3B2C"

_FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
)
# Space Mono isn't reliable in mail clients; fall back to a monospace stack for
# the wordmark so it still reads as the Level identity.
_MONO_STACK = "'Space Mono', 'SFMono-Regular', Menlo, Consolas, monospace"


def _html(link: str, *, is_invite: bool) -> str:
    """Build the branded HTML email body."""
    heading = "Set up your team on Level" if is_invite else "Your sign-in link"
    lead = (
        "You've been invited to Level — the fair-rotation planner for grassroots "
        "coaches. Tap the button below to create your team and get started."
        if is_invite
        else "Tap the button below to sign in to Level. It works on the device you "
        "opened this email on."
    )
    cta = "Set up my team" if is_invite else "Sign in to Level"

    # Absolute URL — mail clients don't resolve relative paths. The spirit-level
    # lines mark sits to the right of the live "Level" text.
    logo_src = f"{app_base_url()}/assets/brand/LevelLinesTransparent.png"

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:{_STUDIO_GREEN};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_STUDIO_GREEN};">
    <tr><td align="center" style="padding:32px 16px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:520px;background:{_DEEP_INK};border-radius:16px;overflow:hidden;border:1px solid {_HAIRLINE};">

        <!-- Wordmark: live "Level" text + spirit-level logo to its right -->
        <tr><td style="padding:28px 32px 12px 32px;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="vertical-align:middle;">
              <span style="font-family:{_MONO_STACK};font-weight:700;font-size:24px;letter-spacing:2px;color:{_SIGNAL_LIME};">Level</span>
            </td>
            <td style="vertical-align:middle;padding-left:14px;">
              <img src="{logo_src}" alt="" width="104"
                   style="display:block;width:104px;height:auto;border:0;outline:none;text-decoration:none;">
            </td>
          </tr></table>
        </td></tr>

        <!-- Heading + lead -->
        <tr><td style="padding:8px 32px 0 32px;">
          <h1 style="margin:0 0 12px 0;font-family:{_FONT_STACK};font-size:22px;line-height:1.3;color:{_CHALK};">
            {heading}
          </h1>
          <p style="margin:0;font-family:{_FONT_STACK};font-size:15px;line-height:1.6;color:{_MUTED};">
            {lead}
          </p>
        </td></tr>

        <!-- CTA -->
        <tr><td style="padding:24px 32px 8px 32px;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr><td
              style="border-radius:10px;background:{_SIGNAL_LIME};">
            <a href="{link}" target="_blank"
               style="display:inline-block;padding:14px 28px;font-family:{_FONT_STACK};font-size:16px;
                      font-weight:700;color:{_ON_ACCENT};text-decoration:none;border-radius:10px;">
              {cta}
            </a>
          </td></tr></table>
        </td></tr>

        <tr><td style="padding:4px 32px 0 32px;">
          <p style="margin:0;font-family:{_FONT_STACK};font-size:12px;line-height:1.6;color:{_MUTED};">
            This link expires shortly and can only be used once. If the button
            doesn't work, copy this URL into your browser:<br>
            <a href="{link}" style="color:{_SIGNAL_LIME};word-break:break-all;">{link}</a>
          </p>
        </td></tr>

        <!-- Divider -->
        <tr><td style="padding:24px 32px 0 32px;">
          <div style="border-top:1px solid {_HAIRLINE};"></div>
        </td></tr>

        <!-- How to use -->
        <tr><td style="padding:20px 32px 4px 32px;">
          <p style="margin:0 0 8px 0;font-family:{_MONO_STACK};font-size:13px;font-weight:700;
                    letter-spacing:1px;color:{_SIGNAL_LIME};">GETTING STARTED</p>
          <p style="margin:0;font-family:{_FONT_STACK};font-size:14px;line-height:1.7;color:{_CHALK};">
            1. Add your squad — names, positions and skill levels.<br>
            2. Set up a match and generate a fair rotation plan.<br>
            3. Review the plan, tinker if you like, then run match day.
          </p>
        </td></tr>

        <!-- Feedback -->
        <tr><td style="padding:16px 32px 4px 32px;">
          <p style="margin:0 0 8px 0;font-family:{_MONO_STACK};font-size:13px;font-weight:700;
                    letter-spacing:1px;color:{_SIGNAL_LIME};">FOUND A BUG OR HAVE AN IDEA?</p>
          <p style="margin:0;font-family:{_FONT_STACK};font-size:14px;line-height:1.7;color:{_CHALK};">
            Tap <strong>Report a bug</strong> in the app — bug reports and feature
            requests both land there, and they go straight to us. We read every one.
          </p>
        </td></tr>

        <!-- Footer -->
        <tr><td style="padding:24px 32px 28px 32px;">
          <p style="margin:0;font-family:{_FONT_STACK};font-size:12px;line-height:1.6;color:{_MUTED};">
            Keeping things level — fair playing time for every kid.<br>
            If you didn't request this email, you can safely ignore it.
          </p>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _text(link: str, *, is_invite: bool) -> str:
    """Plain-text fallback (improves deliverability and covers text-only clients)."""
    opener = (
        "You've been invited to Level — the fair-rotation planner for grassroots "
        "coaches. Open this link to create your team and get started:"
        if is_invite
        else "Open this link to sign in to Level:"
    )
    return (
        f"LEVEL\n\n{opener}\n\n{link}\n\n"
        "This link expires shortly and can only be used once.\n\n"
        "GETTING STARTED\n"
        "1. Add your squad — names, positions and skill levels.\n"
        "2. Set up a match and generate a fair rotation plan.\n"
        "3. Review the plan, tinker if you like, then run match day.\n\n"
        "FOUND A BUG OR HAVE AN IDEA?\n"
        "Tap 'Report a bug' in the app — bug reports and feature requests both "
        "land there, and they go straight to us.\n\n"
        "Keeping things level — fair playing time for every kid.\n"
        "If you didn't request this email, you can safely ignore it.\n"
    )


def send_login_link(to_email: str, link: str, *, is_invite: bool = False) -> None:
    """Email `to_email` a magic link. Dev-stub (log) when no RESEND_API_KEY is set."""
    subject = "Your Level invite" if is_invite else "Your Level sign-in link"
    key = resend_api_key()
    if not key:
        logger.info("MAGIC LINK (dev-stub, not emailed) for %s: %s", to_email, link)
        return

    try:
        import httpx

        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "from": email_from(),
                "to": [to_email],
                "subject": subject,
                "html": _html(link, is_invite=is_invite),
                "text": _text(link, is_invite=is_invite),
            },
            timeout=10.0,
        )
        resp.raise_for_status()
    except Exception:  # noqa: BLE001 — never leak send failures to the caller/UX path
        # Log and swallow: the endpoint always responds 200 (no account enumeration),
        # and a failed send simply means the coach can request another link.
        logger.exception("Failed to send login email to %s", to_email)


def send_email_change_link(to_email: str, link: str) -> None:
    """Email a confirm-email-change link to the NEW address.

    Dev-stub (log) when no RESEND_API_KEY is set. Errors are swallowed like the
    login path — a failed send just means the coach requests another link.
    """
    key = resend_api_key()
    if not key:
        logger.info("EMAIL CHANGE LINK (dev-stub, not emailed) for %s: %s", to_email, link)
        return
    subject = "Confirm your new Level email"
    html = (
        f'<div style="font-family:{_FONT_STACK};font-size:15px;line-height:1.6;'
        f'color:{_STUDIO_GREEN};max-width:520px;">'
        f'<p style="font-family:{_MONO_STACK};font-weight:700;letter-spacing:2px;'
        f'color:{_STUDIO_GREEN};">LEVEL</p>'
        "<h2>Confirm your new email</h2>"
        "<p>You asked to change the email address on your Level account to this one. "
        "Tap below to confirm the change — until you do, your old address stays active.</p>"
        f'<p><a href="{link}" target="_blank" '
        f'style="display:inline-block;padding:12px 24px;background:{_SIGNAL_LIME};'
        f'color:{_ON_ACCENT};font-weight:700;text-decoration:none;border-radius:10px;">'
        "Confirm new email</a></p>"
        "<p style=\"font-size:12px;color:#5a6b60;\">This link expires shortly and can only be "
        f'used once. If the button doesn\'t work, paste this URL:<br>'
        f'<a href="{link}" style="color:{_STUDIO_GREEN};word-break:break-all;">{link}</a></p>'
        "<p style=\"font-size:12px;color:#5a6b60;\">If you didn't request this, you can safely "
        "ignore this email — nothing will change.</p></div>"
    )
    text = (
        "LEVEL\n\nConfirm your new email address for Level.\n\n"
        f"Open this link to confirm the change:\n{link}\n\n"
        "This link expires shortly and can only be used once.\n"
        "If you didn't request this, you can safely ignore this email.\n"
    )
    try:
        import httpx

        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "from": email_from(),
                "to": [to_email],
                "subject": subject,
                "html": html,
                "text": text,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
    except Exception:  # noqa: BLE001 — don't leak send failures into the UX path
        logger.exception("Failed to send email-change link to %s", to_email)


def send_email_changed_notice(
    old_email: str, *, new_email: str, team_name: str, reclaim_link: str
) -> None:
    """Warn the OLD address that the account's email was changed, with a link to
    reclaim the squad (revert + sign out everywhere) if it wasn't the owner.

    Dev-stub (log) when no RESEND_API_KEY. Errors swallowed like the login path.
    """
    key = resend_api_key()
    if not key:
        logger.info(
            "EMAIL-CHANGED NOTICE (dev-stub) to %s (new=%s, team=%s): %s",
            old_email, new_email, team_name, reclaim_link,
        )
        return
    subject = f"Your Level email for {team_name} was changed"
    html = (
        f'<div style="font-family:{_FONT_STACK};font-size:15px;line-height:1.6;'
        f'color:{_STUDIO_GREEN};max-width:520px;">'
        f'<p style="font-family:{_MONO_STACK};font-weight:700;letter-spacing:2px;'
        f'color:{_STUDIO_GREEN};">LEVEL</p>'
        "<h2>Your email address was changed</h2>"
        f"<p>The email registered to <strong>{team_name}</strong> on Level was changed "
        f"to <strong>{new_email}</strong>. If that was you, no action is needed.</p>"
        "<p><strong>If this wasn't you</strong>, click below to reclaim your squad — this "
        "restores this email address and signs out every device.</p>"
        f'<p><a href="{reclaim_link}" target="_blank" '
        f'style="display:inline-block;padding:12px 24px;background:{_SIGNAL_LIME};'
        f'color:{_ON_ACCENT};font-weight:700;text-decoration:none;border-radius:10px;">'
        "Reclaim my squad</a></p>"
        "<p style=\"font-size:12px;color:#5a6b60;\">If the button doesn't work, paste this URL:"
        f'<br><a href="{reclaim_link}" style="color:{_STUDIO_GREEN};word-break:break-all;">'
        f"{reclaim_link}</a></p></div>"
    )
    text = (
        f"LEVEL\n\nThe email registered to {team_name} on Level was changed to "
        f"{new_email}.\n\nIf that was you, no action is needed.\n\n"
        "If this WASN'T you, open this link to reclaim your squad — it restores this "
        f"email address and signs out every device:\n{reclaim_link}\n"
    )
    try:
        import httpx

        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "from": email_from(),
                "to": [old_email],
                "subject": subject,
                "html": html,
                "text": text,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
    except Exception:  # noqa: BLE001 — don't leak send failures into the UX path
        logger.exception("Failed to send email-changed notice to %s", old_email)


def send_early_access_email(submitter_email: str, name: str, message: str) -> None:
    """Notify the founder of an early-access request from the marketing site.

    Unlike the login path this does NOT swallow errors — a lost waitlist signup is
    worse than a retry prompt, so the caller surfaces failures to the form. Reply-to
    is set to the submitter so a reply goes straight back to them.
    """
    subject = f"Early access request — {submitter_email}"
    text = (
        "New early-access request from the Level marketing site.\n\n"
        f"Email:   {submitter_email}\n"
        f"Name:    {name or '—'}\n\n"
        f"Message:\n{message or '—'}\n"
    )
    html = (
        f'<div style="font-family:{_FONT_STACK};font-size:15px;line-height:1.6;color:{_STUDIO_GREEN};">'
        f'<h2 style="font-family:{_MONO_STACK};color:{_STUDIO_GREEN};">New early-access request</h2>'
        f"<p><strong>Email:</strong> {submitter_email}<br>"
        f"<strong>Name:</strong> {name or '—'}</p>"
        f"<p><strong>Message:</strong><br>{(message or '—')}</p>"
        "</div>"
    )
    key = resend_api_key()
    if not key:
        logger.info(
            "EARLY ACCESS (dev-stub, not emailed): %s <%s> — %s", name, submitter_email, message
        )
        return
    import httpx

    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "from": email_from(),
            "to": [early_access_to()],
            "subject": subject,
            "html": html,
            "text": text,
            "reply_to": submitter_email,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
