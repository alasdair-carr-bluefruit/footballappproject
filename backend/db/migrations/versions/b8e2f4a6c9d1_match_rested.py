"""match_rested: players the coach rested (owed time later) vs simply unavailable

Revision ID: b8e2f4a6c9d1
Revises: a3d7c1e9f4b2
Create Date: 2026-11-24 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8e2f4a6c9d1'
down_revision: Union[str, Sequence[str], None] = 'a3d7c1e9f4b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Guarded so it coexists with SQLModel.metadata.create_all()."""
    insp = sa.inspect(op.get_bind())
    if "match_rested" in insp.get_table_names():
        return
    op.create_table(
        "match_rested",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.UniqueConstraint("match_id", "player_id", name="uq_rested_match_player"),
    )
    op.create_index("ix_match_rested_match_id", "match_rested", ["match_id"])


def downgrade() -> None:
    op.drop_index("ix_match_rested_match_id", table_name="match_rested")
    op.drop_table("match_rested")
