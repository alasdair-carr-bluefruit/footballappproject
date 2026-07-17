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
from backend.db.database import create_db_and_tables
from backend.settings import auth_enabled, frontend_origin, validate_config


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

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(squad_router, prefix="/api/squad", tags=["squad"])
app.include_router(match_router, prefix="/api/matches", tags=["matches"])
app.include_router(tournament_router, prefix="/api/tournaments", tags=["tournaments"])
app.include_router(feedback_router, prefix="/api/feedback", tags=["feedback"])

app.mount("/assets", StaticFiles(directory="assets"), name="assets")
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
