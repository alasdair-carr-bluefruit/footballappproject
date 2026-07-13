import os
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./football.db")

# Repo root holds alembic.ini; backend/db/database.py → parents[2].
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
_BASELINE_REVISION = "4cf63d43cd4c"

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
]


def create_db_and_tables() -> None:
    import backend.db.models  # noqa: F401 — registers all tables on SQLModel.metadata

    SQLModel.metadata.create_all(engine)
    _apply_legacy_additive_columns()
    _run_migrations()


def _apply_legacy_additive_columns() -> None:
    """Legacy bridge: ensure pre-Alembic instances reach baseline schema.

    Baseline (Alembic revision 4cf63d43cd4c) assumes these columns exist, so an
    older instance that never received one of them must be topped up before it is
    stamped at baseline. Inspection-based and idempotent — a no-op scan once an
    instance is fully migrated. New schema changes go through Alembic, not here.
    """
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


def _run_migrations() -> None:
    """Bring the database up to the latest Alembic revision.

    On a pre-Alembic database (tables exist from create_all + the legacy bridge
    above, but no alembic_version table), stamp it at baseline first so only the
    post-baseline data migrations run. Then upgrade to head.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    if "alembic_version" not in inspect(engine).get_table_names():
        command.stamp(cfg, _BASELINE_REVISION)
    command.upgrade(cfg, "head")


def get_session():
    with Session(engine) as session:
        yield session
