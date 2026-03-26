from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api.routers import match_router, squad_router
from backend.db.database import create_db_and_tables


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    create_db_and_tables()
    yield


app = FastAPI(title="Football Rotation", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(squad_router, prefix="/api/squad", tags=["squad"])
app.include_router(match_router, prefix="/api/matches", tags=["matches"])

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
