"""project product_link column

Revision ID: f7a9c3e1b2d4
Revises: 8c342aa73f17
Create Date: 2026-04-12 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "f7a9c3e1b2d4"
down_revision = "8c342aa73f17"
branch_labels = None
depends_on = None


def _column_exists(inspector, table_name, column_name):
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _column_exists(inspector, "project", "product_link"):
        op.add_column(
            "project", sa.Column("product_link", sa.String(length=500), nullable=True)
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _column_exists(inspector, "project", "product_link"):
        op.drop_column("project", "product_link")
