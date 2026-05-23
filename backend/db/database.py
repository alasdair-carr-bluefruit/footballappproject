import os

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./football.db")
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def create_db_and_tables() -> None:
    from backend.db.models import MatchDB, PlayerDB, RotationPlanDB, SquadDB  # noqa: F401

    SQLModel.metadata.create_all(engine)

    # Additive migrations — safe to re-run on existing DBs
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE players ADD COLUMN shirt_number INTEGER",
            "ALTER TABLE matches ADD COLUMN status TEXT DEFAULT 'planned'",
            "ALTER TABLE matches ADD COLUMN current_slot INTEGER DEFAULT 0",
            "ALTER TABLE rotation_plans ADD COLUMN removed_players_json TEXT DEFAULT '{}'",
        ]:
            try:
                conn.execute(__import__("sqlalchemy").text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists


def get_session():
    with Session(engine) as session:
        yield session
