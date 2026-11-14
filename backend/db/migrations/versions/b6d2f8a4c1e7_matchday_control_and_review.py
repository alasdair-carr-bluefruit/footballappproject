"""matchday control + server clock, plan review mark, notify_plans

Revision ID: b6d2f8a4c1e7
Revises: a1c5e9d3b7f2
Create Date: 2026-11-14 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b6d2f8a4c1e7'
down_revision: Union[str, Sequence[str], None] = 'a1c5e9d3b7f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns() -> list[tuple[str, sa.Column]]:
    return [
        ("matches", sa.Column("reviewed_at", sa.String(), nullable=True)),
        ("matches", sa.Column("controller_account_id", sa.Integer(), nullable=True)),
        ("matches", sa.Column("controller_device_id", sa.String(), server_default="", nullable=False)),
        ("matches", sa.Column("controller_since", sa.String(), nullable=True)),
        ("matches", sa.Column("timer_running", sa.Integer(), server_default="0", nullable=False)),
        ("matches", sa.Column("timer_elapsed_ms", sa.Integer(), server_default="0", nullable=False)),
        ("matches", sa.Column("timer_anchor_at", sa.String(), nullable=True)),
        ("tournaments", sa.Column("reviewed_at", sa.String(), nullable=True)),
        ("accounts", sa.Column("notify_plans", sa.Integer(), server_default="1", nullable=False)),
    ]


def upgrade() -> None:
    """All additive, all with safe defaults — existing rows behave exactly as before
    (no controller, no server clock, not reviewed, notifications on). Guarded so it
    coexists with SQLModel.metadata.create_all() regardless of which runs first."""
    insp = sa.inspect(op.get_bind())
    existing = {t: {c["name"] for c in insp.get_columns(t)} for t in ("matches", "tournaments", "accounts")}
    for table, column in _columns():
        if column.name not in existing[table]:
            op.add_column(table, column)


def downgrade() -> None:
    for table, column in reversed(_columns()):
        op.drop_column(table, column.name)
