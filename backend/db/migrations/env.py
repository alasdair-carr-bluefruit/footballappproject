from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

from backend.db import models  # noqa: F401 — registers all tables on SQLModel.metadata

# Import the application's engine and all model modules so SQLModel.metadata is
# fully populated. Migrations run against the same engine/DATABASE_URL as the app,
# so SQLite (local) and PostgreSQL (prod) are handled identically.
from backend.db.database import engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI connection)."""
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=engine.url.get_backend_name() == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against the application engine."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # batch mode lets SQLite emulate ALTER/DROP COLUMN via table copy
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
