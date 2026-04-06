"""processing_settings table

Revision ID: 0006_processing_settings
Revises: 0005_document_softdelete
Create Date: 2026-04-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_processing_settings"
down_revision = "0005_document_softdelete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("import_concurrency", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("ai_concurrency", sa.Integer(), nullable=False, server_default="4"),
    )
    # Standardwert sofort einfügen (Singleton)
    op.execute(
        "INSERT INTO processing_settings (id, import_concurrency, ai_concurrency) "
        "VALUES (1, 10, 4) ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("processing_settings")
