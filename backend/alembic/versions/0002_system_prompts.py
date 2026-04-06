"""system_prompts table

Revision ID: 0002_system_prompts
Revises: 0001_initial
Create Date: 2026-04-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_system_prompts"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_prompts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_system_prompts_id"), "system_prompts", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_system_prompts_id"), table_name="system_prompts")
    op.drop_table("system_prompts")
