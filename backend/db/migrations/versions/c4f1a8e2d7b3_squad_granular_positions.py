"""squads.granular_positions: coach toggle to read position picks as LB/CB/RB…

Revision ID: c4f1a8e2d7b3
Revises: b8e2f4a6c9d1
Create Date: 2026-11-24 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4f1a8e2d7b3'
down_revision: Union[str, Sequence[str], None] = 'b8e2f4a6c9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Guarded so it coexists with SQLModel.metadata.create_all(). Default off."""
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("squads")}
    if "granular_positions" not in cols:
        op.add_column(
            "squads",
            sa.Column("granular_positions", sa.Boolean(), server_default=sa.false(), nullable=False),
        )


def downgrade() -> None:
    op.drop_column("squads", "granular_positions")
