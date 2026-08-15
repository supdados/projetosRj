"""user notifications

Revision ID: 9f2d4b8c1a11
Revises: 2b7c8e4d1f11
Create Date: 2026-02-22 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9f2d4b8c1a11'
down_revision = '2b7c8e4d1f11'
branch_labels = None
depends_on = None


def _has_table(name):
    """Guarda de instalação limpa (Sprint 5.3): em banco vazio a revisão histórica
    é no-op — o schema completo nasce na revisão baseline de catch-up."""
    import sqlalchemy as _sa
    from alembic import op as _op
    return name in _sa.inspect(_op.get_bind()).get_table_names()


def _has_column(table, column):
    import sqlalchemy as _sa
    from alembic import op as _op
    insp = _sa.inspect(_op.get_bind())
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade():
    if not _has_table("user") or _has_table("user_notification"):
        return
    op.create_table(
        'user_notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recipient_user_id', sa.Integer(), nullable=False),
        sa.Column('actor_user_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=80), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('target_url', sa.String(length=500), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['actor_user_id'], ['user.id']),
        sa.ForeignKeyConstraint(['recipient_user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_user_notification_recipient_user_id', 'user_notification', ['recipient_user_id'], unique=False)
    op.create_index('ix_user_notification_actor_user_id', 'user_notification', ['actor_user_id'], unique=False)
    op.create_index('ix_user_notification_event_type', 'user_notification', ['event_type'], unique=False)
    op.create_index('ix_user_notification_is_read', 'user_notification', ['is_read'], unique=False)
    op.create_index(
        'ix_user_notification_recipient_read_created',
        'user_notification',
        ['recipient_user_id', 'is_read', 'created_at'],
        unique=False,
    )
    op.alter_column('user_notification', 'is_read', server_default=None)


def downgrade():
    op.drop_index('ix_user_notification_recipient_read_created', table_name='user_notification')
    op.drop_index('ix_user_notification_is_read', table_name='user_notification')
    op.drop_index('ix_user_notification_event_type', table_name='user_notification')
    op.drop_index('ix_user_notification_actor_user_id', table_name='user_notification')
    op.drop_index('ix_user_notification_recipient_user_id', table_name='user_notification')
    op.drop_table('user_notification')
