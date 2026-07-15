"""match length as float + per-match/tournament show_timer

Revision ID: b2e4a9c17d30
Revises: 57b6bfa73768
Create Date: 2026-07-15 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b2e4a9c17d30'
down_revision: Union[str, Sequence[str], None] = '57b6bfa73768'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add show_timer flags; widen matches.quarter_length_mins to float.

    Guarded so it coexists with SQLModel.metadata.create_all() (which may already
    have added the columns) regardless of which runs first.
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)

    match_cols = {c["name"] for c in insp.get_columns("matches")}
    if "show_timer" not in match_cols:
        op.add_column(
            "matches",
            sa.Column("show_timer", sa.Integer(), server_default="1", nullable=False),
        )

    tourn_cols = {c["name"] for c in insp.get_columns("tournaments")}
    if "show_timer" not in tourn_cols:
        op.add_column(
            "tournaments",
            sa.Column("show_timer", sa.Integer(), server_default="1", nullable=False),
        )

    # Allow fractional period lengths (e.g. 12.5-min quarters). Only Postgres has a
    # fixed column type that must be altered; SQLite is dynamically typed and stores
    # a REAL in the existing INTEGER-affinity column with no rewrite needed.
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "matches", "quarter_length_mins",
            existing_type=sa.Integer(), type_=sa.Float(), existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "matches", "quarter_length_mins",
            existing_type=sa.Float(), type_=sa.Integer(), existing_nullable=False,
        )
    op.drop_column("tournaments", "show_timer")
    op.drop_column("matches", "show_timer")
