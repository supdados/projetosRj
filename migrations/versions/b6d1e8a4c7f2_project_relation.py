"""project relation

Revision ID: b6d1e8a4c7f2
Revises: 0257819cbe43
Create Date: 2026-08-25 10:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

revision = "b6d1e8a4c7f2"
down_revision = "0257819cbe43"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if _has_table("project_relation"):
        return

    op.create_table(
        "project_relation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_low_id", sa.Integer(), nullable=False),
        sa.Column("project_high_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_low_id"],
            ["project.id"],
            name="fk_project_relation_low",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_high_id"],
            ["project.id"],
            name="fk_project_relation_high",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user.id"],
            name="fk_project_relation_created_by",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_low_id", "project_high_id", name="uq_project_relation_pair"
        ),
    )
    op.create_index(
        "ix_project_relation_project_high_id",
        "project_relation",
        ["project_high_id"],
    )


def downgrade():
    if not _has_table("project_relation"):
        return

    inspector = sa.inspect(op.get_bind())
    existing_indexes = {ix["name"] for ix in inspector.get_indexes("project_relation")}
    if "ix_project_relation_project_high_id" in existing_indexes:
        op.drop_index(
            "ix_project_relation_project_high_id", table_name="project_relation"
        )

    op.drop_table("project_relation")
