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
    public_router,
    squad_router,
    teams_router,
    tournament_router,
)
from backend.auth.session import session_epoch_from, set_session_cookie, verify_session
from backend.db.database import create_db_and_tables
from backend.settings import (
    SESSION_COOKIE,
    auth_enabled,
    frontend_origin,
    marketing_origins,
    validate_config,
)


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
    # The app origin (credentialed) plus the apex marketing origins, which POST the
    # public early-access form cross-origin (no cookies, but still need an allow-list).
    allowed = ([_origin] if _origin else []) + marketing_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed,
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
        cookie = request.cookies.get(SESSION_COOKIE)
        account_id = verify_session(cookie)
        if account_id is not None:
            # Preserve the token's epoch so the sliding refresh never downgrades a
            # post-reclaim session back to epoch 0 (which deps would then reject).
            set_session_cookie(response, account_id, session_epoch_from(cookie) or 0)
    return response


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(squad_router, prefix="/api/squad", tags=["squad"])
app.include_router(teams_router, prefix="/api/teams", tags=["teams"])
app.include_router(match_router, prefix="/api/matches", tags=["matches"])
app.include_router(tournament_router, prefix="/api/tournaments", tags=["tournaments"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])
app.include_router(public_router, prefix="/api", tags=["public"])

app.mount("/assets", StaticFiles(directory="assets"), name="assets")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


if __name__ == "__main__":
    # Entry point for container/PaaS launch. Reads $PORT in Python so the port is
    # never subject to shell-expansion quirks (Railway/Fly inject $PORT at runtime).
    import os

    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
