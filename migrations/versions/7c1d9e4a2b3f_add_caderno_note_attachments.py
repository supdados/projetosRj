"""add caderno note attachments

Revision ID: 7c1d9e4a2b3f
Revises: 6a4f6d2c1b90
Create Date: 2026-04-12 23:25:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "7c1d9e4a2b3f"
down_revision = "6a4f6d2c1b90"
branch_labels = None
depends_on = None


def _column_exists(inspector, table_name, column_name):
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    with op.batch_alter_table("caderno_block", schema=None) as batch_op:
        if not _column_exists(inspector, "caderno_block", "attached_to_block_id"):
            batch_op.add_column(
                sa.Column("attached_to_block_id", sa.Integer(), nullable=True)
            )
        if not _column_exists(inspector, "caderno_block", "attached_offset_x"):
            batch_op.add_column(
                sa.Column(
                    "attached_offset_x",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
        if not _column_exists(inspector, "caderno_block", "attached_offset_y"):
            batch_op.add_column(
                sa.Column(
                    "attached_offset_y",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    with op.batch_alter_table("caderno_block", schema=None) as batch_op:
        if _column_exists(inspector, "caderno_block", "attached_offset_y"):
            batch_op.drop_column("attached_offset_y")
        if _column_exists(inspector, "caderno_block", "attached_offset_x"):
            batch_op.drop_column("attached_offset_x")
        if _column_exists(inspector, "caderno_block", "attached_to_block_id"):
            batch_op.drop_column("attached_to_block_id")
