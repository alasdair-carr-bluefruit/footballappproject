"""accounts.intros_seen: walkthrough + first-use intros seen, per account

Revision ID: d2a7f4c9e1b6
Revises: c4f1a8e2d7b3
Create Date: 2026-11-25 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2a7f4c9e1b6'
down_revision: Union[str, Sequence[str], None] = 'c4f1a8e2d7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Guarded so it coexists with SQLModel.metadata.create_all(). Existing rows get
    "" (= not yet backfilled); GET /api/auth/me fills it from the coach's data the
    first time they load the app, so they never see intros for features they use."""
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("accounts")}
    if "intros_seen" not in cols:
        op.add_column(
            "accounts",
            sa.Column("intros_seen", sa.Text(), server_default="", nullable=False),
        )


def downgrade() -> None:
    op.drop_column("accounts", "intros_seen")
