"""matches / tournaments .created_by_account_id (assistant-authored plans)

Revision ID: a1c5e9d3b7f2
Revises: e4b8a1c6d2f9
Create Date: 2026-11-14 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c5e9d3b7f2'
down_revision: Union[str, Sequence[str], None] = 'e4b8a1c6d2f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("matches", "tournaments")


def upgrade() -> None:
    """Record who created a match / tournament, so an assistant coach can edit and
    run the plans they made (and nobody else's). Nullable, no backfill: existing
    rows stay NULL = head-coach only, which is exactly today's behaviour. Guarded so
    it coexists with SQLModel.metadata.create_all() regardless of which runs first."""
    insp = sa.inspect(op.get_bind())
    for table in TABLES:
        cols = {c["name"] for c in insp.get_columns(table)}
        if "created_by_account_id" not in cols:
            op.add_column(table, sa.Column("created_by_account_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "created_by_account_id")
