"""per-match own_goals (own goals scored by the opposition, counting for us)

Revision ID: e1b4f2a9c6d7
Revises: b6d2f8a4c1e7
Create Date: 2026-11-14 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1b4f2a9c6d7'
down_revision: Union[str, Sequence[str], None] = 'b6d2f8a4c1e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add matches.own_goals. Guarded so it coexists with
    SQLModel.metadata.create_all() regardless of which runs first.
    Default 0 = no opposition own goals recorded."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("matches")}
    if "own_goals" not in cols:
        op.add_column(
            "matches",
            sa.Column("own_goals", sa.Integer(), server_default="0", nullable=False),
        )


def downgrade() -> None:
    op.drop_column("matches", "own_goals")
