"""coach-set max_subs cap on tournaments (+ denormalised onto matches)

Revision ID: a8d3e6f1c2b4
Revises: f7c2d9a4b8e1
Create Date: 2026-07-20 15:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a8d3e6f1c2b4'
down_revision: Union[str, Sequence[str], None] = 'f7c2d9a4b8e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tournaments.max_subs and matches.max_subs. Nullable — NULL means
    'fall back to the per-size preset mid-period sub cap'. Guarded so they
    coexist with SQLModel.metadata.create_all() regardless of which runs first."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in ("tournaments", "matches"):
        cols = {c["name"] for c in insp.get_columns(table)}
        if "max_subs" not in cols:
            op.add_column(table, sa.Column("max_subs", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("matches", "max_subs")
    op.drop_column("tournaments", "max_subs")
