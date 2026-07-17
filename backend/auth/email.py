"""Magic-link email delivery, behind a tiny sender interface.

In dev / tests (no RESEND_API_KEY) the link is logged instead of sent, so the
whole auth flow is exercisable with no external dependency. In production the
same call posts to the Resend API via httpx. Swapping providers later is a change
to this one module.
"""
from __future__ import annotations

import logging

from backend.settings import email_from, resend_api_key

logger = logging.getLogger("level.auth.email")


def send_login_link(to_email: str, link: str, *, is_invite: bool = False) -> None:
    """Email `to_email` a magic link. Dev-stub (log) when no RESEND_API_KEY is set."""
    subject = "Your Level invite" if is_invite else "Your Level sign-in link"
    verb = "set up your team" if is_invite else "sign in"
    key = resend_api_key()
    if not key:
        logger.info("MAGIC LINK (dev-stub, not emailed) for %s: %s", to_email, link)
        return

    html = (
        f"<p>Tap the link below to {verb} on Level:</p>"
        f'<p><a href="{link}">{link}</a></p>'
        f"<p>This link expires shortly and can only be used once.</p>"
    )
    try:
        import httpx

        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {key}"},
            json={"from": email_from(), "to": [to_email], "subject": subject, "html": html},
            timeout=10.0,
        )
        resp.raise_for_status()
    except Exception:  # noqa: BLE001 — never leak send failures to the caller/UX path
        # Log and swallow: the endpoint always responds 200 (no account enumeration),
        # and a failed send simply means the coach can request another link.
        logger.exception("Failed to send login email to %s", to_email)
