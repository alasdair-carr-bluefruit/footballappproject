"""Runtime configuration for multi-user auth (v1.1).

Values are read from the environment *lazily* (per call) rather than captured at
import time, so tests can toggle `AUTH_ENABLED` and secrets per-test via
`monkeypatch.setenv` without reimporting the app.

Auth is OFF by default: dev and the existing test suite keep today's single-squad
behaviour (one implicit default account). Production sets `AUTH_ENABLED=true`,
which requires the secrets below — `validate_config()` fails fast on boot if any
are missing.
"""
from __future__ import annotations

import os

# The signed session cookie's name (kept `gaffer_`-prefixed on purpose — see CLAUDE.md).
SESSION_COOKIE = "gaffer_session"

# Lifetimes.
SESSION_MAX_AGE_DAYS = 30
LOGIN_TOKEN_TTL_MINUTES = 15
INVITE_TTL_DAYS = 14


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def auth_enabled() -> bool:
    """Whether per-account auth + isolation is enforced. Off → single default squad."""
    return _truthy(os.getenv("AUTH_ENABLED"))


def secret_key() -> str:
    """Key for signing session cookies. A fixed dev key when auth is off; required in prod."""
    return os.getenv("SECRET_KEY") or "dev-insecure-secret-key-not-for-production"


def admin_key() -> str | None:
    """Shared secret gating the admin invite endpoints."""
    return os.getenv("ADMIN_KEY")


def frontend_origin() -> str:
    """Allowed CORS origin. Empty → same-origin only (the StaticFiles mount case)."""
    return os.getenv("FRONTEND_ORIGIN", "").strip()


def app_base_url() -> str:
    """Base URL used to build magic-link / invite links in emails."""
    return os.getenv("APP_BASE_URL", frontend_origin() or "http://localhost:8000").rstrip("/")


def resend_api_key() -> str | None:
    """Resend API key. Absent → magic links are logged (dev-stub) instead of emailed."""
    return os.getenv("RESEND_API_KEY")


def email_from() -> str:
    """The From address for transactional email (Resend test sender by default)."""
    return os.getenv("EMAIL_FROM", "Level <onboarding@resend.dev>")


def cookie_secure() -> bool:
    """Set the Secure flag on the session cookie.

    Explicit COOKIE_SECURE wins (set it false for http staging / tests); otherwise
    default to secure whenever auth is enabled (prod is always https).
    """
    override = os.getenv("COOKIE_SECURE")
    if override is not None:
        return _truthy(override)
    return auth_enabled()


def validate_config() -> None:
    """Fail fast on boot if auth is enabled but the required secrets are missing."""
    if not auth_enabled():
        return
    missing = [name for name, val in (("SECRET_KEY", os.getenv("SECRET_KEY")),
                                      ("ADMIN_KEY", os.getenv("ADMIN_KEY"))) if not val]
    if missing:
        raise RuntimeError(
            f"AUTH_ENABLED=true but required secret(s) unset: {', '.join(missing)}"
        )
