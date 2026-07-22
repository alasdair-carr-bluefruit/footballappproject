"""invites.invited_by_account_id (coach self-service invite attribution)

Revision ID: c9d4e2b1a7f6
Revises: b7f1e2a9c3d5
Create Date: 2026-07-22 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c9d4e2b1a7f6'
down_revision: Union[str, Sequence[str], None] = 'b7f1e2a9c3d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add invites.invited_by_account_id so the admin portal can see which coach
    minted a self-service (invite-a-friend) link. NULL = admin-minted invite.
    Guarded so it coexists with SQLModel.metadata.create_all() regardless of order."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    # `invites` is created by SQLModel create_all (it postdates the baseline), which
    # always runs before migrations at startup — but guard anyway so this is safe
    # regardless of invocation order.
    if "invites" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("invites")}
    if "invited_by_account_id" not in cols:
        op.add_column("invites", sa.Column("invited_by_account_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("invites", "invited_by_account_id")
