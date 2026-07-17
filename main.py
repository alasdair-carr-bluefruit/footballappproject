from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routers import (
    admin_router,
    auth_router,
    feedback_router,
    match_router,
    squad_router,
    tournament_router,
)
from backend.auth.session import set_session_cookie, verify_session
from backend.db.database import create_db_and_tables
from backend.settings import SESSION_COOKIE, auth_enabled, frontend_origin, validate_config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    validate_config()  # fail fast if AUTH_ENABLED but secrets are missing
    create_db_and_tables()
    yield


app = FastAPI(title="Level", lifespan=lifespan)

# CORS: with auth on, cookies require a concrete allowed origin + credentials
# (a wildcard origin is invalid alongside credentials). The frontend is normally
# served same-origin via the StaticFiles mount below, so an explicit origin is
# only needed for a split deploy — set FRONTEND_ORIGIN then.
_origin = frontend_origin()
if auth_enabled():
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_origin] if _origin else [],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.middleware("http")
async def rolling_session(request, call_next):
    """Sliding-session refresh: on any authenticated request, re-issue the session
    cookie with a fresh timestamp, so the 30-day expiry counts from last activity
    (an active coach never has to re-request a magic link). Skipped when the
    response already touches the cookie (login sets a new one, logout clears it)."""
    response = await call_next(request)
    if not auth_enabled():
        return response
    already_set = any(
        h.split("=", 1)[0].strip().lower() == SESSION_COOKIE.lower()
        for h in response.headers.getlist("set-cookie")
    )
    if not already_set:
        account_id = verify_session(request.cookies.get(SESSION_COOKIE))
        if account_id is not None:
            set_session_cookie(response, account_id)
    return response


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(squad_router, prefix="/api/squad", tags=["squad"])
app.include_router(match_router, prefix="/api/matches", tags=["matches"])
app.include_router(tournament_router, prefix="/api/tournaments", tags=["tournaments"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])

app.mount("/assets", StaticFiles(directory="assets"), name="assets")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
