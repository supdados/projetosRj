"""area catalog table

Revision ID: c3d2e1f4a5b6
Revises: b4f6d7e8a901
Create Date: 2026-02-28 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d2e1f4a5b6'
down_revision = 'b4f6d7e8a901'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'area_catalog',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_area_catalog_name'),
    )


def downgrade():
    op.drop_table('area_catalog')
