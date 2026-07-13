"""relational rotation storage

Revision ID: 57b6bfa73768
Revises: 4cf63d43cd4c
Create Date: 2026-07-12 06:40:15.251766

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '57b6bfa73768'
down_revision: Union[str, Sequence[str], None] = '4cf63d43cd4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Table DDL builders. Each is only executed when the table is missing, so this
# migration coexists safely with SQLModel.metadata.create_all() (checkfirst=True)
# regardless of which runs first.
def _create_goal_records() -> None:
    op.create_table(
        'goal_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('goals', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_id', 'player_id', name='uq_goal_match_player'),
    )
    with op.batch_alter_table('goal_records', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_goal_records_match_id'), ['match_id'], unique=False)


def _create_match_availability() -> None:
    op.create_table(
        'match_availability',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_id', 'player_id', name='uq_avail_match_player'),
    )
    with op.batch_alter_table('match_availability', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_match_availability_match_id'), ['match_id'], unique=False,
        )


def _create_removed_players() -> None:
    op.create_table(
        'removed_players',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('from_slot', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_id', 'player_id', name='uq_removed_match_player'),
    )
    with op.batch_alter_table('removed_players', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_removed_players_match_id'), ['match_id'], unique=False)


def _create_slots() -> None:
    op.create_table(
        'slots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('slot_index', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['match_id'], ['matches.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('match_id', 'slot_index', name='uq_slot_match_index'),
    )
    with op.batch_alter_table('slots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_slots_match_id'), ['match_id'], unique=False)


def _create_slot_assignments() -> None:
    op.create_table(
        'slot_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slot_id', sa.Integer(), nullable=False),
        sa.Column('position', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['slot_id'], ['slots.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slot_id', 'position', name='uq_assignment_slot_position'),
    )
    with op.batch_alter_table('slot_assignments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_slot_assignments_slot_id'), ['slot_id'], unique=False)


_TABLE_BUILDERS = {
    'goal_records': _create_goal_records,
    'match_availability': _create_match_availability,
    'removed_players': _create_removed_players,
    'slots': _create_slots,
    'slot_assignments': _create_slot_assignments,
}


def upgrade() -> None:
    """Create relational rotation tables (if absent) and backfill from JSON blobs."""
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())

    # slots must exist before slot_assignments (FK); dict order guarantees it.
    for name, builder in _TABLE_BUILDERS.items():
        if name not in existing:
            builder()

    _backfill(bind)


def _backfill(bind: sa.engine.Connection) -> None:
    """Copy RotationPlanDB JSON blobs into the relational tables.

    Idempotent: skips if slots are already populated (a plan with slots always
    produces at least one slot row), so re-running or re-stamping is safe.
    """
    meta = sa.MetaData()
    meta.reflect(bind=bind, only=[
        'rotation_plans', 'slots', 'slot_assignments',
        'goal_records', 'match_availability', 'removed_players',
    ])
    slots_t = meta.tables['slots']
    assign_t = meta.tables['slot_assignments']
    goals_t = meta.tables['goal_records']
    avail_t = meta.tables['match_availability']
    removed_t = meta.tables['removed_players']
    rp = meta.tables['rotation_plans']

    already = bind.execute(sa.select(sa.func.count()).select_from(slots_t)).scalar()
    if already:
        return  # backfill already done

    rows = bind.execute(sa.select(
        rp.c.match_id, rp.c.slots_json, rp.c.goals_json,
        rp.c.available_player_ids_json, rp.c.removed_players_json,
    )).fetchall()

    for row in rows:
        mid = row.match_id

        for slot in json.loads(row.slots_json or "[]"):
            res = bind.execute(
                sa.insert(slots_t).values(match_id=mid, slot_index=slot["slot_index"])
            )
            slot_id = res.inserted_primary_key[0]
            for position, pid in (slot.get("lineup") or {}).items():
                if pid is None:
                    continue
                bind.execute(sa.insert(assign_t).values(
                    slot_id=slot_id, position=position, player_id=pid,
                ))

        for pid_str, count in json.loads(row.goals_json or "{}").items():
            bind.execute(sa.insert(goals_t).values(
                match_id=mid, player_id=int(pid_str), goals=count,
            ))

        for pid in dict.fromkeys(json.loads(row.available_player_ids_json or "[]")):
            bind.execute(sa.insert(avail_t).values(match_id=mid, player_id=pid))

        for pid_str, from_slot in json.loads(row.removed_players_json or "{}").items():
            bind.execute(sa.insert(removed_t).values(
                match_id=mid, player_id=int(pid_str), from_slot=from_slot,
            ))


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('slot_assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_slot_assignments_slot_id'))

    op.drop_table('slot_assignments')
    with op.batch_alter_table('slots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_slots_match_id'))

    op.drop_table('slots')
    with op.batch_alter_table('removed_players', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_removed_players_match_id'))

    op.drop_table('removed_players')
    with op.batch_alter_table('match_availability', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_match_availability_match_id'))

    op.drop_table('match_availability')
    with op.batch_alter_table('goal_records', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_goal_records_match_id'))

    op.drop_table('goal_records')
    # ### end Alembic commands ###
