"""document soft delete (deleted_at column)

Revision ID: 0005_document_softdelete
Revises: 0004_system_logs
Create Date: 2026-04-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_document_softdelete"
down_revision = "0004_system_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_deleted_at", table_name="documents")
    op.drop_column("documents", "deleted_at")
