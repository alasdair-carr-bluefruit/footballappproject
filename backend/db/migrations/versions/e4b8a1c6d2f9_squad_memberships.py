"""squad_memberships (assistant coaches) + invites.squad_id/role

Revision ID: e4b8a1c6d2f9
Revises: c9d4e2b1a7f6
Create Date: 2026-09-28 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4b8a1c6d2f9'
down_revision: Union[str, Sequence[str], None] = 'c9d4e2b1a7f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-team roles (T3.2 assistant coach mode).

    - `squad_memberships`: who can access a squad and as what ("head" | "assistant").
      Normally created by SQLModel create_all (which runs first at startup); created
      here too if missing so a bare `alembic upgrade` works.
    - Backfill one "head" membership per owned squad (squads.account_id). Idempotent:
      skips squads that already have a membership row for their owner.
    - `invites.squad_id` / `invites.role`: an assistant invite joins an existing squad
      instead of creating a new coach + team.
    """
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "squad_memberships" not in tables:
        op.create_table(
            "squad_memberships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("squad_id", sa.Integer(), nullable=False, index=True),
            sa.Column("account_id", sa.Integer(), nullable=False, index=True),
            sa.Column("role", sa.String(), nullable=False, server_default="head"),
            sa.Column("created_at", sa.String(), nullable=False, server_default=""),
            sa.Column("invited_by_account_id", sa.Integer(), nullable=True),
            sa.UniqueConstraint("squad_id", "account_id", name="uq_membership_squad_account"),
        )

    # Portable across SQLite + Postgres (INSERT ... SELECT with NOT EXISTS).
    op.execute(
        "INSERT INTO squad_memberships (squad_id, account_id, role, created_at) "
        "SELECT s.id, s.account_id, 'head', '' FROM squads s "
        "WHERE s.account_id IS NOT NULL AND NOT EXISTS ("
        "SELECT 1 FROM squad_memberships m "
        "WHERE m.squad_id = s.id AND m.account_id = s.account_id)"
    )

    if "invites" in tables:
        cols = {c["name"] for c in insp.get_columns("invites")}
        if "squad_id" not in cols:
            op.add_column("invites", sa.Column("squad_id", sa.Integer(), nullable=True))
        if "role" not in cols:
            op.add_column(
                "invites", sa.Column("role", sa.String(), nullable=False, server_default="")
            )


def downgrade() -> None:
    op.drop_column("invites", "role")
    op.drop_column("invites", "squad_id")
    op.drop_table("squad_memberships")
