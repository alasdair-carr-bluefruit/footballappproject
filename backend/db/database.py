import os

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./football.db")

# check_same_thread is SQLite-only; PostgreSQL doesn't accept it
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)


def create_db_and_tables() -> None:
    from backend.db.models import MatchDB, PlayerDB, RotationPlanDB, SquadDB, TournamentDB  # noqa: F401

    SQLModel.metadata.create_all(engine)

    # Additive migrations — safe to re-run on existing DBs
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE players ADD COLUMN shirt_number INTEGER",
            "ALTER TABLE players ADD COLUMN source_tournament_id INTEGER",
            "ALTER TABLE matches ADD COLUMN status TEXT DEFAULT 'planned'",
            "ALTER TABLE matches ADD COLUMN current_slot INTEGER DEFAULT 0",
            "ALTER TABLE matches ADD COLUMN tournament_id INTEGER",
            "ALTER TABLE matches ADD COLUMN tournament_stage TEXT DEFAULT ''",
            "ALTER TABLE matches ADD COLUMN match_number INTEGER",
            "ALTER TABLE rotation_plans ADD COLUMN removed_players_json TEXT DEFAULT '{}'",
            "ALTER TABLE tournaments ADD COLUMN player_position_overrides_json TEXT DEFAULT '{}'",
        ]:
            try:
                conn.execute(__import__("sqlalchemy").text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists


def get_session():
    with Session(engine) as session:
        yield session
