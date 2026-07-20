"""Public router (`/api`) — unauthenticated endpoints the marketing site calls.

Currently just the early-access waitlist form on the apex site, which emails the
founder. No auth, no DB writes; a honeypot field drops obvious bots.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.auth.email import send_early_access_email

router = APIRouter()


class EarlyAccessBody(BaseModel):
    email: str
    name: str = ""
    message: str = ""
    website: str = ""  # honeypot — hidden in the form; bots fill it, humans don't


@router.post("/early-access")
def early_access(body: EarlyAccessBody) -> dict:
    """Email the founder an early-access request from the marketing site."""
    if body.website.strip():  # honeypot tripped → silently accept and drop
        return {"ok": True}
    email = body.email.strip()
    if "@" not in email or "." not in email.split("@")[-1] or len(email) > 254:
        raise HTTPException(status_code=422, detail="Please enter a valid email address.")
    try:
        send_early_access_email(email, body.name.strip()[:100], body.message.strip()[:2000])
    except Exception as e:  # noqa: BLE001 — surface send failures so the form can retry
        raise HTTPException(
            status_code=502, detail="Couldn't send that just now — please try again."
        ) from e
    return {"ok": True}
