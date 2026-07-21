"""squads.account_id (multi-team owner FK)

Revision ID: b7f1e2a9c3d5
Revises: a8d3e6f1c2b4
Create Date: 2026-07-21 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7f1e2a9c3d5'
down_revision: Union[str, Sequence[str], None] = 'a8d3e6f1c2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add squads.account_id (the owning account) so one account can own many
    squads. AccountDB.squad_id keeps its name but now means the ACTIVE squad.
    Backfill from the existing 1:1 link (accounts.squad_id → squads.id). Guarded
    so it coexists with SQLModel.metadata.create_all() regardless of order."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("squads")}
    if "account_id" not in cols:
        op.add_column("squads", sa.Column("account_id", sa.Integer(), nullable=True))
    # Backfill: adopt each squad to the account that currently points at it.
    # Portable across SQLite + Postgres (correlated subquery, no UPDATE...FROM).
    op.execute(
        "UPDATE squads SET account_id = ("
        "SELECT a.id FROM accounts a WHERE a.squad_id = squads.id"
        ") WHERE account_id IS NULL"
    )


def downgrade() -> None:
    op.drop_column("squads", "account_id")
