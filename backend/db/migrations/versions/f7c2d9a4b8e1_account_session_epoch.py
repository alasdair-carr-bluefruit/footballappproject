"""accounts.session_epoch (sign-out-everywhere / reclaim support)

Revision ID: f7c2d9a4b8e1
Revises: d5a9c7e1f3b2
Create Date: 2026-07-20 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f7c2d9a4b8e1'
down_revision: Union[str, Sequence[str], None] = 'd5a9c7e1f3b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add accounts.session_epoch. Bumping it invalidates all issued session
    cookies for that account (reclaim = 'sign out of all devices'). Guarded so it
    coexists with SQLModel.metadata.create_all() regardless of which runs first.
    (reclaim_tokens is a brand-new table, so create_all handles it — no op here.)"""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("accounts")}
    if "session_epoch" not in cols:
        op.add_column(
            "accounts",
            sa.Column("session_epoch", sa.Integer(), server_default="0", nullable=False),
        )


def downgrade() -> None:
    op.drop_column("accounts", "session_epoch")
