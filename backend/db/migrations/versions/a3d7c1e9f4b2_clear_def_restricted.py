"""DEF no longer special: clear players.def_restricted

Revision ID: a3d7c1e9f4b2
Revises: e1b4f2a9c6d7
Create Date: 2026-11-24 12:00:00.000000

Owner decision 2026-11-24: an unticked DEF is a soft preference like an unticked
MID or ATT (preferred_positions already carries it). The flag made the engine treat
it as near-hard. Data-only; the column stays so older clients keep working.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3d7c1e9f4b2'
down_revision: Union[str, Sequence[str], None] = 'e1b4f2a9c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE players SET def_restricted = :f WHERE def_restricted = :t")
               .bindparams(f=False, t=True))


def downgrade() -> None:
    # Re-derive from the position picks (DEF missing from a non-empty list).
    # JSON text match is enough: preferred_positions is a JSON list of codes.
    op.execute(sa.text(
        "UPDATE players SET def_restricted = :t "
        "WHERE preferred_positions NOT IN ('', '[]') AND preferred_positions NOT LIKE '%\"DEF\"%'"
    ).bindparams(t=True))
