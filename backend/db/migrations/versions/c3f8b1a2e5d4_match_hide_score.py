"""per-match hide_score flag (FA sub-U12 scoreline masking)

Revision ID: c3f8b1a2e5d4
Revises: b2e4a9c17d30
Create Date: 2026-07-17 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c3f8b1a2e5d4'
down_revision: Union[str, Sequence[str], None] = 'b2e4a9c17d30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add matches.hide_score. Guarded so it coexists with
    SQLModel.metadata.create_all() regardless of which runs first."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    match_cols = {c["name"] for c in insp.get_columns("matches")}
    if "hide_score" not in match_cols:
        op.add_column(
            "matches",
            sa.Column("hide_score", sa.Integer(), server_default="0", nullable=False),
        )


def downgrade() -> None:
    op.drop_column("matches", "hide_score")
