"""per-match/tournament share_gk flag (specialist keeper time sharing)

Revision ID: d5a9c7e1f3b2
Revises: c3f8b1a2e5d4
Create Date: 2026-07-18 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd5a9c7e1f3b2'
down_revision: Union[str, Sequence[str], None] = 'c3f8b1a2e5d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add matches.share_gk and tournaments.share_gk. Guarded so they coexist
    with SQLModel.metadata.create_all() regardless of which runs first.
    Default 1 = a specialist keeper rotates out for equal time."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in ("matches", "tournaments"):
        cols = {c["name"] for c in insp.get_columns(table)}
        if "share_gk" not in cols:
            op.add_column(
                table,
                sa.Column("share_gk", sa.Integer(), server_default="1", nullable=False),
            )


def downgrade() -> None:
    op.drop_column("tournaments", "share_gk")
    op.drop_column("matches", "share_gk")
