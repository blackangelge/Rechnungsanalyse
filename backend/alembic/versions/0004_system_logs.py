"""system_logs table

Revision ID: 0004_system_logs
Revises: 0003_supplier
Create Date: 2026-04-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0004_system_logs"
down_revision = "0003_supplier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("level", sa.String(20), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("import_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_logs_id", "system_logs", ["id"], unique=False)
    op.create_index("ix_system_logs_category", "system_logs", ["category"], unique=False)
    op.create_index("ix_system_logs_created_at", "system_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_system_logs_created_at", table_name="system_logs")
    op.drop_index("ix_system_logs_category", table_name="system_logs")
    op.drop_index("ix_system_logs_id", table_name="system_logs")
    op.drop_table("system_logs")
