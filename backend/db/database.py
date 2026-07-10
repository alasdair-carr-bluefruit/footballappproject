import os

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./football.db")

# check_same_thread is SQLite-only; PostgreSQL doesn't accept it
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)


# Additive-only migrations: (table, column, column definition).
# Each is applied only if the column is missing, so this is safe to re-run and
# safe on both SQLite and PostgreSQL (no shared transaction to abort). ADD COLUMN
# is non-destructive — existing rows get the DEFAULT.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("players", "shirt_number", "INTEGER"),
    ("players", "source_tournament_id", "INTEGER"),
    ("matches", "status", "TEXT DEFAULT 'planned'"),
    ("matches", "current_slot", "INTEGER DEFAULT 0"),
    ("matches", "tournament_id", "INTEGER"),
    ("matches", "tournament_stage", "TEXT DEFAULT ''"),
    ("matches", "match_number", "INTEGER"),
    ("rotation_plans", "removed_players_json", "TEXT DEFAULT '{}'"),
    ("tournaments", "player_position_overrides_json", "TEXT DEFAULT '{}'"),
    ("matches", "timer_mode", "TEXT DEFAULT 'up'"),
    ("tournaments", "timer_mode", "TEXT DEFAULT 'up'"),
]


def create_db_and_tables() -> None:
    from backend.db.models import MatchDB, PlayerDB, RotationPlanDB, SquadDB, TournamentDB  # noqa: F401

    SQLModel.metadata.create_all(engine)

    # Inspect existing schema and add only the columns that are genuinely missing.
    # Each ALTER runs in its own transaction; a real failure is raised, not
    # silently swallowed (a missing-column-that-should-exist would otherwise
    # surface later as an opaque 500).
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table, column, coldef in _ADDITIVE_COLUMNS:
        if table not in existing_tables:
            continue  # table doesn't exist yet — create_all owns its schema
        columns = {c["name"] for c in inspector.get_columns(table)}
        if column in columns:
            continue  # already present
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}"))


def get_session():
    with Session(engine) as session:
        yield session
